# Safety Model

## Guarantees targeted by V1

- `--check` does not intentionally write repository files.
- `--apply` stops on a dirty Git working tree.
- Baseline validation must pass before updates.
- Post-update validation must pass before changes are accepted.
- Failed post-update validation triggers tracked-state rollback.
- Reports are stored outside the scanned repository by default.
- No source-code migration occurs.

## Boundaries

A-Scanner is not a sandbox. Package managers may execute build backends, install hooks, lifecycle
scripts, and repository code.

Ignored directories are not restored by Git rollback. `.venv`, `node_modules`, caches, and other
ignored package environments can change during a run.

Network registries are mutable external inputs, so two runs at different times can discover
different available versions even when repository state is unchanged. Determinism applies to the
decision rules and recorded evidence, not to external registry state.

## Trust policy

Use `--apply` only when:

- The repository is trusted.
- Registry configuration is trusted.
- Validation commands have been reviewed.
- A complete Git clone or other recovery path exists.
