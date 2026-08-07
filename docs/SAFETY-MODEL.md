# Safety Model

## Guarantees targeted by V1

- `--check` does not intentionally write repository files.
- Reports are stored outside the scanned repository; explicit in-repository report destinations
  are rejected.
- `--apply` stops on a dirty Git working tree.
- `--apply` requires at least one supported locked uv or npm project.
- Baseline validation must pass and preserve Git-visible state before updates.
- A baseline integrity violation restores the clean intake state before failure is reported.
- Native package updates may change only detected manifest/lockfile paths in Git-visible state and
  may not move `HEAD`.
- Post-update validation must pass and preserve the package-update Git-visible state before changes
  are accepted.
- Failed update, update-integrity, post-update validation, or post-update integrity checks trigger
  rollback to the intake state.
- A controlled exception after package update execution begins also triggers rollback.
- Git inspection failure is treated as an error, not as an empty change set.
- No source-code migration occurs.

## Validation integrity

Validation commands are trusted executable tooling and may run repository code. A successful exit
code alone is not enough for A-Scanner to accept their effects.

Before baseline and post-update validation, A-Scanner records the expected `HEAD` and a worktree
fingerprint. After validation it re-inspects Git and compares the fingerprint. The fingerprint
covers tracked changes plus non-ignored untracked paths and file contents, so a validation command
cannot silently alter an already-modified dependency file or add an unrelated Git-visible change.

A baseline integrity violation restores the repository to the clean intake `HEAD`. Verified
restoration is reported as `baseline_failed`; failed restoration is `rollback_failed`. A
post-update validation or integrity violation enters rollback. If Git cannot be inspected after
dependency updates, the run also enters rollback rather than assuming no changes occurred.

## Package-update integrity

Package managers may run lifecycle hooks and build/install code, so successful process exit is not
by itself sufficient evidence that their repository effects are acceptable.

After native package updates complete, A-Scanner verifies that `HEAD` still matches the intake
commit and that every Git-visible changed path is one of the detected project's manifest or
lockfile paths. Unexpected Git-visible paths, a moved `HEAD`, failed Git inspection, failed updater
commands, and controlled exceptions after updates begin all enter rollback.

Ignored package environments remain outside this Git-visible integrity boundary because they are
also outside Git rollback guarantees.

## Boundaries

A-Scanner is not a sandbox. Package managers may execute build backends, install hooks, lifecycle
scripts, and repository code. Configured validation commands can also execute arbitrary trusted
repository tooling.

Ignored directories are not part of the Git-visible validation fingerprint and are not restored by
Git rollback. `.venv`, `node_modules`, caches, and other ignored package environments can change
during a run.

Network registries are mutable external inputs, so two runs at different times can discover
different available versions even when repository state is unchanged. Determinism applies to the
decision rules and recorded evidence, not to external registry state.

A-Scanner's rollback guarantee is Git-scoped. A validation or package-manager process can still
have effects outside the repository, modify ignored environments, contact networks, or interact
with other system resources permitted to that process.

Report persistence also depends on the operating system allowing A-Scanner to create and write the
selected external evidence directory. An external filesystem failure is outside the repository
rollback guarantee.

## Trust policy

Use `--apply` only when:

- The repository is trusted.
- Registry configuration is trusted.
- Validation commands have been reviewed.
- A complete Git clone or other recovery path exists.

Use `--check` only against repositories whose package-manager metadata inspection is trusted to run
under the current user account. A-Scanner does not sandbox package-manager inspection commands.
