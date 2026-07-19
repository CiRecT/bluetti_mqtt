# Bluetti MQTT

This context describes control and telemetry concepts shared between Bluetti
power stations, MQTT clients, and external automation systems.

## Language

**Grid charging current limit**:
The maximum current in amperes that a power station may draw from the grid for
battery charging; it is not a guaranteed charging power.
_Avoid_: Grid charging power, AC charging power setting

**Acknowledged grid charging current limit**:
The most recent grid charging current limit for which the power station
returned a valid MODBUS write response; it is not a measured charging current.
_Avoid_: Actual grid charging current, read-back value

**Grid charging command result**:
A transient outcome event stating whether one grid charging current limit
command was applied or failed.
_Avoid_: Grid charging state, read-back value

**Grid charging current update interval**:
The configured minimum time between attempts to apply grid charging current
limits; it is never shorter than ten seconds.
_Avoid_: Polling interval, PV controller cycle

**PV surplus controller**:
An external automation component that determines a grid charging current limit
from PV generation, site consumption, and other energy-management inputs.
_Avoid_: Built-in PV controller

**Authoritative grid charging controller**:
The sole automation component allowed to issue grid charging current limit
commands for a power station.
_Avoid_: Competing controller, secondary writer
