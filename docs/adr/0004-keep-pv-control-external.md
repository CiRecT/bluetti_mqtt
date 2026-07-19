---
status: accepted
---

# Keep PV surplus control external

`bluetti_mqtt` exposes validated, acknowledged grid charging actuators but does
not calculate PV surplus, schedule delayed setpoints, or enforce a controller
watchdog. One authoritative external controller owns the regulation strategy
and explicitly controls the independent charging-current limit and grid-charge
switch; device settings are not automatically reset when that controller stops.
