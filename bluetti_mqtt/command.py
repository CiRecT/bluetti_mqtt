from dataclasses import dataclass, replace
from enum import Enum
import asyncio
import logging
import re
import time
from typing import Any, Callable, Dict, List, Mapping, Optional, Tuple, Union

from bleak import BleakError
from bluetti_mqtt.bluetooth.exc import (
    BadConnectionError,
    ConnectionChangedError,
    DispatchTimeoutError,
    ModbusError,
    ParseError,
)
from bluetti_mqtt.core import BluettiDevice, DeviceCommand
from bluetti_mqtt.core.devices.capabilities import ExecutionPolicy


COMMAND_TOPIC_RE = re.compile(r'^bluetti/command/(\w+)-(\d+)/([a-z_]+)$')
INTEGER_PAYLOAD_RE = re.compile(r'^-?(0|[1-9][0-9]*)$')


class CommandStatus(str, Enum):
    APPLIED = 'applied'
    REJECTED = 'rejected'
    FAILED = 'failed'


class CommandError(str, Enum):
    INVALID_PAYLOAD = 'invalid_payload'
    OUT_OF_RANGE = 'out_of_range'
    RETAINED_COMMAND_NOT_ALLOWED = 'retained_command_not_allowed'
    RATE_LIMITED = 'rate_limited'
    UNKNOWN_DEVICE = 'unknown_device'
    UNSUPPORTED_FIELD = 'unsupported_field'
    DEVICE_UNAVAILABLE = 'device_unavailable'
    DEVICE_TIMEOUT = 'device_timeout'
    INVALID_RESPONSE = 'invalid_response'
    MODBUS_ERROR = 'modbus_error'
    TRANSPORT_ERROR = 'transport_error'
    INTERNAL_ERROR = 'internal_error'


NormalizedValue = Union[int, bool, str]


@dataclass(frozen=True)
class CommandRequest:
    device: BluettiDevice
    device_id: str
    field: str
    value: NormalizedValue
    command: DeviceCommand
    policy: ExecutionPolicy = ExecutionPolicy()


@dataclass(frozen=True)
class CommandResult:
    device_id: str
    field: str
    status: CommandStatus
    cached: bool = False
    value: Optional[NormalizedValue] = None
    error: Optional[CommandError] = None

    @classmethod
    def rejected(
        cls,
        device_id: str,
        field: str,
        error: CommandError,
        value: Optional[NormalizedValue] = None,
    ):
        return cls(device_id, field, CommandStatus.REJECTED, value=value, error=error)

    @classmethod
    def applied(cls, request: CommandRequest):
        return cls(request.device_id, request.field, CommandStatus.APPLIED, value=request.value)

    @classmethod
    def failed(cls, request: CommandRequest, error: CommandError):
        return cls(
            request.device_id,
            request.field,
            CommandStatus.FAILED,
            value=request.value,
            error=error,
        )


class CommandExecutor:
    def __init__(
        self,
        manager,
        clock: Callable[[], float] = time.monotonic,
        minimum_update_intervals: Optional[Mapping[Tuple[str, str], int]] = None,
    ):
        self.manager = manager
        self.clock = clock
        self.minimum_update_intervals = dict(minimum_update_intervals or {})
        self._locks: Dict[str, asyncio.Lock] = {}
        self._last_attempts: Dict[Tuple[str, str], float] = {}
        self._last_keys: Dict[Tuple[str, str], Tuple[Any, ...]] = {}
        self._results: Dict[Tuple[Any, ...], CommandResult] = {}
        self._inflight: Dict[Tuple[Any, ...], asyncio.Future] = {}

    async def execute(self, request: CommandRequest) -> CommandResult:
        dispatch_deadline = (
            self.clock() + request.policy.dispatch_timeout
            if request.policy.dispatch_timeout is not None else None
        )
        interval = max(
            request.policy.minimum_update_interval,
            self.minimum_update_intervals.get((request.device.address, request.field), 0),
        )
        key = (request.device.address, request.field, type(request.value), request.value)
        rate_scope = (request.device.address, request.field)

        inflight = self._inflight.get(key)
        if inflight is not None:
            return replace(await asyncio.shield(inflight), cached=True)

        if interval > 0:
            other_inflight = any(
                pending_key[0] == request.device.address and pending_key[1] == request.field
                for pending_key in self._inflight
            )
            if other_inflight:
                return CommandResult.rejected(
                    request.device_id,
                    request.field,
                    CommandError.RATE_LIMITED,
                    request.value,
                )
            last_attempt = self._last_attempts.get(rate_scope)
            if last_attempt is not None and self.clock() - last_attempt < interval:
                previous = self._results.get(key) if self._last_keys.get(rate_scope) == key else None
                if previous is not None:
                    return replace(previous, cached=True)
                return CommandResult.rejected(
                    request.device_id,
                    request.field,
                    CommandError.RATE_LIMITED,
                    request.value,
                )

        if not self.manager.is_ready(request.device.address):
            return CommandResult.rejected(
                request.device_id,
                request.field,
                CommandError.DEVICE_UNAVAILABLE,
                request.value,
            )

        loop = asyncio.get_running_loop()
        outcome_future = loop.create_future()
        self._inflight[key] = outcome_future
        lock = self._locks.setdefault(request.device.address, asyncio.Lock())
        lock_acquired = False
        try:
            if dispatch_deadline is None:
                await lock.acquire()
                lock_acquired = True
            else:
                remaining = dispatch_deadline - self.clock()
                if remaining > 0:
                    try:
                        await asyncio.wait_for(lock.acquire(), timeout=remaining)
                        lock_acquired = True
                    except asyncio.TimeoutError:
                        pass

            if not lock_acquired or (
                dispatch_deadline is not None and self.clock() >= dispatch_deadline
            ):
                result = CommandResult.rejected(
                    request.device_id,
                    request.field,
                    CommandError.DEVICE_TIMEOUT,
                    request.value,
                )
            else:
                attempt_request = request
                if dispatch_deadline is not None:
                    attempt_request = replace(
                        request,
                        policy=replace(
                            request.policy,
                            dispatch_timeout=max(0, dispatch_deadline - self.clock()),
                        ),
                    )
                result = await self._attempt(
                    attempt_request,
                    (rate_scope, key) if interval > 0 else None,
                )
            self._results[key] = result
            outcome_future.set_result(result)
            return result
        except BaseException:
            outcome_future.cancel()
            raise
        finally:
            if lock_acquired:
                lock.release()
            self._inflight.pop(key, None)

    def _record_attempt(self, rate_scope: Tuple[str, str], key: Tuple[Any, ...]):
        self._last_attempts[rate_scope] = self.clock()
        self._last_keys[rate_scope] = key

    async def _attempt(self, request: CommandRequest, rate_context: Optional[Tuple[Any, ...]]) -> CommandResult:
        try:
            response_future = await self.manager.perform(
                request.device.address,
                request.command,
                policy=request.policy,
                on_attempt=(
                    (lambda: self._record_attempt(rate_context[0], rate_context[1]))
                    if rate_context is not None else None
                ),
            )
            response = await response_future
            if not request.command.is_valid_response(response):
                return CommandResult.failed(request, CommandError.INVALID_RESPONSE)
            return CommandResult.applied(request)
        except asyncio.TimeoutError:
            return CommandResult.failed(request, CommandError.DEVICE_TIMEOUT)
        except DispatchTimeoutError:
            return CommandResult.rejected(
                request.device_id,
                request.field,
                CommandError.DEVICE_TIMEOUT,
                request.value,
            )
        except ConnectionChangedError:
            return CommandResult.rejected(
                request.device_id,
                request.field,
                CommandError.DEVICE_UNAVAILABLE,
                request.value,
            )
        except ParseError:
            return CommandResult.failed(request, CommandError.INVALID_RESPONSE)
        except ModbusError:
            return CommandResult.failed(request, CommandError.MODBUS_ERROR)
        except (BleakError, EOFError, BadConnectionError):
            return CommandResult.failed(request, CommandError.TRANSPORT_ERROR)
        except Exception:
            logging.exception('Unexpected public command failure')
            return CommandResult.failed(request, CommandError.INTERNAL_ERROR)


def _decode_ascii(payload: bytes) -> Optional[str]:
    try:
        return payload.decode('ascii')
    except UnicodeDecodeError:
        return None


def _parse_value(field_config: Any, payload: bytes):
    text = _decode_ascii(payload)
    if text is None:
        return None, CommandError.INVALID_PAYLOAD

    field_type = field_config.type.name
    metadata = field_config.home_assistant_extra
    if field_type == 'BOOL':
        if text == 'ON':
            return True, None
        if text == 'OFF':
            return False, None
        return None, CommandError.INVALID_PAYLOAD

    if field_type == 'BUTTON':
        if text == metadata.get('payload_press'):
            return True, None
        return None, CommandError.INVALID_PAYLOAD

    if field_type == 'ENUM':
        if text in metadata.get('options', []):
            return text, None
        return None, CommandError.INVALID_PAYLOAD

    if field_type == 'NUMERIC':
        if INTEGER_PAYLOAD_RE.fullmatch(text) is None:
            return None, CommandError.INVALID_PAYLOAD
        value = int(text)
        minimum = metadata.get('min')
        maximum = metadata.get('max')
        step = metadata.get('step', 1)
        base = minimum if minimum is not None else 0
        if (
            (minimum is not None and value < minimum)
            or (maximum is not None and value > maximum)
            or (value - base) % step != 0
        ):
            return value, CommandError.OUT_OF_RANGE
        return value, None

    raise AssertionError(f'unexpected MQTT field type: {field_type}')


def parse_public_command(
    topic: str,
    payload: bytes,
    devices: List[BluettiDevice],
    field_configs: Union[Mapping[str, Any], Callable[[BluettiDevice], Mapping[str, Any]]],
    retain: bool = False,
) -> Optional[Union[CommandRequest, CommandResult]]:
    match = COMMAND_TOPIC_RE.fullmatch(topic)
    if match is None:
        return None

    device_id = f'{match[1]}-{match[2]}'
    field_name = match[3]
    device = next(
        (candidate for candidate in devices if candidate.type == match[1] and candidate.sn == match[2]),
        None,
    )
    if device is None:
        return CommandResult.rejected(device_id, field_name, CommandError.UNKNOWN_DEVICE)

    available_fields = field_configs(device) if callable(field_configs) else field_configs
    field_config = available_fields.get(field_name)
    if field_config is None or not field_config.setter or not device.has_field_setter(field_name):
        return CommandResult.rejected(device_id, field_name, CommandError.UNSUPPORTED_FIELD)
    value, error = _parse_value(field_config, payload)
    if retain and not field_config.allow_retained_commands:
        return CommandResult.rejected(
            device_id,
            field_name,
            CommandError.RETAINED_COMMAND_NOT_ALLOWED,
            value if error is None else None,
        )

    if error is not None:
        return CommandResult.rejected(device_id, field_name, error, value)

    command = device.build_setter_command(field_name, value)
    policy = device.get_command_policy(field_name)
    return CommandRequest(device, device_id, field_name, value, command, policy)
