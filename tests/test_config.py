import asyncio

import pytest

from bluetti_mqtt.config import ConfigError, load_yaml_config
from bluetti_mqtt.server_cli import CommandLineHandler


def write_config(tmp_path, content):
    path = tmp_path / 'bluetti.yaml'
    path.write_text(content, encoding='utf-8')
    return path


def test_minimal_yaml_uses_documented_defaults(tmp_path):
    path = write_config(tmp_path, '''
version: 1
mqtt:
  host: broker.local
devices:
  - model: AC300
    address: AA:BB:CC:DD:EE:FF
''')

    config = load_yaml_config(path, environ={})

    assert config.mqtt.port == 1883
    assert config.polling_interval == 0
    assert config.home_assistant == 'normal'
    assert config.devices[0].grid_charging.enabled is False
    assert config.devices[0].grid_charging.minimum_update_interval == 10


def test_complete_yaml_resolves_password_from_environment(tmp_path):
    path = write_config(tmp_path, '''
version: 1
mqtt:
  host: broker.local
  port: 8883
  username: operator
  password_env: BLUETTI_MQTT_PASSWORD
polling_interval: 15
home_assistant: advanced
devices:
  - model: AC300
    address: AA:BB:CC:DD:EE:FF
    grid_charging:
      enabled: true
      minimum_update_interval: 30
''')

    config = load_yaml_config(path, environ={'BLUETTI_MQTT_PASSWORD': 'secret'})

    assert config.mqtt.password == 'secret'
    assert config.mqtt.password_env is None
    assert config.devices[0].grid_charging.enabled is True
    assert config.devices[0].grid_charging.minimum_update_interval == 30


@pytest.mark.parametrize(('yaml_text', 'path_fragment'), [
    ('version: 2\nmqtt: {host: broker}\ndevices: [{model: AC300, address: A}]\n', 'version'),
    ('version: 1\nunknown: true\nmqtt: {host: broker}\ndevices: [{model: AC300, address: A}]\n', 'unknown'),
    ('version: 1\nmqtt: {host: broker, port: "1883"}\ndevices: [{model: AC300, address: A}]\n', 'mqtt.port'),
    ('version: 1\nmqtt: {host: broker}\ndevices: []\n', 'devices'),
    ('version: 1\nmqtt: {host: broker}\ndevices: [{model: UNKNOWN, address: A}]\n', 'devices.0.model'),
    ('version: 1\nmqtt: {host: broker}\ndevices: [{model: AC300}]\n', 'devices.0.address'),
    (
        'version: 1\nmqtt: {host: broker}\ndevices: [{model: AC300, address: aa}, {model: AC500, address: AA}]\n',
        'devices',
    ),
    (
        'version: 1\nmqtt: {host: broker}\ndevices: [{model: AC500, address: A, '
        'grid_charging: {enabled: true}}]\n',
        'devices.0',
    ),
    (
        'version: 1\nmqtt: {host: broker}\ndevices: [{model: AC300, address: A, '
        'grid_charging: {minimum_update_interval: 9}}]\n',
        'minimum_update_interval',
    ),
])
def test_invalid_yaml_reports_precise_configuration_path(tmp_path, yaml_text, path_fragment):
    path = write_config(tmp_path, yaml_text)

    with pytest.raises(ConfigError) as error:
        load_yaml_config(path, environ={})

    assert path_fragment in str(error.value)


def test_password_sources_are_mutually_exclusive(tmp_path):
    path = write_config(tmp_path, '''
version: 1
mqtt:
  host: broker
  password: direct
  password_env: MQTT_PASSWORD
devices:
  - model: AC300
    address: A
''')

    with pytest.raises(ConfigError, match='mqtt'):
        load_yaml_config(path, environ={'MQTT_PASSWORD': 'environment'})


def test_missing_password_environment_variable_is_fatal(tmp_path):
    path = write_config(tmp_path, '''
version: 1
mqtt:
  host: broker
  password_env: MISSING_PASSWORD
devices:
  - model: AC300
    address: A
''')

    with pytest.raises(ConfigError, match='mqtt.password_env'):
        load_yaml_config(path, environ={})


def test_config_mode_is_selected_explicitly_and_exclusively(tmp_path):
    path = write_config(tmp_path, '''
version: 1
mqtt: {host: broker}
devices: [{model: AC300, address: A}]
''')

    config = CommandLineHandler(['bluetti-mqtt', '--config', str(path)], environ={}).parse()

    assert config.mqtt.host == 'broker'
    assert config.devices[0].model == 'AC300'


def test_config_mode_rejects_cli_runtime_arguments(tmp_path):
    path = write_config(tmp_path, '''
version: 1
mqtt: {host: broker}
devices: [{model: AC300, address: A}]
''')

    handler = CommandLineHandler(
        ['bluetti-mqtt', '--config', str(path), '--port', '1884'],
        environ={},
    )

    with pytest.raises(ConfigError, match='cannot be combined'):
        handler.parse()


def test_legacy_cli_arguments_remain_unchanged():
    args = CommandLineHandler(
        ['bluetti-mqtt', '--broker', 'broker', '--port', '1884', 'AA:BB'],
        environ={},
    ).parse()

    assert args.hostname == 'broker'
    assert args.port == 1884
    assert args.addresses == ['AA:BB']


def test_cli_start_creates_an_event_loop_when_none_exists(monkeypatch):
    class FakeLoop:
        def __init__(self):
            self.ran = False
            self.closed = False

        def add_signal_handler(self, signal, callback):
            pass

        def set_exception_handler(self, callback):
            pass

        def create_task(self, coroutine):
            coroutine.close()

        def run_forever(self):
            self.ran = True

        def close(self):
            self.closed = True

    def no_current_loop():
        raise RuntimeError("There is no current event loop in thread 'MainThread'.")

    loop = FakeLoop()
    installed_loops = []
    monkeypatch.setattr(asyncio, 'get_event_loop', no_current_loop)
    monkeypatch.setattr(asyncio, 'new_event_loop', lambda: loop)
    monkeypatch.setattr(asyncio, 'set_event_loop', installed_loops.append)

    CommandLineHandler(['bluetti-mqtt']).start(object())

    assert loop.ran is True
    assert loop.closed is True
    assert installed_loops == [loop, None]
