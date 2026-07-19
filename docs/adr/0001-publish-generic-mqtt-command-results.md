---
status: accepted
---

# Publish generic MQTT command results

Every writable MQTT field publishes a transient result event after a command
is rejected, applied, or fails. A generic result path avoids special-case
acknowledgement plumbing for grid charging controls and lets automation clients
distinguish adapter validation failures from device or transport failures while
preserving the existing command topics.
