# AGENTS.md

## Project overview

`bluetti_mqtt` is a Python package and set of command-line tools that bridge
supported Bluetti power stations to MQTT over Bluetooth Low Energy (BLE). It
polls MODBUS-style registers, publishes parsed state, accepts selected write
commands, and creates Home Assistant MQTT discovery entities.

The repository is a single setuptools package. It currently targets Python
3.10 or newer and has no automated test suite.

## Repository map

- `bluetti_mqtt/core/commands.py`: MODBUS request construction, response sizing,
  CRC validation, and raw response parsing.
- `bluetti_mqtt/core/devices/struct.py`: register field definitions and parsing.
- `bluetti_mqtt/core/devices/`: device-specific register maps, polling ranges,
  enums, and writable ranges.
- `bluetti_mqtt/bluetooth/`: BLE scanning, connection state, request queuing,
  retries, and response assembly.
- `bluetti_mqtt/bus.py`: asynchronous in-process message bus between polling and
  MQTT layers.
- `bluetti_mqtt/device_handler.py`: device discovery, polling loops, and command
  dispatch.
- `bluetti_mqtt/mqtt_client.py`: MQTT topics, Home Assistant discovery payloads,
  field metadata, value conversion, and incoming command handling.
- `bluetti_mqtt/server_cli.py`: `bluetti-mqtt` application entry point.
- `bluetti_mqtt/logger_cli.py`: `bluetti-logger` reverse-engineering helper.
- `bluetti_mqtt/discovery_cli.py`: `bluetti-discovery` MODBUS range scanner.
- `setup.cfg`, `setup.py`, and `pyproject.toml`: packaging metadata and build
  configuration.
- `.github/workflows/release.yml`: style check, distribution build, and upstream
  Test PyPI/PyPI publishing workflow.

The main runtime flow is:

1. `server_cli.py` starts the event bus, MQTT client, and `DeviceHandler`.
2. `DeviceHandler` uses `MultiDeviceManager`/`BluetoothClient` to poll a device.
3. A device class parses register bytes into named fields.
4. Parsed messages pass through `EventBus` to `MQTTClient` for publishing.
5. Valid MQTT commands travel back through the bus and BLE layers as MODBUS
   write commands.

## Environment setup

Use `python3`; some environments do not provide a `python` alias.

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install --upgrade pip
python3 -m pip install -r requirements.txt
python3 -m pip install -e .
python3 -m pip install flake8 build
```

`requirements.txt` pins the known runtime dependency set, while package runtime
dependencies are also declared in `setup.cfg`. Flake8 and `build` are CI/developer
tools and are not currently declared as project dependencies.

BLE access is platform-specific. Linux development may require a running D-Bus,
BlueZ, Bluetooth permissions, and a nearby supported device. MQTT integration
work also requires a reachable broker.

## Development commands

After installing the package in editable mode:

```bash
bluetti-mqtt --help
bluetti-logger --help
bluetti-discovery --help
```

Run the gateway against a real device and broker only when the task calls for
integration testing:

```bash
bluetti-mqtt --scan
bluetti-mqtt --broker MQTT_HOST DEVICE_ADDRESS
```

Set `DEBUG=1` to enable debug logging and Python warnings:

```bash
DEBUG=1 bluetti-mqtt --broker MQTT_HOST DEVICE_ADDRESS
```

Do not run `bluetti-discovery --log ...` casually. It scans registers from 0
through 12500, can take hours, and communicates continuously with real hardware.

## Validation and testing

There is no committed `tests/` directory or configured test framework. For every
change, run the checks that exist in CI:

```bash
python3 -m flake8 bluetti_mqtt
python3 -m build
```

Flake8 uses `.flake8`: the maximum line length is 120, and unused imports are
allowed only in `__init__.py` files. Build artifacts are written to `dist/` and
are ignored by Git.

When adding testable behavior, add focused automated tests rather than relying
only on hardware checks. Prefer tests that use captured byte payloads and fake
BLE/MQTT collaborators so register parsing, command encoding, CRC handling,
topic handling, and Home Assistant payloads remain deterministic. Document and
clearly separate any validation that still requires a physical device or broker.

## Code conventions

- Follow the existing Python style: four-space indentation, single-quoted
  strings in most modules, type hints where they improve interfaces, and lines
  no longer than 120 characters.
- Keep asynchronous I/O non-blocking. Use `asyncio.sleep` in coroutines and
  preserve cancellation/cleanup behavior in long-running tasks.
- Keep protocol concerns separated: raw MODBUS behavior belongs in `core`, BLE
  transport belongs in `bluetooth`, orchestration belongs in `device_handler`,
  and MQTT/Home Assistant behavior belongs in `mqtt_client`.
- Preserve existing public CLI names and MQTT topic formats unless a change is
  explicitly intended and documented as breaking.
- Maintain Python 3.10 compatibility unless the project deliberately raises its
  minimum supported version. Avoid newer syntax and standard-library APIs until
  that decision is reflected in packaging and CI.
- Add user-visible changes under `FUTURE` in `CHANGELOG.md`.
- Do not hand-edit generated build output or commit virtual environments,
  credentials, device addresses, broker passwords, packet logs, or discovery
  logs.

## Device and protocol changes

Treat register definitions and writes as hardware-facing code:

- Confirm register addresses, sizes, byte order, scale, range, and enum values
  from reliable captures or documentation.
- Keep read ranges within the device's known supported regions. A field is
  parsed only when its complete register span is present in a response.
- Add setters only for fields whose register is included in that device class's
  `writable_ranges`. Never broaden a writable range merely to make a command
  pass validation.
- A writable MQTT field must agree across the device structure, writable range,
  and `MqttFieldConfig`; verify boolean, enum, and numeric conversion paths.
- Invalid writes can change the state of physical equipment. Do not perform
  live write tests without explicit authorization and a known-safe device state.

To add a device model, normally update all of the following:

1. Add its class and register map under `bluetti_mqtt/core/devices/`.
2. Export it from `bluetti_mqtt/core/devices/__init__.py` and
   `bluetti_mqtt/core/__init__.py`.
3. Extend `DEVICE_NAME_RE` and `build_device()` in
   `bluetti_mqtt/bluetooth/__init__.py`.
4. Add or reuse MQTT/Home Assistant field metadata as needed.
5. Add parsing and command tests built from captured protocol data.
6. Update `README.md` and `CHANGELOG.md` for user-visible support.

## MQTT and Home Assistant compatibility

State topics use `bluetti/state/<device>/<field>`, and commands use
`bluetti/command/<device>/<field>`. Home Assistant discovery configuration is
derived from the field maps in `mqtt_client.py`.

When adding or renaming a field, check all downstream effects: MQTT state topic,
command parsing, retained discovery payload, entity type, unique ID, units,
device class, state class, pack-field handling, and serialization of `Decimal`,
`Enum`, and boolean values. Prefer backward-compatible topic and entity IDs to
avoid creating duplicate Home Assistant entities.

## Pull request and release hygiene

- Keep changes focused and avoid unrelated formatting churn in the large device
  maps or MQTT field table.
- Include automated coverage for new pure-Python behavior whenever practical.
- State which checks ran and which hardware-dependent checks were not possible.
- Before committing, inspect `git diff` and run Flake8 plus the distribution
  build.
- Do not publish packages or create release tags as part of routine validation.
  In the upstream repository, the GitHub Actions workflow publishes builds to
  Test PyPI and publishes tagged pushes to PyPI.
