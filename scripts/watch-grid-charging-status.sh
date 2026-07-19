#!/usr/bin/env bash
set -euo pipefail

usage() {
    echo "Usage: $0 AC300-<serial>" >&2
}

if [[ $# -ne 1 ]]; then
    usage
    exit 2
fi

device_id=$1
if [[ ! $device_id =~ ^AC300-[0-9]+$ ]]; then
    echo 'Device ID must have the form AC300-<numeric serial>.' >&2
    exit 2
fi

if ! command -v mosquitto_sub >/dev/null 2>&1; then
    echo 'mosquitto_sub is required (Debian package: mosquitto-clients).' >&2
    exit 127
fi

mqtt_host=${MQTT_HOST:-192.168.178.31}
mqtt_port=${MQTT_PORT:-1885}
mqtt_username=${MQTT_USERNAME:-mqttuser}

if [[ -n ${MQTT_TEST_PASSWORD:-} ]]; then
    mqtt_password=$MQTT_TEST_PASSWORD
else
    read -r -s -p 'MQTT password: ' mqtt_password
    echo
fi

trap 'unset mqtt_password MQTT_TEST_PASSWORD' EXIT

echo "Watching grid charging state and results for $device_id on $mqtt_host:$mqtt_port" >&2
mosquitto_sub \
    -h "$mqtt_host" \
    -p "$mqtt_port" \
    -u "$mqtt_username" \
    -P "$mqtt_password" \
    -q 1 \
    -v \
    -t "bluetti/result/$device_id/grid_charging_current_limit" \
    -t "bluetti/result/$device_id/grid_charge_on" \
    -t "bluetti/state/$device_id/grid_charging_current_limit" \
    -t "bluetti/state/$device_id/grid_charge_on"
