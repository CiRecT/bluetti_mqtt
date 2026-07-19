from bluetti_mqtt.bus import EventBus
from bluetti_mqtt.device_handler import DeviceHandler


class NamedManager:
    def __init__(self, names):
        self.names = names

    def get_name(self, address):
        return self.names[address]


def test_model_mismatch_disables_only_the_mismatched_device():
    handler = DeviceHandler(
        ['A', 'B'],
        interval=0,
        bus=EventBus(),
        expected_models={'A': 'AC300', 'B': 'AC500'},
    )
    handler.manager = NamedManager({'A': 'AC5001', 'B': 'AC5002'})

    assert handler._get_device('A') is None
    assert handler._get_device('B').type == 'AC500'
    assert handler.disabled_addresses == {'A'}


def test_unknown_discovered_model_disables_only_that_device():
    handler = DeviceHandler(
        ['A', 'B'],
        interval=0,
        bus=EventBus(),
        expected_models={'A': 'AC300', 'B': 'AC500'},
    )
    handler.manager = NamedManager({'A': 'UNKNOWN1', 'B': 'AC5002'})

    assert handler._get_device('A') is None
    assert handler._get_device('B').type == 'AC500'
