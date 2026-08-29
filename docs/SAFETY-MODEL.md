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
- npm lifecycle scripts are disabled during A-Scanner's `npm update` by default.
- Post-update validation must pass and preserve the package-update Git-visible state before changes
  are accepted.
- Failed update, update-integrity, post-update validation, or post-update integrity checks trigger
  rollback to the intake state.
- A controlled exception after package update execution begins also triggers rollback.
- Git inspection failure is treated as an error, not as an empty change set.
- Untracked files larger than 100 MiB fail worktree fingerprinting closed rather than being silently
  omitted from the integrity model.
- No source-code migration occurs.

## Validation integrity

Validation commands are trusted executable tooling and may run repository code. A successful exit
code alone is not enough for A-Scanner to accept their effects.

Before baseline and post-update validation, A-Scanner records the expected `HEAD` and a worktree
fingerprint. After validation it re-inspects Git and compares the fingerprint. The fingerprint
covers tracked changes plus non-ignored untracked paths and file contents. Oversized untracked
files are rejected before validation rather than skipped, because skipping their contents would
weaken the integrity claim.

A baseline integrity violation restores the repository to the clean intake `HEAD`. Verified
restoration is reported as `baseline_failed`; failed restoration is `rollback_failed`. A
post-update validation or integrity violation enters rollback. If Git cannot be inspected after
dependency updates, the run also enters rollback rather than assuming no changes occurred.

## Package-update integrity

Package managers may run build/install code. A-Scanner passes `--ignore-scripts` to `npm update` by
default so npm `preinstall`, `install`, and `postinstall` lifecycle scripts are not run by that
update step. Repositories that genuinely require those hooks may opt in with:

```toml
[npm]
ignore_scripts = false
```

Enabling lifecycle scripts expands the code-execution surface and is appropriate only for trusted
repositories and packages. Even with the default `ignore_scripts = true`, APPLY mode is **not a
sandbox**: package-manager operations, Python build backends, configured validation commands, and
repository tooling may still execute code.

After native package updates complete, A-Scanner verifies that `HEAD` still matches the intake
commit and that every Git-visible changed path is one of the detected project's manifest or
lockfile paths. Unexpected Git-visible paths, a moved `HEAD`, failed Git inspection, failed updater
commands, and controlled exceptions after updates begin all enter rollback.

Ignored package environments remain outside this Git-visible integrity boundary because they are
also outside Git rollback guarantees.

## Configuration and input hardening

An explicitly requested `--config` file must exist. A typo or missing explicit path fails preflight
instead of silently falling back to default configuration. The implicit repository-local
`a-scanner.toml` remains optional.

Configured warning regular expressions are bounded to 256 characters, must compile successfully,
and obvious nested-repeat forms are rejected. Compiled patterns are cached for bounded reuse. This
reduces regex resource-exhaustion risk; it is not a claim that arbitrary regular expressions are
formally proven safe.

Configured scan exclusions may be simple directory names or repository-relative path/glob patterns.
Canonical exclusions are always retained.

## Evidence persistence

JSON and text reports are written to same-directory temporary files, flushed, and atomically
replaced into their final names. On POSIX systems A-Scanner restricts report files to mode `0600`;
on Windows, POSIX permission bits do not express the full ACL model, so users must still protect
the selected report directory appropriately.

Reports can contain package-manager and validation stdout/stderr. Those external tools may emit
credentials or other sensitive values, so reports should be treated as potentially sensitive
evidence even though A-Scanner itself does not intentionally collect secrets.

## Boundaries

A-Scanner is not a sandbox. Package managers may execute build backends, install hooks, lifecycle
scripts when explicitly enabled, and repository code. Configured validation commands can also
execute arbitrary trusted repository tooling.

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
