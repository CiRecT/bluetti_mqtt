import json

import pytest

from bluetti_mqtt.bus import CommandResultMessage, EventBus
from bluetti_mqtt.command import CommandError, CommandResult, CommandStatus
from bluetti_mqtt.mqtt_client import MQTTClient
from tests.fakes import FakeMQTTClient


@pytest.mark.asyncio
async def test_result_publication_uses_stable_json_qos_one_and_no_retain():
    mqtt = MQTTClient(EventBus(), 'broker', 'none')
    client = FakeMQTTClient()
    result = CommandResult(
        'AC300-123',
        'grid_charging_current_limit',
        CommandStatus.REJECTED,
        cached=False,
        value=11,
        error=CommandError.OUT_OF_RANGE,
    )

    await mqtt._handle_result(client, CommandResultMessage(result))

    publication = client.publications[0]
    assert publication.topic == 'bluetti/result/AC300-123/grid_charging_current_limit'
    assert json.loads(publication.payload) == {
        'status': 'rejected',
        'cached': False,
        'value': 11,
        'error': 'out_of_range',
    }
    assert publication.qos == 1
    assert publication.retain is False


@pytest.mark.asyncio
async def test_unparseable_value_is_omitted_from_result_json():
    mqtt = MQTTClient(EventBus(), 'broker', 'none')
    client = FakeMQTTClient()
    result = CommandResult.rejected(
        'AC300-123',
        'grid_charging_current_limit',
        CommandError.INVALID_PAYLOAD,
    )

    await mqtt._handle_result(client, CommandResultMessage(result))

    assert json.loads(client.publications[0].payload) == {
        'status': 'rejected',
        'cached': False,
        'error': 'invalid_payload',
    }


def test_event_bus_listeners_are_not_duplicated_on_mqtt_reconnect():
    bus = EventBus()
    mqtt = MQTTClient(bus, 'broker', 'none')

    mqtt._connect_bus()
    mqtt._connect_bus()

    assert bus.parser_listeners == [mqtt.handle_message]
    assert bus.command_result_listeners == [mqtt.handle_message]
