import asyncio
from dataclasses import dataclass
import logging
from typing import Callable, List, Union
from bluetti_mqtt.command import CommandRequest, CommandResult
from bluetti_mqtt.core import BluettiDevice, DeviceCommand


@dataclass(frozen=True)
class ParserMessage:
    device: BluettiDevice
    parsed: dict


@dataclass(frozen=True)
class CommandMessage:
    device: BluettiDevice
    command: DeviceCommand


@dataclass(frozen=True)
class PublicCommandMessage:
    request: CommandRequest


@dataclass(frozen=True)
class CommandResultMessage:
    result: CommandResult


class EventBus:
    parser_listeners: List[Callable[[ParserMessage], None]]
    command_listeners: List[Callable[[CommandMessage], None]]
    public_command_listeners: List[Callable[[PublicCommandMessage], None]]
    command_result_listeners: List[Callable[[CommandResultMessage], None]]
    queue: asyncio.Queue

    def __init__(self):
        self.parser_listeners = []
        self.command_listeners = []
        self.public_command_listeners = []
        self.command_result_listeners = []
        self.queue = None

    def add_parser_listener(self, cb: Callable[[ParserMessage], None]):
        self.parser_listeners.append(cb)

    def add_command_listener(self, cb: Callable[[CommandMessage], None]):
        self.command_listeners.append(cb)

    def add_public_command_listener(self, cb: Callable[[PublicCommandMessage], None]):
        self.public_command_listeners.append(cb)

    def add_command_result_listener(self, cb: Callable[[CommandResultMessage], None]):
        self.command_result_listeners.append(cb)

    async def put(self, msg: Union[ParserMessage, CommandMessage, PublicCommandMessage, CommandResultMessage]):
        if not self.queue:
            self.queue = asyncio.Queue()

        await self.queue.put(msg)

    """Reads messages and notifies listeners"""
    async def run(self):
        if not self.queue:
            self.queue = asyncio.Queue()

        while True:
            msg = await self.queue.get()
            logging.debug(f'queue size: {self.queue.qsize()}')
            if isinstance(msg, ParserMessage):
                await asyncio.gather(*[pl(msg) for pl in self.parser_listeners])
            elif isinstance(msg, CommandMessage):
                await asyncio.gather(*[cl(msg) for cl in self.command_listeners])
            elif isinstance(msg, PublicCommandMessage):
                await asyncio.gather(*[cl(msg) for cl in self.public_command_listeners])
            elif isinstance(msg, CommandResultMessage):
                await asyncio.gather(*[rl(msg) for rl in self.command_result_listeners])
            self.queue.task_done()
