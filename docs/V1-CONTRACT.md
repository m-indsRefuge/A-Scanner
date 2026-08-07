# A-Scanner V1 Contract

## Purpose

A-Scanner is a deterministic CLI tool that inspects a Git repository, reports dependency and
deprecation state, applies latest-compatible dependency updates for supported ecosystems, runs
validation, and produces evidence.

## Supported ecosystem contract

V1 supports only:

- `uv`: a project directory containing both `pyproject.toml` and `uv.lock`
- `npm`: a project directory containing both `package.json` and `package-lock.json`

Unsupported manifests are reported but not modified. `--apply` requires at least one supported
locked uv or npm project; an unsupported or empty target fails preflight.

## Discovery exclusion rule

A-Scanner prunes canonical environment, package-manager, cache, test-workspace, and build
directory names before recursive project detection. Repository `[scan].exclude` entries extend
that canonical list and cannot remove built-in exclusions.

Exclusion matching uses platform path-case semantics and exact immediate directory names. Entries
are not paths or glob patterns. V1 does not read or interpret `.gitignore` files for discovery.

## Commands

```text
a-scan <repository> --check
a-scan <repository> --apply
```

`--check` is repository-file read-only. It may contact registries and read or populate package
manager caches. Reports are written outside the target repository. An explicit report directory
that resolves to the repository root or a descendant is rejected; preflight evidence is then
written to the default external report location.

`--apply` may change dependency manifests, lockfiles, and ignored package environments.

## Compatible-update rule

A-Scanner delegates compatibility resolution to the native package manager:

- `uv lock --upgrade`
- `npm update --save`

A-Scanner does not rewrite runtime constraints, deliberately cross incompatible major-version
boundaries, replace dependencies, or edit application source code.

## Compatibility-ceiling evidence

For npm, registry output differentiates `wanted` from `latest`. When they differ, A-Scanner records
a compatibility ceiling.

For uv, the V0.1 adapter records the latest-version information exposed by `uv tree --outdated`.
Full normalized compatibility-ceiling classification remains a V1 hardening task.

## Validation rule

A configured validation command is an argument array and optional working directory. A command
passes only when its process exit code is zero. Configuration structure and warning regular
expressions are validated before execution.

If no commands are configured, A-Scanner discovers conservative commands from supported project
metadata. `--apply` refuses to continue when no validation command can be established.

Validation commands may run trusted repository tooling, but their Git-visible side effects are not
implicitly accepted. A-Scanner fingerprints `HEAD`, tracked changes, and non-ignored untracked file
paths and contents around baseline and post-update validation.

- Baseline validation must leave the pre-update Git-visible state unchanged. A changed `HEAD`,
  changed fingerprint, or failed Git integrity inspection causes `baseline_failed` and prevents
  dependency updates.
- Post-update validation must leave the package-update Git-visible state unchanged. A validation
  command failure, changed `HEAD`, changed fingerprint, or failed Git change/integrity inspection
  enters rollback.

Ignored package environments are outside this Git-visible integrity comparison.

## Rollback rule

`--apply` requires an initially clean Git working tree. On post-update validation or validation
integrity failure, A-Scanner:

1. Records available failure and integrity evidence.
2. Resets tracked files to the original `HEAD`.
3. Removes untracked, non-ignored files created during the run.
4. Verifies that `HEAD` and Git status match the initial clean state.
5. Writes the evidence report outside the target repository.

A failure of reset, clean, or final Git verification yields `rollback_failed`. Final rollback
verification errors are contained at the rollback boundary rather than escaping as an unhandled
exception.

Ignored environments are outside the rollback guarantee.

## Non-goals

V1 does not:

- Use an LLM
- Repair source code
- Upgrade Python or Node runtimes
- Replace abandoned packages
- Commit, push, open pull requests, or merge
- Schedule itself
- Support package managers other than uv and npm
- Guarantee that a warning can be mapped to one dependency
