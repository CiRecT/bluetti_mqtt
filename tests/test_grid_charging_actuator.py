import json
from dataclasses import dataclass

import pytest

from bluetti_mqtt.bus import CommandResultMessage, EventBus, PublicCommandMessage
from bluetti_mqtt.command import CommandError, CommandResult, CommandStatus
from bluetti_mqtt.core.devices.ac300 import AC300
from bluetti_mqtt.mqtt_client import MQTTClient
from tests.fakes import FakeMQTTClient


@dataclass
class IncomingMessage:
    topic: str
    payload: bytes
    retain: bool = False


def enabled_client(bus=None):
    return MQTTClient(
        bus or EventBus(),
        'broker',
        'normal',
        grid_charging_addresses={'A'},
    )


def test_actuator_is_public_only_for_explicitly_enabled_address():
    enabled = enabled_client()
    disabled = MQTTClient(EventBus(), 'broker', 'normal')
    ac300 = AC300('A', '123')

    assert 'grid_charging_current_limit' in enabled._field_configs_for_device(ac300)
    assert 'grid_charging_current_limit' not in disabled._field_configs_for_device(ac300)


@pytest.mark.asyncio
@pytest.mark.parametrize(('payload', 'error'), [
    (b'1', None),
    (b'5', None),
    (b'10', None),
    (b'0', CommandError.OUT_OF_RANGE),
    (b'11', CommandError.OUT_OF_RANGE),
    (b'5.0', CommandError.INVALID_PAYLOAD),
    (b'5A', CommandError.INVALID_PAYLOAD),
    (b'{}', CommandError.INVALID_PAYLOAD),
    (b'', CommandError.INVALID_PAYLOAD),
])
async def test_current_limit_payload_matrix(payload, error):
    bus = EventBus()
    mqtt = enabled_client(bus)
    mqtt.devices = [AC300('A', '123')]
    message = IncomingMessage('bluetti/command/AC300-123/grid_charging_current_limit', payload)

    await mqtt._handle_command(message)
    queued = await bus.queue.get()

    if error is None:
        assert isinstance(queued, PublicCommandMessage)
        assert queued.request.value == int(payload)
    else:
        assert isinstance(queued, CommandResultMessage)
        assert queued.result.error == error


@pytest.mark.asyncio
async def test_retained_current_limit_is_rejected_before_dispatch():
    bus = EventBus()
    mqtt = enabled_client(bus)
    mqtt.devices = [AC300('A', '123')]
    message = IncomingMessage(
        'bluetti/command/AC300-123/grid_charging_current_limit',
        b'5',
        retain=True,
    )

    await mqtt._handle_command(message)
    queued = await bus.queue.get()

    assert isinstance(queued, CommandResultMessage)
    assert queued.result.error == CommandError.RETAINED_COMMAND_NOT_ALLOWED
    assert queued.result.value == 5


@pytest.mark.asyncio
async def test_applied_current_limit_publishes_nonretained_acknowledged_state():
    mqtt = enabled_client()
    client = FakeMQTTClient()
    result = CommandResult(
        'AC300-123',
        'grid_charging_current_limit',
        CommandStatus.APPLIED,
        value=5,
    )

    await mqtt._handle_result(client, CommandResultMessage(result))

    state = next(item for item in client.publications if item.topic.startswith('bluetti/state/'))
    assert state.topic == 'bluetti/state/AC300-123/grid_charging_current_limit'
    assert state.payload == b'5'
    assert state.retain is False


@pytest.mark.asyncio
async def test_failed_current_limit_does_not_publish_acknowledged_state():
    mqtt = enabled_client()
    client = FakeMQTTClient()
    result = CommandResult(
        'AC300-123',
        'grid_charging_current_limit',
        CommandStatus.FAILED,
        value=5,
        error=CommandError.DEVICE_TIMEOUT,
    )

    await mqtt._handle_result(client, CommandResultMessage(result))

    assert all(not item.topic.startswith('bluetti/state/') for item in client.publications)


@pytest.mark.asyncio
async def test_home_assistant_number_has_current_constraints_and_no_initial_state():
    mqtt = enabled_client()
    client = FakeMQTTClient()

    await mqtt._init_device(AC300('A', '123'), client)

    discovery = next(
        item for item in client.publications
        if item.topic == 'homeassistant/number/123_grid_charging_current_limit/config'
    )
    payload = json.loads(discovery.payload)
    assert payload['command_topic'] == 'bluetti/command/AC300-123/grid_charging_current_limit'
    assert payload['state_topic'] == 'bluetti/state/AC300-123/grid_charging_current_limit'
    assert payload['min'] == 1
    assert payload['max'] == 10
    assert payload['step'] == 1
    assert payload['unit_of_measurement'] == 'A'
    assert all(
        item.topic != 'bluetti/state/AC300-123/grid_charging_current_limit'
        for item in client.publications
    )
