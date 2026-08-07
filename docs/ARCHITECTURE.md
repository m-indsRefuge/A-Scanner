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
  -> PROJECT_DISCOVERY
  -> INVENTORY_BEFORE
  -> BASELINE_GIT_FINGERPRINT
  -> BASELINE_VALIDATION
  -> BASELINE_INTEGRITY_CHECK
  -> APPLY (only in --apply)
  -> INVENTORY_AFTER
  -> POST_UPDATE_GIT_FINGERPRINT
  -> POST_VALIDATION
  -> POST_VALIDATION_INTEGRITY_CHECK
  -> ACCEPT or ROLLBACK
  -> REPORT
```

All subprocess calls are made with explicit argument arrays. Validation commands are not executed
through a shell.

## Discovery exclusions

Configuration produces one effective exclusion tuple before project discovery begins. Canonical
transient-directory exclusions are always present, and validated repository-specific names are
appended with deterministic de-duplication.

```text
canonical exclusions
        +
configured additions
        |
        v
normalized exclusion set
        |
        v
os.walk directory pruning
        |
        v
uv/npm manifest-lockfile detection
```

The detector normalizes exclusion and candidate directory names with `os.path.normcase()` and
prunes exact-name matches before descent. It does not parse `.gitignore`, path globs, or negation
rules.

## Git integrity around validation

Validation commands are trusted executable tooling but are not allowed to silently contribute
changes to an accepted dependency-update result. The engine fingerprints Git-visible repository
state immediately before each validation phase and verifies it afterwards.

The fingerprint includes the current `HEAD`, the binary tracked diff from `HEAD`, and the paths and
contents of non-ignored untracked files. This detects a validation command that changes an already
modified dependency file as well as new unrelated changes. Ignored environments are intentionally
outside this fingerprint because they are also outside Git rollback guarantees.

Baseline integrity failure stops before dependency updates. Post-update validation or integrity
failure enters the rollback path. A Git inspection failure is treated as an error rather than as an
empty change set.

## Report persistence boundary

Reports are external evidence. After the target Git root is resolved, the engine rejects an
explicit report directory equal to or below that repository. The corresponding preflight failure
report is persisted through the default external report directory instead of the rejected path.
