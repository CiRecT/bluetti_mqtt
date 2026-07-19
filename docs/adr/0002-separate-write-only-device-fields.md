---
status: accepted
---

# Separate write-only device fields from telemetry fields

Write-only controls are registered separately from the readable device
structure while remaining accessible through the existing `BluettiDevice`
field and command interface. This prevents unreliable register reads from
being published as telemetry and gives write-only controls one place to own
addressing, conversion, validation, rate limits, and retry policy.
