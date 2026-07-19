import asyncio
from bleak import BleakError
import logging
import time
from typing import Dict, List, Mapping, Optional, Set, Tuple, cast
from bluetti_mqtt.bluetooth import BadConnectionError, MultiDeviceManager, ModbusError, ParseError, build_device
from bluetti_mqtt.bus import CommandMessage, CommandResultMessage, EventBus, ParserMessage, PublicCommandMessage
from bluetti_mqtt.command import CommandExecutor
from bluetti_mqtt.core import BluettiDevice, ReadHoldingRegisters


class DeviceHandler:
    def __init__(
        self,
        addresses: List[str],
        interval: int,
        bus: EventBus,
        expected_models: Optional[Mapping[str, str]] = None,
        minimum_update_intervals: Optional[Mapping[Tuple[str, str], int]] = None,
    ):
        self.manager = MultiDeviceManager(addresses)
        self.command_executor = CommandExecutor(
            self.manager,
            minimum_update_intervals=minimum_update_intervals,
        )
        self.devices: Dict[str, BluettiDevice] = {}
        self.expected_models = dict(expected_models or {})
        self.disabled_addresses: Set[str] = set()
        self.public_command_tasks: Set[asyncio.Task] = set()
        self.interval = interval
        self.bus = bus

    async def run(self):
        loop = asyncio.get_running_loop()

        # Start manager
        manager_task = loop.create_task(self.manager.run())

        # Connect to event bus
        self.bus.add_command_listener(self.handle_command)
        self.bus.add_public_command_listener(self.handle_public_command)

        # Poll the clients
        logging.info('Starting to poll clients...')
        polling_tasks = [self._poll(a) for a in self.manager.addresses]
        pack_polling_tasks = [self._pack_poll(a) for a in self.manager.addresses]
        try:
            await asyncio.gather(*(polling_tasks + pack_polling_tasks + [manager_task]))
        finally:
            command_tasks = list(self.public_command_tasks)
            for task in command_tasks:
                task.cancel()
            await asyncio.gather(*command_tasks, return_exceptions=True)

    async def handle_command(self, msg: CommandMessage):
        if self.manager.is_ready(msg.device.address):
            logging.debug(f'Performing command {msg.device}: {msg.command}')
            await self.manager.perform_nowait(msg.device.address, msg.command)

    async def handle_public_command(self, msg: PublicCommandMessage):
        task = asyncio.create_task(self._execute_public_command(msg))
        self.public_command_tasks.add(task)
        task.add_done_callback(self.public_command_tasks.discard)

    async def _execute_public_command(self, msg: PublicCommandMessage):
        result = await self.command_executor.execute(msg.request)
        await self.bus.put(CommandResultMessage(result))

    async def _poll(self, address: str):
        while True:
            if not self.manager.is_ready(address):
                logging.debug(f'Waiting for connection to {address} to start polling...')
                await asyncio.sleep(1)
                continue

            device = self._get_device(address)
            if device is None:
                return

            # Send all polling commands
            start_time = time.monotonic()
            for command in device.polling_commands:
                await self._poll_with_command(device, command)
            elapsed = time.monotonic() - start_time

            # Limit polling rate if interval provided
            if self.interval > 0 and self.interval > elapsed:
                await asyncio.sleep(self.interval - elapsed)

    async def _pack_poll(self, address: str):
        while True:
            if not self.manager.is_ready(address):
                logging.debug(f'Waiting for connection to {address} to start pack polling...')
                await asyncio.sleep(1)
                continue

            # Break if there's nothing to poll
            device = self._get_device(address)
            if device is None:
                return
            if len(device.pack_logging_commands) == 0:
                break

            start_time = time.monotonic()
            for pack in range(1, device.pack_num_max + 1):
                # Send pack set command if the device supports more than 1 pack
                if device.pack_num_max > 1:
                    command = device.build_setter_command('pack_num', pack)
                    await self.manager.perform_nowait(address, command)
                    await asyncio.sleep(10)  # We need to wait after switching packs for the data to be available

                # Poll
                for command in device.pack_logging_commands:
                    await self._poll_with_command(device, command)
            elapsed = time.monotonic() - start_time

            # Limit polling rate if interval provided
            if self.interval > 0 and self.interval > elapsed:
                await asyncio.sleep(self.interval - elapsed)

    async def _poll_with_command(self, device: BluettiDevice, command: ReadHoldingRegisters):
        response_future = await self.manager.perform(device.address, command)
        try:
            response = cast(bytes, await response_future)
            body = command.parse_response(response)
            parsed = device.parse(command.starting_address, body)
            await self.bus.put(ParserMessage(device, parsed))
        except ParseError:
            logging.debug('Got a parse exception...')
        except ModbusError as err:
            logging.debug(f'Got an invalid request error for {command}: {err}')
        except (BadConnectionError, BleakError) as err:
            logging.debug(f'Needed to disconnect due to error: {err}')

    def _get_device(self, address: str):
        if address in self.disabled_addresses:
            return None
        if address not in self.devices:
            name = self.manager.get_name(address)
            try:
                device = build_device(address, name)
            except ValueError:
                logging.exception(f'Disabling {address}: unsupported discovered device name {name!r}')
                self.disabled_addresses.add(address)
                return None
            expected_model = self.expected_models.get(address)
            if expected_model is not None and device.type != expected_model:
                logging.error(
                    f'Disabling {address}: configured model {expected_model} does not match discovered {device.type}'
                )
                self.disabled_addresses.add(address)
                return None
            self.devices[address] = device
        return self.devices[address]
