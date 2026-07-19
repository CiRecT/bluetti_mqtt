import asyncio

import pytest

from bluetti_mqtt.command import (
    CommandError,
    CommandExecutor,
    CommandRequest,
    CommandStatus,
    parse_public_command,
)
from bluetti_mqtt.core.devices.ac300 import AC300
from bluetti_mqtt.mqtt_client import NORMAL_DEVICE_FIELDS
from tests.fakes import ControlledOutcome, FakeClock


class RateManager:
    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.attempts = []

    def is_ready(self, address):
        return True

    async def perform(self, address, command, policy=None, on_attempt=None):
        self.attempts.append((address, command, policy))
        if on_attempt is not None:
            on_attempt()
        outcome = self.outcomes.pop(0)
        future = asyncio.get_running_loop().create_future()
        if isinstance(outcome, ControlledOutcome):
            async def resolve_later():
                try:
                    result = await outcome.wait()
                    if not future.done():
                        future.set_result(result)
                except Exception as error:
                    if not future.done():
                        future.set_exception(error)
            asyncio.create_task(resolve_later())
        else:
            future.set_result(outcome)
        return future


def current_request(device, value):
    return CommandRequest(
        device=device,
        device_id=f'{device.type}-{device.sn}',
        field='grid_charging_current_limit',
        value=value,
        command=device.build_setter_command('grid_charging_current_limit', value),
        policy=device.get_command_policy('grid_charging_current_limit'),
    )


@pytest.mark.asyncio
async def test_completed_duplicate_replays_cached_result_without_ble_attempt():
    device = AC300('A', '123')
    request = current_request(device, 5)
    manager = RateManager([bytes(request.command)])
    executor = CommandExecutor(manager, clock=FakeClock().monotonic)

    first = await executor.execute(request)
    duplicate = await executor.execute(request)

    assert first.status == CommandStatus.APPLIED
    assert first.cached is False
    assert duplicate.status == CommandStatus.APPLIED
    assert duplicate.cached is True
    assert len(manager.attempts) == 1


@pytest.mark.asyncio
async def test_different_value_inside_interval_is_rejected_and_not_delayed():
    device = AC300('A', '123')
    first = current_request(device, 5)
    manager = RateManager([bytes(first.command)])
    executor = CommandExecutor(manager, clock=FakeClock().monotonic)

    await executor.execute(first)
    result = await executor.execute(current_request(device, 6))

    assert result.status == CommandStatus.REJECTED
    assert result.error == CommandError.RATE_LIMITED
    assert result.value == 6
    assert len(manager.attempts) == 1


@pytest.mark.asyncio
async def test_exact_interval_boundary_allows_next_attempt():
    device = AC300('A', '123')
    first = current_request(device, 5)
    second = current_request(device, 6)
    clock = FakeClock()
    manager = RateManager([bytes(first.command), bytes(second.command)])
    executor = CommandExecutor(manager, clock=clock.monotonic)

    await executor.execute(first)
    clock.advance(10)
    result = await executor.execute(second)

    assert result.status == CommandStatus.APPLIED
    assert len(manager.attempts) == 2


@pytest.mark.asyncio
async def test_rate_limit_is_isolated_per_device():
    first_device = AC300('A', '123')
    second_device = AC300('B', '456')
    first = current_request(first_device, 5)
    second = current_request(second_device, 6)
    manager = RateManager([bytes(first.command), bytes(second.command)])
    executor = CommandExecutor(manager, clock=FakeClock().monotonic)

    assert (await executor.execute(first)).status == CommandStatus.APPLIED
    assert (await executor.execute(second)).status == CommandStatus.APPLIED


@pytest.mark.asyncio
async def test_identical_inflight_duplicate_joins_one_attempt():
    device = AC300('A', '123')
    request = current_request(device, 5)
    outcome = ControlledOutcome()
    manager = RateManager([outcome])
    executor = CommandExecutor(manager, clock=FakeClock().monotonic)

    first_task = asyncio.create_task(executor.execute(request))
    await outcome.started.wait()
    duplicate_task = asyncio.create_task(executor.execute(request))
    await asyncio.sleep(0)
    outcome.resolve(bytes(request.command))

    first, duplicate = await asyncio.gather(first_task, duplicate_task)
    assert first.cached is False
    assert duplicate.cached is True
    assert len(manager.attempts) == 1


@pytest.mark.asyncio
async def test_different_inflight_value_is_rejected_immediately():
    device = AC300('A', '123')
    first = current_request(device, 5)
    outcome = ControlledOutcome()
    manager = RateManager([outcome])
    executor = CommandExecutor(manager, clock=FakeClock().monotonic)

    first_task = asyncio.create_task(executor.execute(first))
    await outcome.started.wait()
    result = await executor.execute(current_request(device, 6))

    assert result.error == CommandError.RATE_LIMITED
    assert len(manager.attempts) == 1
    outcome.resolve(bytes(first.command))
    await first_task


@pytest.mark.asyncio
async def test_configured_interval_can_increase_device_default():
    device = AC300('A', '123')
    first = current_request(device, 5)
    clock = FakeClock()
    manager = RateManager([bytes(first.command)])
    executor = CommandExecutor(
        manager,
        clock=clock.monotonic,
        minimum_update_intervals={('A', 'grid_charging_current_limit'): 30},
    )

    await executor.execute(first)
    clock.advance(10)
    result = await executor.execute(current_request(device, 6))

    assert result.error == CommandError.RATE_LIMITED


@pytest.mark.asyncio
async def test_old_value_is_not_replayed_after_a_newer_attempt():
    device = AC300('A', '123')
    five = current_request(device, 5)
    six = current_request(device, 6)
    clock = FakeClock()
    manager = RateManager([bytes(five.command), bytes(six.command)])
    executor = CommandExecutor(manager, clock=clock.monotonic)

    await executor.execute(five)
    clock.advance(10)
    await executor.execute(six)
    clock.advance(1)
    result = await executor.execute(five)

    assert result.status == CommandStatus.REJECTED
    assert result.error == CommandError.RATE_LIMITED
    assert result.cached is False
    assert len(manager.attempts) == 2


@pytest.mark.asyncio
async def test_current_interval_never_blocks_grid_charge_shutdown():
    device = AC300('A', '123')
    current = current_request(device, 5)
    shutdown = parse_public_command(
        'bluetti/command/AC300-123/grid_charge_on',
        b'OFF',
        [device],
        NORMAL_DEVICE_FIELDS,
    )
    manager = RateManager([bytes(current.command), bytes(shutdown.command)])
    executor = CommandExecutor(
        manager,
        clock=FakeClock().monotonic,
        minimum_update_intervals={('A', 'grid_charging_current_limit'): 30},
    )

    await executor.execute(current)
    result = await executor.execute(shutdown)

    assert result.status == CommandStatus.APPLIED
    assert len(manager.attempts) == 2


@pytest.mark.asyncio
async def test_interval_starts_at_transport_attempt_not_queue_time():
    class DelayedStartManager:
        def __init__(self):
            self.queued = asyncio.Event()
            self.future = None
            self.on_attempt = None

        def is_ready(self, address):
            return True

        async def perform(self, address, command, policy=None, on_attempt=None):
            self.future = asyncio.get_running_loop().create_future()
            self.command = command
            self.on_attempt = on_attempt
            self.queued.set()
            return self.future

        def start_and_acknowledge(self):
            self.on_attempt()
            self.future.set_result(bytes(self.command))

    device = AC300('A', '123')
    request = current_request(device, 5)
    clock = FakeClock()
    manager = DelayedStartManager()
    executor = CommandExecutor(manager, clock=clock.monotonic)

    task = asyncio.create_task(executor.execute(request))
    await manager.queued.wait()
    clock.advance(100)
    manager.start_and_acknowledge()
    await task
    clock.advance(9)

    result = await executor.execute(current_request(device, 6))

    assert result.error == CommandError.RATE_LIMITED


@pytest.mark.asyncio
async def test_cancelling_shared_attempt_cancels_joined_duplicate():
    device = AC300('A', '123')
    request = current_request(device, 5)
    outcome = ControlledOutcome()
    executor = CommandExecutor(RateManager([outcome]), clock=FakeClock().monotonic)

    first = asyncio.create_task(executor.execute(request))
    await outcome.started.wait()
    duplicate = asyncio.create_task(executor.execute(request))
    await asyncio.sleep(0)
    first.cancel()

    with pytest.raises(asyncio.CancelledError):
        await first
    with pytest.raises(asyncio.CancelledError):
        await duplicate
    outcome.resolve(bytes(request.command))
