---
status: accepted
---

# Use explicit versioned YAML configuration

Optional configuration files use a strict, versioned YAML schema selected only
through `--config`. YAML mode obtains all runtime settings from the file and
does not mix them with CLI configuration, while the existing CLI-only mode
remains backward compatible; Pydantic validates the schema after safe YAML
parsing so future device-specific settings can evolve without ambiguous legacy
heuristics.
