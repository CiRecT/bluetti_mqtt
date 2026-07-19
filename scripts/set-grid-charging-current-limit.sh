#!/usr/bin/env bash
set -euo pipefail

usage() {
    echo "Usage: $0 AC300-<serial> <1-10>" >&2
}

if [[ $# -ne 2 ]]; then
    usage
    exit 2
fi

device_id=$1
limit=$2

if [[ ! $device_id =~ ^AC300-[0-9]+$ ]]; then
    echo 'Device ID must have the form AC300-<numeric serial>.' >&2
    exit 2
fi

if [[ ! $limit =~ ^([1-9]|10)$ ]]; then
    echo 'Grid charging current limit must be an integer from 1 through 10 A.' >&2
    exit 2
fi

if ! command -v mosquitto_pub >/dev/null 2>&1; then
    echo 'mosquitto_pub is required (Debian package: mosquitto-clients).' >&2
    exit 127
fi

mqtt_host=${MQTT_HOST:-192.168.178.31}
mqtt_port=${MQTT_PORT:-1885}
mqtt_username=${MQTT_USERNAME:-mqttuser}
topic="bluetti/command/$device_id/grid_charging_current_limit"

echo "Target: $device_id via $mqtt_host:$mqtt_port" >&2
echo "Command: set grid charging current limit to $limit A" >&2
echo 'This publishes a non-retained physical-device command.' >&2
read -r -p 'Type SET to continue: ' confirmation
if [[ $confirmation != 'SET' ]]; then
    echo 'Cancelled.' >&2
    exit 1
fi

if [[ -n ${MQTT_TEST_PASSWORD:-} ]]; then
    mqtt_password=$MQTT_TEST_PASSWORD
else
    read -r -s -p 'MQTT password: ' mqtt_password
    echo
fi

trap 'unset mqtt_password MQTT_TEST_PASSWORD' EXIT

mosquitto_pub \
    -h "$mqtt_host" \
    -p "$mqtt_port" \
    -u "$mqtt_username" \
    -P "$mqtt_password" \
    -q 1 \
    -t "$topic" \
    -m "$limit"

echo 'Command published. Require a fresh applied result before enabling Grid Charging.' >&2
