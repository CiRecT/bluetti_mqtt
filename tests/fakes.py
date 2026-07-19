import asyncio
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from bluetti_mqtt.core import DeviceCommand


@dataclass(frozen=True)
class PublishedMessage:
    topic: str
    payload: str
    qos: int
    retain: bool


class FakeMQTTClient:
    def __init__(self):
        self.publications: List[PublishedMessage] = []
        self.subscriptions: List[tuple[str, int]] = []

    async def publish(self, topic: str, payload: str, qos: int = 0, retain: bool = False):
        self.publications.append(PublishedMessage(topic, payload, qos, retain))

    async def subscribe(self, topic: str, qos: int = 0):
        self.subscriptions.append((topic, qos))


class FakeBLEAdapter:
    def __init__(self):
        self.requests: List[tuple[str, DeviceCommand]] = []
        self._outcomes: asyncio.Queue = asyncio.Queue()

    def succeed_with(self, response: bytes):
        self._outcomes.put_nowait(response)

    def fail_with(self, error: Exception):
        self._outcomes.put_nowait(error)

    async def perform(self, address: str, command: DeviceCommand) -> bytes:
        self.requests.append((address, command))
        outcome = await self._outcomes.get()
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


class FakeClock:
    def __init__(self, initial: float = 0.0):
        self._now = initial

    def monotonic(self) -> float:
        return self._now

    def advance(self, seconds: float):
        if seconds < 0:
            raise ValueError('clock cannot move backwards')
        self._now += seconds


class FakeEnvironment:
    def __init__(self, values: Optional[Dict[str, str]] = None):
        self.values = values or {}

    def get(self, name: str) -> Optional[str]:
        return self.values.get(name)


class ControlledOutcome:
    def __init__(self):
        self.started = asyncio.Event()
        self._future: Optional[asyncio.Future] = None

    async def wait(self) -> Any:
        self.started.set()
        if self._future is None:
            self._future = asyncio.get_running_loop().create_future()
        return await self._future

    def resolve(self, value: Any):
        if self._future is None:
            raise RuntimeError('outcome has not started')
        self._future.set_result(value)

    def reject(self, error: Exception):
        if self._future is None:
            raise RuntimeError('outcome has not started')
        self._future.set_exception(error)
