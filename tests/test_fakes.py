import asyncio

import pytest

from bluetti_mqtt.bluetooth import BadConnectionError, ModbusError, ParseError
from bluetti_mqtt.core import WriteSingleRegister
from tests.fakes import FakeBLEAdapter, FakeClock, FakeMQTTClient


@pytest.mark.asyncio
async def test_fake_mqtt_records_publications_and_subscriptions():
    mqtt = FakeMQTTClient()

    await mqtt.subscribe('bluetti/command/#', qos=1)
    await mqtt.publish('bluetti/result/AC300-123/field', '{}', qos=1, retain=False)

    assert mqtt.subscriptions == [('bluetti/command/#', 1)]
    assert mqtt.publications[0].qos == 1
    assert mqtt.publications[0].retain is False


@pytest.mark.asyncio
@pytest.mark.parametrize('error', [
    asyncio.TimeoutError(),
    ParseError('bad response'),
    ModbusError('device exception'),
    BadConnectionError('transport failed'),
])
async def test_fake_ble_exposes_protocol_and_transport_outcomes(error):
    ble = FakeBLEAdapter()
    command = WriteSingleRegister(3019, 5)
    ble.fail_with(error)

    with pytest.raises(type(error)):
        await ble.perform('AA:BB', command)

    assert ble.requests == [('AA:BB', command)]


@pytest.mark.asyncio
async def test_fake_ble_exposes_successful_response():
    ble = FakeBLEAdapter()
    command = WriteSingleRegister(3019, 5)
    response = bytes.fromhex('01060bcb00053a13')
    ble.succeed_with(response)

    assert await ble.perform('AA:BB', command) == response


def test_fake_clock_advances_without_real_sleep():
    clock = FakeClock(initial=4.5)

    clock.advance(5.5)

    assert clock.monotonic() == 10.0
