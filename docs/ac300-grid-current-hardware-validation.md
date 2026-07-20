# AC300 grid charging current hardware validation

## Result

The operator reported successful completion of the controlled AC300 hardware
procedure on 2026-07-20. The test covered the 1 A, 5 A, and 10 A current limits
described in
[`ac300-grid-current-hardware-test.md`](ac300-grid-current-hardware-test.md).

The operator confirmed that the procedure worked as intended. This confirms the
hardware gate based on operator observation, including command acknowledgement,
the persistent app setting, charging behaviour at each requested limit, and the
separate shutdown command.

## Evidence boundary

No raw MQTT output, debug log, timestamped measurements, screenshots, or
machine-readable test record was retained. Exact observed current or power
values and the firmware versions active during the run therefore cannot be
independently reconstructed from repository artifacts.

This report is an operator attestation, not a reproducible measurement record.
It must not be used to claim validation across other AC300 devices or firmware
versions. The actuator remains experimental until broader operational evidence
supports removing that designation.

## Automated evidence

The deterministic test suite covers command validation, MODBUS request and
response handling, rate control, MQTT result/state publication, configuration,
and Home Assistant discovery without contacting live hardware. The physical
test supplements those checks; it does not replace them.
