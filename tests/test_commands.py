import pytest

from bluetti_mqtt.core import ReadHoldingRegisters, WriteSingleRegister
from bluetti_mqtt.core.utils import modbus_crc


def with_crc(body: bytes) -> bytes:
    return body + modbus_crc(body).to_bytes(2, byteorder='little')


def test_read_holding_registers_builds_known_modbus_request():
    command = ReadHoldingRegisters(10, 3)

    assert bytes(command) == bytes.fromhex('0103000a000325c9')
    assert command.response_size() == 11


def test_write_single_register_builds_known_modbus_request():
    command = WriteSingleRegister(3019, 5)

    assert bytes(command) == bytes.fromhex('01060bcb00053a13')
    assert command.response_size() == 8


@pytest.mark.parametrize('response', [
    with_crc(bytes.fromhex('02060bcb0005')),
    with_crc(bytes.fromhex('01030bcb0005')),
    with_crc(bytes.fromhex('01060bcc0005')),
    with_crc(bytes.fromhex('01060bcb0006')),
    bytes.fromhex('01060bcb00053a12'),
    bytes.fromhex('01060bcb00053a'),
    bytes.fromhex('01060bcb00053a1300'),
])
def test_write_single_register_rejects_every_non_exact_acknowledgement(response):
    command = WriteSingleRegister(3019, 5)

    assert command.is_valid_response(response) is False


def test_write_single_register_accepts_exact_acknowledgement():
    command = WriteSingleRegister(3019, 5)

    assert command.is_valid_response(bytes.fromhex('01060bcb00053a13')) is True


def test_modbus_exception_requires_complete_valid_response():
    command = WriteSingleRegister(3019, 5)
    valid_exception = with_crc(bytes.fromhex('018602'))

    assert command.is_exception_response(valid_exception) is True
    assert command.is_exception_response(valid_exception[:-1]) is False
    assert command.is_exception_response(valid_exception[:-1] + b'\x00') is False


def test_read_response_validation_remains_crc_based():
    command = ReadHoldingRegisters(10, 1)
    response = with_crc(bytes.fromhex('010302002a'))

    assert command.is_valid_response(response) is True
