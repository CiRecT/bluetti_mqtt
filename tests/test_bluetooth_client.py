import asyncio

import pytest

from bluetti_mqtt.bluetooth import ConnectionChangedError, ParseError
from bluetti_mqtt.bluetooth.client import BluetoothClient
from bluetti_mqtt.core import WriteSingleRegister
from bluetti_mqtt.core.devices.capabilities import ExecutionPolicy


@pytest.mark.asyncio
async def test_overlong_write_response_fails_immediately():
    client = object.__new__(BluetoothClient)
    client.current_command = WriteSingleRegister(3019, 5)
    client.notify_future = asyncio.get_running_loop().create_future()
    client.notify_response = bytearray()

    client._notification_handler(1, bytearray(bytes(client.current_command) + b'\x00'))

    with pytest.raises(ParseError, match='length'):
        await client.notify_future


@pytest.mark.asyncio
async def test_no_retry_policy_performs_one_attempt_on_timeout(monkeypatch):
    class FakeGattClient:
        def __init__(self):
            self.writes = []

        async def write_gatt_char(self, uuid, command):
            self.writes.append((uuid, command))

    async def immediate_timeout(awaitable, timeout):
        assert timeout == 5
        awaitable.cancel()
        raise asyncio.TimeoutError

    client = object.__new__(BluetoothClient)
    client.loop = asyncio.get_running_loop()
    client.command_queue = asyncio.Queue()
    client.client = FakeGattClient()
    client.connection_generation = 1
    command = WriteSingleRegister(3019, 5)
    policy = ExecutionPolicy(timeout=5, max_attempts=1, minimum_update_interval=10)
    monkeypatch.setattr('bluetti_mqtt.bluetooth.client.asyncio.wait_for', immediate_timeout)

    result_future = await client.perform(command, policy)
    await client._perform_command()

    with pytest.raises(asyncio.TimeoutError):
        await result_future
    assert len(client.client.writes) == 1


@pytest.mark.asyncio
async def test_partial_response_is_invalid_instead_of_plain_timeout(monkeypatch):
    class PartialGattClient:
        async def write_gatt_char(self, uuid, command):
            client._notification_handler(1, bytearray(command[:4]))

    async def immediate_timeout(awaitable, timeout):
        assert timeout == 5
        awaitable.cancel()
        raise asyncio.TimeoutError

    client = object.__new__(BluetoothClient)
    client.loop = asyncio.get_running_loop()
    client.command_queue = asyncio.Queue()
    client.client = PartialGattClient()
    client.connection_generation = 1
    command = WriteSingleRegister(3019, 5)
    policy = ExecutionPolicy(timeout=5, max_attempts=1, minimum_update_interval=10)
    monkeypatch.setattr('bluetti_mqtt.bluetooth.client.asyncio.wait_for', immediate_timeout)

    result_future = await client.perform(command, policy)
    await client._perform_command()

    with pytest.raises(ParseError, match='Incomplete'):
        await result_future


@pytest.mark.asyncio
async def test_no_retry_command_cannot_survive_reconnect():
    class FakeGattClient:
        def __init__(self):
            self.writes = []

        async def write_gatt_char(self, uuid, command):
            self.writes.append((uuid, command))

    client = object.__new__(BluetoothClient)
    client.loop = asyncio.get_running_loop()
    client.command_queue = asyncio.Queue()
    client.client = FakeGattClient()
    client.connection_generation = 1
    command = WriteSingleRegister(3019, 5)
    policy = ExecutionPolicy(
        timeout=5,
        max_attempts=1,
        minimum_update_interval=10,
        dispatch_timeout=5,
        requires_same_connection=True,
    )

    result_future = await client.perform(command, policy)
    client.connection_generation = 2
    await client._perform_command()

    with pytest.raises(ConnectionChangedError, match='expired after reconnect'):
        await result_future
    assert client.client.writes == []


@pytest.mark.asyncio
async def test_fragmented_overlong_response_is_rejected_before_completion():
    client = object.__new__(BluetoothClient)
    client.loop = asyncio.get_running_loop()
    client.current_command = WriteSingleRegister(3019, 5)
    client.notify_future = client.loop.create_future()
    client.notify_response = bytearray()
    client._response_completion_scheduled = False
    response = bytes(client.current_command)

    client._notification_handler(1, bytearray(response))
    await asyncio.sleep(0)
    client._notification_handler(1, bytearray(b'\x00'))

    with pytest.raises(ParseError, match='length'):
        await client.notify_future
