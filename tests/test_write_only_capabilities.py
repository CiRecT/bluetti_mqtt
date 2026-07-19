import pytest

from bluetti_mqtt.core.devices.ac300 import AC300
from bluetti_mqtt.core.devices.ac500 import AC500


@pytest.mark.parametrize(('value', 'expected_hex'), [
    (1, '01060bcb00013bd0'),
    (5, '01060bcb00053a13'),
    (10, '01060bcb000a7a17'),
])
def test_ac300_builds_grid_current_commands_from_write_only_capability(value, expected_hex):
    device = AC300('A', '123')

    command = device.build_setter_command('grid_charging_current_limit', value)

    assert bytes(command) == bytes.fromhex(expected_hex)


@pytest.mark.parametrize('value', [0, 11, 1.5, True])
def test_grid_current_write_only_capability_rejects_invalid_values(value):
    device = AC300('A', '123')

    with pytest.raises(ValueError):
        device.build_setter_command('grid_charging_current_limit', value)


def test_grid_current_capability_is_ac300_only():
    assert AC300('A', '123').has_field_setter('grid_charging_current_limit') is True
    assert AC500('B', '456').has_field_setter('grid_charging_current_limit') is False


def test_register_3019_polling_never_becomes_telemetry():
    device = AC300('A', '123')
    parsed = device.parse(3019, bytes.fromhex('0005'))

    assert 'grid_charging_current_limit' not in parsed


def test_grid_current_capability_owns_safe_execution_policy():
    policy = AC300('A', '123').get_command_policy('grid_charging_current_limit')

    assert policy.timeout == 5
    assert policy.max_attempts == 1
    assert policy.minimum_update_interval == 10
    assert policy.dispatch_timeout == 5
    assert policy.requires_same_connection is True


def test_existing_readable_setters_still_build_commands():
    command = AC300('A', '123').build_setter_command('grid_charge_on', True)

    assert command.address == 3011
    assert command.value == 1
