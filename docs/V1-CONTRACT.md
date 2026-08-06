# A-Scanner V1 Contract

## Purpose

A-Scanner is a deterministic CLI tool that inspects a Git repository, reports dependency and
deprecation state, applies latest-compatible dependency updates for supported ecosystems, runs
validation, and produces evidence.

## Supported ecosystem contract

V1 supports only:

- `uv`: a project directory containing both `pyproject.toml` and `uv.lock`
- `npm`: a project directory containing both `package.json` and `package-lock.json`

Unsupported manifests are reported but not modified.

## Commands

```text
a-scan <repository> --check
a-scan <repository> --apply
```

`--check` is repository-file read-only. It may contact registries and read or populate package
manager caches.

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
passes only when its process exit code is zero.

If no commands are configured, A-Scanner discovers conservative commands from supported project
metadata. `--apply` refuses to continue when no validation command can be established.

## Rollback rule

`--apply` requires an initially clean Git working tree. On post-update validation failure,
A-Scanner:

1. Records the failed command outputs.
2. Resets tracked files to the original `HEAD`.
3. Removes untracked, non-ignored files created during the run.
4. Verifies that `HEAD` and Git status match the initial clean state.
5. Writes the evidence report outside the target repository.

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
