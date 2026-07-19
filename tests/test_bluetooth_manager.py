from types import SimpleNamespace

import pytest

from bluetti_mqtt.bluetooth.manager import MultiDeviceManager


@pytest.mark.asyncio
async def test_manager_passes_advertised_name_to_bluetooth_client(monkeypatch):
    created_clients = []

    class FakeScanner:
        @staticmethod
        async def discover():
            return [
                SimpleNamespace(address='A', name='AC300123'),
                SimpleNamespace(address='OTHER', name='AC500456'),
            ]

    class FakeBluetoothClient:
        def __init__(self, address, name=None):
            created_clients.append((address, name))

        async def run(self):
            pass

    monkeypatch.setattr('bluetti_mqtt.bluetooth.manager.BleakScanner', FakeScanner)
    monkeypatch.setattr('bluetti_mqtt.bluetooth.manager.BluetoothClient', FakeBluetoothClient)

    await MultiDeviceManager(['A']).run()

    assert created_clients == [('A', 'AC300123')]
