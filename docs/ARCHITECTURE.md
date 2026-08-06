# Architecture

```text
CLI
 |
 v
Engine
 +-- Git guard
 +-- Project detector
 +-- uv adapter
 +-- npm adapter
 +-- Warning parser
 +-- Validation runner
 +-- Report writer
```

## Deterministic core

The engine owns orchestration and state transitions. Adapters only translate native package
manager data and commands into the shared report model.

The JSON report is the future agent boundary. An LLM or orchestration agent may later invoke
A-Scanner and reason over the evidence, but it does not participate in scanning, updating,
validation, or rollback.

## State flow

```text
PREFLIGHT
  -> INVENTORY_BEFORE
  -> BASELINE_VALIDATION
  -> APPLY (only in --apply)
  -> INVENTORY_AFTER
  -> POST_VALIDATION
  -> ACCEPT or ROLLBACK
  -> REPORT
```

All subprocess calls are made with explicit argument arrays. Validation commands are not executed
through a shell.
