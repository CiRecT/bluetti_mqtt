import asyncio
from dataclasses import dataclass
import json

import pytest

from bluetti_mqtt.bus import EventBus
from bluetti_mqtt.command import CommandExecutor
from bluetti_mqtt.core.devices.ac300 import AC300
from bluetti_mqtt.device_handler import DeviceHandler
from bluetti_mqtt.mqtt_client import MQTTClient
from tests.fakes import FakeMQTTClient


@dataclass
class IncomingMessage:
    topic: str
    payload: bytes
    retain: bool = False


class OutcomeManager:
    def __init__(self, outcome=None):
        self.attempts = []
        self.outcome = outcome

    def is_ready(self, address):
        return True

    async def perform(self, address, command, policy=None, on_attempt=None):
        self.attempts.append((address, bytes(command), policy))
        if on_attempt is not None:
            on_attempt()
        future = asyncio.get_running_loop().create_future()
        outcome = bytes(command) if self.outcome is None else self.outcome
        if isinstance(outcome, BaseException):
            future.set_exception(outcome)
        else:
            future.set_result(outcome)
        return future


@pytest.mark.asyncio
async def test_mqtt_to_acknowledged_state_flow_uses_only_fakes():
    bus = EventBus()
    manager = OutcomeManager()
    handler = DeviceHandler(
        ['A'],
        0,
        bus,
        minimum_update_intervals={('A', 'grid_charging_current_limit'): 10},
    )
    handler.manager = manager
    handler.command_executor = CommandExecutor(manager)
    bus.add_public_command_listener(handler.handle_public_command)

    mqtt = MQTTClient(bus, 'unused-broker', 'normal', grid_charging_addresses={'A'})
    mqtt.devices = [AC300('A', '123')]
    publications = FakeMQTTClient()
    result_published = asyncio.Event()

    async def publish_result(message):
        await mqtt._handle_result(publications, message)
        result_published.set()

    bus.add_command_result_listener(publish_result)
    bus_task = asyncio.create_task(bus.run())

    await mqtt._handle_command(IncomingMessage(
        'bluetti/command/AC300-123/grid_charging_current_limit',
        b'5',
    ))
    await result_published.wait()

    assert manager.attempts[0][1] == bytes.fromhex('01060bcb00053a13')
    result = next(item for item in publications.publications if item.topic.startswith('bluetti/result/'))
    state = next(item for item in publications.publications if item.topic.startswith('bluetti/state/'))
    assert json.loads(result.payload) == {'status': 'applied', 'cached': False, 'value': 5}
    assert result.qos == 1
    assert result.retain is False
    assert state.payload == b'5'
    assert state.retain is False

    bus_task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await bus_task


@pytest.mark.asyncio
async def test_timeout_flows_to_failed_result_without_state_or_retry():
    bus = EventBus()
    manager = OutcomeManager(asyncio.TimeoutError())
    handler = DeviceHandler(['A'], 0, bus)
    handler.manager = manager
    handler.command_executor = CommandExecutor(manager)
    bus.add_public_command_listener(handler.handle_public_command)

    mqtt = MQTTClient(bus, 'unused-broker', 'normal', grid_charging_addresses={'A'})
    mqtt.devices = [AC300('A', '123')]
    publications = FakeMQTTClient()
    result_published = asyncio.Event()

    async def publish_result(message):
        await mqtt._handle_result(publications, message)
        result_published.set()

    bus.add_command_result_listener(publish_result)
    bus_task = asyncio.create_task(bus.run())
    await mqtt._handle_command(IncomingMessage(
        'bluetti/command/AC300-123/grid_charging_current_limit',
        b'5',
    ))
    await result_published.wait()

    result = next(item for item in publications.publications if item.topic.startswith('bluetti/result/'))
    assert json.loads(result.payload) == {
        'status': 'failed',
        'cached': False,
        'value': 5,
        'error': 'device_timeout',
    }
    assert len(manager.attempts) == 1
    assert all(not item.topic.startswith('bluetti/state/') for item in publications.publications)

    bus_task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await bus_task
