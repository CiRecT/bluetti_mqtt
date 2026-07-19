import pytest

from bluetti_mqtt.command import CommandError, CommandRequest, CommandResult, parse_public_command
from bluetti_mqtt.core.devices.ac200m import AC200M
from bluetti_mqtt.core.devices.ac300 import AC300
from bluetti_mqtt.mqtt_client import NORMAL_DEVICE_FIELDS


def parse(topic, payload, devices):
    return parse_public_command(topic, payload, devices, NORMAL_DEVICE_FIELDS)


@pytest.mark.parametrize(('payload', 'value'), [(b'ON', True), (b'OFF', False)])
def test_boolean_commands_accept_only_canonical_payloads(payload, value):
    device = AC300('A', '123')

    result = parse('bluetti/command/AC300-123/grid_charge_on', payload, [device])

    assert isinstance(result, CommandRequest)
    assert result.value is value


@pytest.mark.parametrize('payload', [b'on', b'1', b'true', b'', b'ON\n'])
def test_boolean_commands_reject_noncanonical_payloads(payload):
    device = AC300('A', '123')

    result = parse('bluetti/command/AC300-123/grid_charge_on', payload, [device])

    assert result.error == CommandError.INVALID_PAYLOAD
    assert result.value is None


def test_enum_commands_require_exact_canonical_name():
    device = AC300('A', '123')

    accepted = parse('bluetti/command/AC300-123/ups_mode', b'PV_PRIORITY', [device])
    rejected = parse('bluetti/command/AC300-123/ups_mode', b'pv_priority', [device])

    assert accepted.value == 'PV_PRIORITY'
    assert rejected.error == CommandError.INVALID_PAYLOAD


@pytest.mark.parametrize(('payload', 'error'), [
    (b'0', None),
    (b'100', None),
    (b'-1', CommandError.OUT_OF_RANGE),
    (b'101', CommandError.OUT_OF_RANGE),
    (b'5.0', CommandError.INVALID_PAYLOAD),
    (b'5A', CommandError.INVALID_PAYLOAD),
    (b'{}', CommandError.INVALID_PAYLOAD),
    (b'', CommandError.INVALID_PAYLOAD),
])
def test_numeric_commands_enforce_integer_syntax_and_range(payload, error):
    device = AC300('A', '123')

    result = parse('bluetti/command/AC300-123/battery_range_start', payload, [device])

    if error is None:
        assert isinstance(result, CommandRequest)
        assert result.value == int(payload)
    else:
        assert result.error == error


@pytest.mark.parametrize(('payload', 'accepted'), [(b'ON', True), (b'OFF', False), (b'', False)])
def test_button_commands_accept_only_configured_payload(payload, accepted):
    device = AC200M('A', '123')

    result = parse('bluetti/command/AC200M-123/power_off', payload, [device])

    assert isinstance(result, CommandRequest) is accepted
    if accepted:
        assert result.value is True
    else:
        assert result.error == CommandError.INVALID_PAYLOAD


@pytest.mark.parametrize('field', ['split_phase_on', 'split_phase_machine_mode'])
def test_non_public_split_phase_fields_are_never_authorized(field):
    device = AC300('A', '123')

    result = parse(f'bluetti/command/AC300-123/{field}', b'ON', [device])

    assert result.error == CommandError.UNSUPPORTED_FIELD


def test_device_capability_is_required_in_addition_to_public_metadata():
    device = AC200M('A', '123')

    result = parse('bluetti/command/AC200M-123/grid_charge_on', b'ON', [device])

    assert result.error == CommandError.UNSUPPORTED_FIELD


def test_unknown_device_produces_stable_rejection():
    result = parse('bluetti/command/AC300-999/grid_charge_on', b'ON', [])

    assert result == CommandResult.rejected('AC300-999', 'grid_charge_on', CommandError.UNKNOWN_DEVICE)


def test_syntactically_unknown_topic_cannot_produce_a_result_topic():
    assert parse_public_command('somewhere/else', b'ON', [], NORMAL_DEVICE_FIELDS) is None


def test_internal_device_commands_remain_available():
    device = AC300('A', '123')

    command = device.build_setter_command('pack_num', 2)

    assert command.address == 3006
    assert command.value == 2
