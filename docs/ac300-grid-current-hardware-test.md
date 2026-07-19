# AC300 grid charging current hardware test

This procedure validates the experimental AC300 grid charging current control.
It separates deterministic software checks from writes to physical equipment.

The examples assume:

- repository: `/home/bluetti/bluetti_mqtt`
- AC300 address: `04:7F:0E:A3:EF:C8`
- MQTT broker: `192.168.178.31:1885`
- MQTT username: `mqttuser`

Do not put MQTT passwords in this document, shell history, logs, or screenshots.

## 1. Verify and test the source checkout

The Raspberry Pi must contain commit `c0fd53a` or an explicitly approved newer
commit. The commit is not available from the upstream repository unless it has
been transferred or pushed separately.

```bash
cd /home/bluetti/bluetti_mqtt
git rev-parse --short HEAD

python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -m pip install -e .

.venv/bin/python -c "import sys, setuptools, wheel; print(sys.executable); print('build backend OK')"
.venv/bin/python -m pytest -q
.venv/bin/python -m flake8 bluetti_mqtt tests
.venv/bin/python -m pip check
.venv/bin/python -m build --no-isolation
```

The baseline for `c0fd53a` is 123 passing tests. Do not continue to the hardware
test if the printed Python path is not
`/home/bluetti/bluetti_mqtt/.venv/bin/python`, or if pytest, Flake8, dependency
checking, or the package build fails. `--no-isolation` is supported because
`requirements-dev.txt` installs the `setuptools` backend and `wheel` into this
exact virtual environment.

## 2. Identify the target without writing

```bash
cd /home/bluetti/bluetti_mqtt
. .venv/bin/activate
bluetti-mqtt --scan
```

Require one unambiguous result with address `04:7F:0E:A3:EF:C8` and a name of
the form `AC300<SERIAL>`. Stop on any model or address mismatch. MQTT uses the
device ID `AC300-<SERIAL>`, not the Bluetooth address.

## 3. Create the protected test configuration

Create `/home/bluetti/bluetti-mqtt-hardware-test.yaml`:

```yaml
version: 1
mqtt:
  host: 192.168.178.31
  port: 1885
  username: mqttuser
  password: 'REPLACE_WITH_PASSWORD'
polling_interval: 10
home_assistant: none
devices:
  - model: AC300
    address: 04:7F:0E:A3:EF:C8
    grid_charging:
      enabled: true
      minimum_update_interval: 10
```

Single quotes protect most YAML special characters. Represent a literal single
quote inside the password as two single quotes. Protect and validate the file:

```bash
chmod 600 /home/bluetti/bluetti-mqtt-hardware-test.yaml

cd /home/bluetti/bluetti_mqtt
. .venv/bin/activate
python3 -c "import os; from bluetti_mqtt.config import load_yaml_config; load_yaml_config('/home/bluetti/bluetti-mqtt-hardware-test.yaml', os.environ); print('config OK')"
```

## 4. Establish a safe baseline

Before any write:

1. Keep an operator at the AC300 with an immediate physical means to stop
   charging or disconnect AC input.
2. Confirm that the supply, socket, protection, and cables safely support 10 A.
3. Ensure adequate battery capacity and ventilation, with no abnormal heat,
   smell, or noise.
4. Stop every other MQTT, Home Assistant, app, or automation writer.
5. Confirm Grid Charging is off and record the previous current-limit setting.
6. Record firmware versions. The validation baseline is IoT `v9014.12`, ARM
   `v4037.07`, and DSP `v4036.30`; assess any difference before writing.
7. Inspect the two exact command topics for retained messages. The application
   rejects retained commands, but stale broker state should still be removed
   deliberately before the test.

The relevant command topics are:

```text
bluetti/command/AC300-<SERIAL>/grid_charging_current_limit
bluetti/command/AC300-<SERIAL>/grid_charge_on
```

## 5. Start and observe the gateway

Terminal A:

```bash
cd /home/bluetti/bluetti_mqtt
. .venv/bin/activate
DEBUG=1 bluetti-mqtt --config /home/bluetti/bluetti-mqtt-hardware-test.yaml
```

Initially send no commands. Require a stable AC300 model match, BLE connection,
and MQTT connection without timeout or reconnect loops.

Terminal B:

```bash
cd /home/bluetti/bluetti_mqtt
scripts/watch-grid-charging-status.sh 'AC300-<SERIAL>'
```

The watcher prompts for the MQTT password and displays the command result plus
acknowledged state topics. It does not write to MQTT.

## 6. Run the controlled 1 A, 5 A, and 10 A sequence

Commands must use QoS 1 and must never be retained. The supplied setter enforces
both rules and validates the requested value locally.

For each value, first prove Grid Charging is off using a trusted MQTT client and
confirm the off state physically. Then set the limit, starting with 1 A:

```bash
export DEVICE_ID='AC300-<SERIAL>'
read -r -s -p 'MQTT password: ' MQTT_TEST_PASSWORD
echo

mosquitto_pub \
  -h 192.168.178.31 -p 1885 \
  -u mqttuser -P "$MQTT_TEST_PASSWORD" \
  -q 1 \
  -t "bluetti/command/$DEVICE_ID/grid_charge_on" \
  -m 'OFF'
```

Require an `applied` result for `grid_charge_on` and confirm the off state at
the device before setting the limit:

```bash
cd /home/bluetti/bluetti_mqtt
scripts/set-grid-charging-current-limit.sh 'AC300-<SERIAL>' 1
```

Expect the watcher to show:

```json
{"status":"applied","cached":false,"value":1}
```

The acknowledged state topic must contain `1`. An `applied` result proves only
that a strict MODBUS acknowledgement was received; it does not prove physical
current. Check that the Bluetti app shows and retains the requested value. If
the app cannot connect while the gateway owns BLE, stop the gateway, inspect
with the app, disconnect the app, restart the gateway, and reconfirm Grid
Charging is off.

Only after the limit is confirmed may Grid Charging be enabled deliberately.
Observe actual current or power with suitable instrumentation for a short
period, then immediately turn Grid Charging off again. Require both an
`applied` result and physical confirmation of the stop.

```bash
mosquitto_pub \
  -h 192.168.178.31 -p 1885 \
  -u mqttuser -P "$MQTT_TEST_PASSWORD" \
  -q 1 \
  -t "bluetti/command/$DEVICE_ID/grid_charge_on" \
  -m 'ON'

# After the short controlled observation:
mosquitto_pub \
  -h 192.168.178.31 -p 1885 \
  -u mqttuser -P "$MQTT_TEST_PASSWORD" \
  -q 1 \
  -t "bluetti/command/$DEVICE_ID/grid_charge_on" \
  -m 'OFF'
```

Wait at least 15 seconds after a current-limit attempt, then repeat the complete
sequence with 5 A and finally 10 A:

```bash
scripts/set-grid-charging-current-limit.sh 'AC300-<SERIAL>' 5
scripts/set-grid-charging-current-limit.sh 'AC300-<SERIAL>' 10
```

Never continue through `rate_limited` or another unexpected result.

For each value record timestamp, MAC, firmware, requested value, complete result
JSON, state payload, app value after reconnect, measured current or power, the
on/off results, and any anomaly.

## 7. Abort and rollback

Immediately command Grid Charging off and, if that is not promptly confirmed
and physically effective, use local controls or safely disconnect AC input.
Abort on:

- any result other than a fresh expected `applied`
- `cached: true` for a supposedly new attempt
- timeout, reconnect, process failure, or duplicate writer
- an app value different from the requested limit
- charging before a deliberate on command
- unexpected current, power, heat, smell, or noise
- failure of the off command to stop charging

A `failed` result does not prove that the write had no physical effect; never
retry blindly. Keep charging off and inspect the actual device state first.

At completion, confirm Grid Charging is off, restore the operator's previous
current limit with another acknowledged command, confirm off again, stop the
gateway with `Ctrl-C`, run `unset MQTT_TEST_PASSWORD DEVICE_ID`, and save a test
report without credentials.
