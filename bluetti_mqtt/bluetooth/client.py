import asyncio
from enum import Enum, auto, unique
import logging
from typing import Callable, Union
from bleak import BleakClient, BleakError
from bleak.exc import BleakDeviceNotFoundError
from bluetti_mqtt.core import DeviceCommand
from bluetti_mqtt.core.devices.capabilities import ExecutionPolicy
from .exc import (
    BadConnectionError,
    ConnectionChangedError,
    DispatchTimeoutError,
    ModbusError,
    ParseError,
)


@unique
class ClientState(Enum):
    NOT_CONNECTED = auto()
    CONNECTED = auto()
    READY = auto()
    PERFORMING_COMMAND = auto()
    COMMAND_ERROR_WAIT = auto()
    DISCONNECTING = auto()


class BluetoothClient:
    RESPONSE_TIMEOUT = 5
    # BLE has no message boundary beyond notifications. Require a short quiet
    # period after a complete MODBUS frame so a trailing fragment is rejected.
    RESPONSE_QUIET_WINDOW = 0.01
    WRITE_UUID = '0000ff02-0000-1000-8000-00805f9b34fb'
    NOTIFY_UUID = '0000ff01-0000-1000-8000-00805f9b34fb'
    DEVICE_NAME_UUID = '00002a00-0000-1000-8000-00805f9b34fb'

    name: Union[str, None]
    current_command: DeviceCommand
    notify_future: asyncio.Future
    notify_response: bytearray

    def __init__(self, address: str):
        self.address = address
        self.state = ClientState.NOT_CONNECTED
        self.name = None
        self.client = BleakClient(self.address)
        self.command_queue = asyncio.Queue()
        self.notify_future = None
        self.loop = asyncio.get_running_loop()
        self.connection_generation = 0

    @property
    def is_ready(self):
        return self.state == ClientState.READY or self.state == ClientState.PERFORMING_COMMAND

    async def perform(
        self,
        cmd: DeviceCommand,
        policy: ExecutionPolicy = None,
        on_attempt: Callable[[], None] = None,
    ):
        future = self.loop.create_future()
        resolved_policy = policy or ExecutionPolicy()
        expires_at = None
        expiry_handle = None
        if resolved_policy.dispatch_timeout is not None:
            expires_at = self.loop.time() + resolved_policy.dispatch_timeout
            expiry_handle = self.loop.call_later(
                resolved_policy.dispatch_timeout,
                self._expire_queued_command,
                future,
            )
        await self.command_queue.put((
            cmd,
            future,
            resolved_policy,
            on_attempt,
            self.connection_generation,
            expires_at,
            expiry_handle,
        ))
        return future

    async def perform_nowait(
        self,
        cmd: DeviceCommand,
        policy: ExecutionPolicy = None,
        on_attempt: Callable[[], None] = None,
    ):
        await self.command_queue.put((
            cmd,
            None,
            policy or ExecutionPolicy(),
            on_attempt,
            self.connection_generation,
            None,
            None,
        ))

    @staticmethod
    def _expire_queued_command(future: asyncio.Future):
        if not future.done():
            future.set_exception(DispatchTimeoutError('command expired before BLE dispatch'))

    async def run(self):
        try:
            while True:
                if self.state == ClientState.NOT_CONNECTED:
                    await self._connect()
                elif self.state == ClientState.CONNECTED:
                    if not self.name:
                        await self._get_name()
                    else:
                        await self._start_listening()
                elif self.state == ClientState.READY:
                    await self._perform_command()
                elif self.state == ClientState.DISCONNECTING:
                    await self._disconnect()
                else:
                    logging.warn(f'Unexpected current state {self.state}')
                    self.state = ClientState.NOT_CONNECTED
        finally:
            # Ensure that we disconnect
            if self.client:
                await self.client.disconnect()

    async def _connect(self):
        """Establish connection to the bluetooth device"""
        try:
            await self.client.connect()
            self.connection_generation += 1
            self.state = ClientState.CONNECTED
            logging.info(f'Connected to device: {self.address}')
        except BleakDeviceNotFoundError:
            logging.debug(f'Error connecting to device {self.address}: Not found')
        except (BleakError, EOFError, asyncio.TimeoutError):
            logging.exception(f'Error connecting to device {self.address}:')
            await asyncio.sleep(1)

    async def _get_name(self):
        """Get device name, which can be parsed for type"""
        try:
            name = await self.client.read_gatt_char(self.DEVICE_NAME_UUID)
            self.name = name.decode('ascii')
            logging.info(f'Device {self.address} has name: {self.name}')
        except BleakError:
            logging.exception(f'Error retrieving device name {self.address}:')
            self.state = ClientState.DISCONNECTING

    async def _start_listening(self):
        """Register for command response notifications"""
        try:
            await self.client.start_notify(
                self.NOTIFY_UUID,
                self._notification_handler)
            self.state = ClientState.READY
        except BleakError:
            self.state = ClientState.DISCONNECTING

    async def _perform_command(self):
        cmd, cmd_future, policy, on_attempt, generation, expires_at, expiry_handle = await self.command_queue.get()
        if cmd_future is not None and cmd_future.done():
            if expiry_handle is not None:
                expiry_handle.cancel()
            self.command_queue.task_done()
            return
        if expires_at is not None and self.loop.time() >= expires_at:
            if cmd_future is not None and not cmd_future.done():
                cmd_future.set_exception(DispatchTimeoutError('command expired before BLE dispatch'))
            if expiry_handle is not None:
                expiry_handle.cancel()
            self.command_queue.task_done()
            return
        if policy.requires_same_connection and generation != self.connection_generation:
            if cmd_future is not None and not cmd_future.done():
                cmd_future.set_exception(ConnectionChangedError('command expired after reconnect'))
            if expiry_handle is not None:
                expiry_handle.cancel()
            self.command_queue.task_done()
            return
        if expiry_handle is not None:
            expiry_handle.cancel()
        attempts = 0
        last_error = None
        while attempts < policy.max_attempts:
            try:
                attempts += 1
                # Prepare to make request
                self.state = ClientState.PERFORMING_COMMAND
                self.current_command = cmd
                self.notify_future = self.loop.create_future()
                self.notify_response = bytearray()
                self._response_completion_scheduled = False

                # Make request
                if on_attempt is not None:
                    on_attempt()
                await self.client.write_gatt_char(
                    self.WRITE_UUID,
                    bytes(self.current_command))

                # Wait for response
                res = await asyncio.wait_for(
                    self.notify_future,
                    timeout=policy.timeout)
                if cmd_future and not cmd_future.done():
                    cmd_future.set_result(res)

                # Success!
                self.state = ClientState.READY
                break
            except ParseError as err:
                last_error = err
                self.state = ClientState.COMMAND_ERROR_WAIT
                if attempts < policy.max_attempts:
                    await asyncio.sleep(policy.timeout)
            except asyncio.TimeoutError as err:
                if self.notify_response:
                    last_error = ParseError('Incomplete response')
                else:
                    last_error = err
                self.state = ClientState.COMMAND_ERROR_WAIT
            except ModbusError as err:
                if cmd_future and not cmd_future.done():
                    cmd_future.set_exception(err)

                # Don't retry
                self.state = ClientState.READY
                break
            except (BleakError, EOFError, BadConnectionError) as err:
                if cmd_future and not cmd_future.done():
                    cmd_future.set_exception(err)

                self.state = ClientState.DISCONNECTING
                break

        if attempts == policy.max_attempts and self.state == ClientState.COMMAND_ERROR_WAIT:
            err = last_error or BadConnectionError('too many retries')
            if cmd_future and not cmd_future.done():
                cmd_future.set_exception(err)
            self.state = ClientState.DISCONNECTING

        self.command_queue.task_done()

    async def _disconnect(self):
        await self.client.disconnect()
        logging.warn(f'Delayed reconnect to {self.address} after error')
        await asyncio.sleep(5)
        self.state = ClientState.NOT_CONNECTED

    def _notification_handler(self, _sender: int, data: bytearray):
        # Ignore notifications we don't expect
        if not self.notify_future or self.notify_future.done():
            return

        # If something went wrong, we might get weird data.
        if data == b'AT+NAME?\r' or data == b'AT+ADV?\r':
            err = BadConnectionError('Got AT+ notification')
            self.notify_future.set_exception(err)
            return

        # Save data
        self.notify_response.extend(data)

        response_size = len(self.notify_response)
        is_exception = (
            response_size >= 2
            and self.notify_response[1] == self.current_command.function_code + 0x80
        )
        expected_size = 5 if is_exception else self.current_command.response_size()

        if response_size > expected_size:
            self.notify_future.set_exception(ParseError('Invalid response length'))
            return

        if response_size == expected_size and not self._response_completion_scheduled:
            self._response_completion_scheduled = True
            self.loop.call_later(self.RESPONSE_QUIET_WINDOW, self._finalize_response)

    def _finalize_response(self):
        if not self.notify_future or self.notify_future.done():
            return
        is_exception = (
            len(self.notify_response) >= 2
            and self.notify_response[1] == self.current_command.function_code + 0x80
        )
        expected_size = 5 if is_exception else self.current_command.response_size()
        if len(self.notify_response) != expected_size:
            self.notify_future.set_exception(ParseError('Invalid response length'))
        elif is_exception and self.current_command.is_exception_response(self.notify_response):
            msg = f'MODBUS Exception {self.current_command}: {self.notify_response[2]}'
            self.notify_future.set_exception(ModbusError(msg))
        elif is_exception:
            self.notify_future.set_exception(ParseError('Invalid MODBUS exception response'))
        elif self.current_command.is_valid_response(self.notify_response):
            self.notify_future.set_result(self.notify_response)
        else:
            self.notify_future.set_exception(ParseError('Invalid response'))
