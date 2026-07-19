import asyncio

import pytest

from bluetti_mqtt.bus import EventBus, ParserMessage
from bluetti_mqtt.core.devices.ac300 import AC300


@pytest.mark.asyncio
async def test_event_bus_delivers_parser_messages_and_remains_cancellable():
    bus = EventBus()
    received = []

    async def listener(message):
        received.append(message)

    bus.add_parser_listener(listener)
    task = asyncio.create_task(bus.run())
    message = ParserMessage(AC300('AA:BB', '1234'), {'ac_input_power': 900})

    await bus.put(message)
    await bus.queue.join()

    assert received == [message]

    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
