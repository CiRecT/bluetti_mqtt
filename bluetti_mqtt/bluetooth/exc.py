class ParseError(Exception):
    pass


class ModbusError(Exception):
    """Used when the command returns a MODBUS exception"""
    pass


# Triggers a re-connect
class BadConnectionError(Exception):
    pass


class DispatchTimeoutError(Exception):
    """Command expired in the local queue before a BLE write was attempted."""
    pass


class ConnectionChangedError(Exception):
    """Command was queued for a BLE connection that is no longer active."""
    pass
