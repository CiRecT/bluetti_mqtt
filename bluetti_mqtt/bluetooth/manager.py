import asyncio
import logging
from typing import Callable, Dict, List
from bleak import BleakScanner
from bluetti_mqtt.core import DeviceCommand
from bluetti_mqtt.core.devices.capabilities import ExecutionPolicy
from .client import BluetoothClient


class MultiDeviceManager:
    clients: Dict[str, BluetoothClient]

    def __init__(self, addresses: List[str]):
        self.addresses = addresses
        self.clients = {}

    async def run(self):
        logging.info(f'Connecting to clients: {self.addresses}')

        # Perform a blocking scan just to speed up initial connect
        discovered_devices = await BleakScanner.discover()
        advertised_names = {
            device.address.casefold(): device.name
            for device in discovered_devices
            if device.name
        }

        # Start client loops
        self.clients = {
            address: BluetoothClient(address, advertised_names.get(address.casefold()))
            for address in self.addresses
        }
        await asyncio.gather(*[c.run() for c in self.clients.values()])

    def is_ready(self, address: str):
        if address in self.clients:
            return self.clients[address].is_ready
        else:
            return False

    def get_name(self, address: str):
        if address in self.clients:
            return self.clients[address].name
        else:
            raise Exception('Unknown address')

    async def perform(
        self,
        address: str,
        command: DeviceCommand,
        policy: ExecutionPolicy = None,
        on_attempt: Callable[[], None] = None,
    ):
        if address in self.clients:
            return await self.clients[address].perform(command, policy, on_attempt)
        else:
            raise Exception('Unknown address')

    async def perform_nowait(
        self,
        address: str,
        command: DeviceCommand,
        policy: ExecutionPolicy = None,
        on_attempt: Callable[[], None] = None,
    ):
        if address in self.clients:
            await self.clients[address].perform_nowait(command, policy, on_attempt)
        else:
            raise Exception('Unknown address')
