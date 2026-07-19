# bluetti_mqtt

This tool provides an MQTT interface to Bluetti power stations. State will be
published to the `bluetti/state/[DEVICE NAME]/[PROPERTY]` topic, and commands
can be sent to the `bluetti/command/[DEVICE NAME]/[PROPERTY]` topic.

## Installation

```bash
pip install bluetti_mqtt
```

## Development setup

Python 3.10 or newer is required. Create and activate a local virtual
environment before installing the project and its development tools:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip install -e .
python -m pip install -r requirements-dev.txt
python -m pytest
```

## Usage

```console
$ bluetti-mqtt --scan
Found AC3001234567890123: address 00:11:22:33:44:55
$ bluetti-mqtt --broker [MQTT_BROKER_HOST] 00:11:22:33:44:55
```

If your MQTT broker has a username and password, you can pass those in.

```bash
bluetti-mqtt --broker [MQTT_BROKER_HOST] --username username --password pass 00:11:22:33:44:55
```

By default the device is polled as quickly as possible, but if you'd like to
collect less data, the polling interval can be adjusted.

```bash
# Poll every 60s
bluetti-mqtt --broker [MQTT_BROKER_HOST] --interval 60 00:11:22:33:44:55
```

If you have multiple devices within Bluetooth range, you can monitor all of
them with just a single command. We can only talk to one device at a time, so
you may notice some irregularity in the collected data, especially if you have
not set an interval.

```bash
bluetti-mqtt --broker [MQTT_BROKER_HOST] 00:11:22:33:44:55 00:11:22:33:44:66
```

### YAML configuration

The existing command-line mode remains supported. Alternatively, pass one
explicit, versioned YAML file; `--config` cannot be combined with broker,
polling, Home Assistant, scanning, or device arguments.

```bash
bluetti-mqtt --config /etc/bluetti-mqtt.yaml
```

```yaml
version: 1
mqtt:
  host: broker.example
  port: 1883
  username: bluetti
  password_env: BLUETTI_MQTT_PASSWORD
polling_interval: 10
home_assistant: normal
devices:
  - model: AC300
    address: AA:BB:CC:DD:EE:FF
    grid_charging:
      enabled: true
      minimum_update_interval: 10
```

See [`examples/config.yaml`](examples/config.yaml) for a complete template.
The schema rejects unknown keys and wrong types. Every device needs an exact
supported model and a unique address. MQTT `password` and `password_env` are
mutually exclusive; a missing referenced environment variable stops startup.
Files are loaded only at startup and are not discovered or hot-reloaded.

### MQTT command results

Every syntactically valid public command produces a non-retained QoS 1 JSON
result at `bluetti/result/<device>/<field>`. Command subscriptions also use
QoS 1. Examples:

```json
{"status":"applied","cached":false,"value":5}
{"status":"rejected","cached":false,"value":11,"error":"out_of_range"}
{"status":"failed","cached":false,"value":5,"error":"device_timeout"}
```

`rejected` means no device write was attempted, `failed` means an attempt was
not confirmed, and `applied` means the device returned a valid MODBUS
acknowledgement. It does not prove measured physical behaviour. Stable errors
are `invalid_payload`, `out_of_range`, `retained_command_not_allowed`,
`rate_limited`, `unknown_device`, `unsupported_field`, `device_unavailable`,
`device_timeout`, `invalid_response`, `modbus_error`, `transport_error`, and
`internal_error`. The `value` key is omitted when payload syntax cannot be
parsed. Malformed topics that cannot identify a result topic are logged and
ignored.

### Experimental AC300 grid charging current limit

YAML can opt one AC300 into the `grid_charging_current_limit` actuator. It
accepts only ASCII integers from 1 through 10 A and writes register 3019. The
acknowledged, non-retained state at
`bluetti/state/<device>/grid_charging_current_limit` remains unknown until the
first successful write in the current process; it is never inferred from
polling or treated as measured current. Home Assistant receives a number entity
with minimum 1, maximum 10, step 1, and unit A.

Retained commands are rejected. Duplicate values inside the configured update
interval reuse the previous result with `cached: true`; different values are
rejected as `rate_limited`. The interval defaults to 10 seconds and cannot be
lowered. Device response timeout is five seconds and this actuator is never
automatically retried. A queued setpoint expires after five seconds and is
discarded if the BLE connection generation changes, so it cannot execute after
a later reconnect.

Use one authoritative external writer. To start safely, set the current limit,
wait for `applied`, then send `grid_charge_on=ON`. Stop charging with the
separate `grid_charge_on=OFF` command. The adapter intentionally provides no PV
controller, watchdog, delayed setpoint, or automatic reset; if the external
controller stops, the device retains its last accepted settings.

This feature remains experimental until a controlled AC300 test confirms 1, 5,
and 10 A with IoT v9014.12, ARM v4037.07, and DSP v4036.30. Automated tests do
not access a broker, BLE adapter, or power station.

Manual validation requires explicit authorization and a known-safe AC300 setup
with charging initially disabled, a suitable supply and battery state, and an
operator able to stop charging locally. For each value 1, 5, and 10 A:

1. Publish the non-retained current-limit command and record timestamp, result,
   and raw debug log reference.
2. Require `applied`, then confirm the app shows the requested persistent limit
   after reconnect.
3. Enable `grid_charge_on`, verify observed charging behaviour stays within the
   selected limit, then immediately disable `grid_charge_on` again.
4. Record expected and actual result, app value, measured behaviour, firmware,
   and any anomaly. Stop on the first mismatch; do not continue to a higher
   current.

Rollback is `grid_charge_on=OFF`, followed by restoring the operator's previous
current limit only after another acknowledged command. Disconnect external AC
input or use the device's local controls if MQTT/BLE shutdown does not confirm.
No step in this checklist has been performed by the automated test suite.

## Background Service

If you are running on a platform with systemd, you can use the following as a
template. It should be placed in `/etc/systemd/system/bluetti-mqtt.service`.
Once you've written the file, you'll need to run
`sudo systemctl start bluetti-mqtt`. If you want it to run automatically after
rebooting, you'll also need to run `sudo systemctl enable bluetti-mqtt`.

```ini
[Unit]
Description=Bluetti MQTT
After=network.target
StartLimitIntervalSec=0

[Service]
Type=simple
Restart=always
RestartSec=30
TimeoutStopSec=15
User=your_username_here
ExecStart=/home/your_username_here/.local/bin/bluetti-mqtt --broker [MQTT_BROKER_HOST] 00:11:22:33:44:55

[Install]
WantedBy=multi-user.target
```

## Home Assistant Integration

If you have configured Home Assistant to use the same MQTT broker, then by
default most data and switches will be automatically configured there. This is
possible thanks to Home Assistant's support for automatic MQTT discovery, which
is enabled by default with the discovery prefix of `homeassistant`.

This can be controlled with the `--ha-config` flag, which defaults to
configuring most fields ("normal"). Home Assistant MQTT discovery can also be
disabled, or additional internal device fields can be configured with the
"advanced" option.

In YAML mode, use `home_assistant: normal`, `none`, or `advanced` instead.

## Reverse Engineering

For research purposes you can also use the `bluetti-logger` command to poll
the device and log in a standardised format.

```bash
bluetti-logger --log the-log-file.log 00:11:22:33:44:55
```

While the logger is running, change settings on the device and take note of the
time when you made the change, waiting ~1 minute between changes. Note that
not every setting that can be changed on the device can be changed over
Bluetooth.

If you're looking to add support to control something that the app can change
but cannot be changed directly from the device screen, both iOS and Android
support collecting Bluetooth logs from running apps. Additionally, with the
correct hardware Wireshark can be used to collect logs. With these logs and a
report of what commands were sent at what times, this data can be used to
reverse engineer support.

For supporting new devices, the `bluetti-discovery` command is provided. It
will scan from 0 to 12500 assuming MODBUS-over-Bluetooth. This will take a
while and requires that the scanned device be in close Bluetooth range for
optimal performance.

```console
$ bluetti-discovery --scan
Found AC3001234567890123: address 00:11:22:33:44:55
$ bluetti-discovery --log the-log-file.log 00:11:22:33:44:55
```
