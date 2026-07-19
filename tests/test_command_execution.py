import asyncio

import pytest
from bleak import BleakError

from bluetti_mqtt.bluetooth import (
    BadConnectionError,
    ConnectionChangedError,
    DispatchTimeoutError,
    ModbusError,
    ParseError,
)
from bluetti_mqtt.bluetooth.client import BluetoothClient
from bluetti_mqtt.command import (
    CommandError,
    CommandExecutor,
    CommandResult,
    CommandStatus,
    parse_public_command,
)
from bluetti_mqtt.core.devices.ac300 import AC300
from bluetti_mqtt.mqtt_client import GRID_CHARGING_CURRENT_FIELD, NORMAL_DEVICE_FIELDS


class FakeManager:
    def __init__(self, outcome=None, ready=True):
        self.outcome = outcome
        self.ready = ready
        self.attempts = []

    def is_ready(self, address):
        return self.ready

    async def perform(self, address, command, policy=None, on_attempt=None):
        self.attempts.append((address, command, policy))
        if on_attempt is not None:
            on_attempt()
        future = asyncio.get_running_loop().create_future()
        if isinstance(self.outcome, BaseException):
            future.set_exception(self.outcome)
        else:
            future.set_result(self.outcome)
        return future


def request_for(device, field='grid_charge_on', payload=b'ON'):
    field_configs = dict(NORMAL_DEVICE_FIELDS)
    field_configs['grid_charging_current_limit'] = GRID_CHARGING_CURRENT_FIELD
    return parse_public_command(
        f'bluetti/command/{device.type}-{device.sn}/{field}',
        payload,
        [device],
        field_configs,
    )


@pytest.mark.asyncio
async def test_valid_acknowledgement_produces_applied_result():
    device = AC300('A', '123')
    request = request_for(device)
    manager = FakeManager(bytes(request.command))

    result = await CommandExecutor(manager).execute(request)

    assert result == CommandResult(
        'AC300-123',
        'grid_charge_on',
        CommandStatus.APPLIED,
        value=True,
    )
    assert len(manager.attempts) == 1


@pytest.mark.asyncio
async def test_unavailable_device_is_rejected_without_attempt():
    device = AC300('A', '123')
    manager = FakeManager(ready=False)

    result = await CommandExecutor(manager).execute(request_for(device))

    assert result.status == CommandStatus.REJECTED
    assert result.error == CommandError.DEVICE_UNAVAILABLE
    assert manager.attempts == []


@pytest.mark.asyncio
async def test_mismatched_response_is_failed():
    device = AC300('A', '123')
    manager = FakeManager(bytes.fromhex('01060bc300003a71'))

    result = await CommandExecutor(manager).execute(request_for(device))

    assert result.status == CommandStatus.FAILED
    assert result.error == CommandError.INVALID_RESPONSE


@pytest.mark.asyncio
@pytest.mark.parametrize(('exception', 'error'), [
    (asyncio.TimeoutError(), CommandError.DEVICE_TIMEOUT),
    (ParseError('bad frame'), CommandError.INVALID_RESPONSE),
    (ModbusError('exception response'), CommandError.MODBUS_ERROR),
    (BleakError('BLE failure'), CommandError.TRANSPORT_ERROR),
    (BadConnectionError('connection failure'), CommandError.TRANSPORT_ERROR),
    (RuntimeError('bug'), CommandError.INTERNAL_ERROR),
])
async def test_attempt_failures_use_stable_error_codes(exception, error):
    device = AC300('A', '123')

    result = await CommandExecutor(FakeManager(exception)).execute(request_for(device))

    assert result.status == CommandStatus.FAILED
    assert result.error == error
    assert result.value is True


@pytest.mark.asyncio
@pytest.mark.parametrize(('exception', 'error'), [
    (DispatchTimeoutError('expired before dispatch'), CommandError.DEVICE_TIMEOUT),
    (ConnectionChangedError('reconnected before dispatch'), CommandError.DEVICE_UNAVAILABLE),
])
async def test_pre_dispatch_failures_are_rejected_without_an_attempt(exception, error):
    device = AC300('A', '123')
    manager = FakeManager(exception)

    result = await CommandExecutor(manager).execute(request_for(device))

    assert result.status == CommandStatus.REJECTED
    assert result.error == error
    assert result.value is True


@pytest.mark.asyncio
async def test_reconnected_queued_command_is_rejected_without_a_gatt_write():
    class FakeGattClient:
        def __init__(self):
            self.writes = []

        async def write_gatt_char(self, uuid, command):
            self.writes.append((uuid, command))

    class ReconnectedManager:
        def __init__(self):
            self.client = object.__new__(BluetoothClient)
            self.client.loop = asyncio.get_running_loop()
            self.client.command_queue = asyncio.Queue()
            self.client.client = FakeGattClient()
            self.client.connection_generation = 1

        def is_ready(self, address):
            return True

        async def perform(self, address, command, policy=None, on_attempt=None):
            future = await self.client.perform(command, policy, on_attempt)
            self.client.connection_generation += 1
            await self.client._perform_command()
            return future

    device = AC300('A', '123')
    manager = ReconnectedManager()

    result = await CommandExecutor(manager).execute(request_for(
        device,
        field='grid_charging_current_limit',
        payload=b'5',
    ))

    assert result.status == CommandStatus.REJECTED
    assert result.error == CommandError.DEVICE_UNAVAILABLE
    assert manager.client.client.writes == []
