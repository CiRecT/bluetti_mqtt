import asyncio
from dataclasses import replace

import pytest

from bluetti_mqtt.bus import EventBus, ParserMessage, PublicCommandMessage
from bluetti_mqtt.command import CommandError, CommandExecutor, CommandRequest, CommandStatus
from bluetti_mqtt.core.devices.ac300 import AC300
from bluetti_mqtt.device_handler import DeviceHandler
from tests.fakes import ControlledOutcome


class BlockingManager:
    def __init__(self, outcome):
        self.outcome = outcome
        self.commands = []

    def is_ready(self, address):
        return True

    async def perform(self, address, command, policy=None, on_attempt=None):
        self.commands.append(command)
        if on_attempt is not None:
            on_attempt()
        future = asyncio.get_running_loop().create_future()

        async def complete():
            future.set_result(await self.outcome.wait())

        asyncio.create_task(complete())
        return future


@pytest.mark.asyncio
async def test_inflight_ble_command_does_not_block_other_bus_messages():
    bus = EventBus()
    device = AC300('A', '123')
    command = device.build_setter_command('grid_charging_current_limit', 5)
    request = CommandRequest(
        device,
        'AC300-123',
        'grid_charging_current_limit',
        5,
        command,
        device.get_command_policy('grid_charging_current_limit'),
    )
    outcome = ControlledOutcome()
    manager = BlockingManager(outcome)
    handler = DeviceHandler(['A'], 0, bus)
    handler.command_executor = CommandExecutor(manager)
    bus.add_public_command_listener(handler.handle_public_command)
    parser_received = asyncio.Event()

    async def receive_parser(message):
        parser_received.set()

    bus.add_parser_listener(receive_parser)
    bus_task = asyncio.create_task(bus.run())

    await bus.put(PublicCommandMessage(request))
    await outcome.started.wait()
    await bus.put(ParserMessage(device, {'ac_input_power': 1}))
    await parser_received.wait()

    outcome.resolve(bytes(command))
    await asyncio.gather(*list(handler.public_command_tasks))
    bus_task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await bus_task


@pytest.mark.asyncio
async def test_dispatch_deadline_includes_wait_for_another_device_command():
    device = AC300('A', '123')
    blocking_command = device.build_setter_command('grid_charge_on', True)
    blocking_request = CommandRequest(
        device,
        'AC300-123',
        'grid_charge_on',
        True,
        blocking_command,
        device.get_command_policy('grid_charge_on'),
    )
    current_command = device.build_setter_command('grid_charging_current_limit', 5)
    current_policy = replace(
        device.get_command_policy('grid_charging_current_limit'),
        dispatch_timeout=0.01,
    )
    current_request = CommandRequest(
        device,
        'AC300-123',
        'grid_charging_current_limit',
        5,
        current_command,
        current_policy,
    )
    outcome = ControlledOutcome()
    manager = BlockingManager(outcome)
    executor = CommandExecutor(manager)

    blocking_task = asyncio.create_task(executor.execute(blocking_request))
    await outcome.started.wait()
    current_result = await executor.execute(current_request)

    assert current_result.status == CommandStatus.REJECTED
    assert current_result.error == CommandError.DEVICE_TIMEOUT
    assert manager.commands == [blocking_command]

    outcome.resolve(bytes(blocking_command))
    await blocking_task
