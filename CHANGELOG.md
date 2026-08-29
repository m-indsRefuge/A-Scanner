# Changelog

All notable changes to A-Scanner are documented here.

## Unreleased

Security and robustness hardening from the 2026-08-29 external Meta AI code audit, independently verified against the live repository before remediation.

### Security

- Disable npm lifecycle scripts during `npm update` by default with `--ignore-scripts`; trusted repositories may opt in with `[npm].ignore_scripts = false`.
- Fail closed when non-ignored untracked files larger than 100 MiB would make worktree fingerprinting unbounded rather than silently omitting their contents.
- Write JSON/text reports through atomic same-directory replacement and restrict report permissions to `0600` where POSIX permission semantics are available.
- Bound configured warning regex length, reject obvious nested-repeat forms, and cache compiled patterns.
- Resolve executable paths from the parent process PATH before applying command-specific environment overrides.

### Fixed

- Reject a missing explicitly requested `--config` file instead of silently falling back to defaults.
- Convert invalid/unreadable npm `package.json` and `package-lock.json` input into deterministic inventory failures instead of uncaught JSON errors.
- Treat unrecognized uv outdated JSON as unavailable inventory with preserved command evidence instead of silently reporting zero outdated dependencies.
- Parse NUL-delimited Git status output so rename/copy records use the destination path correctly.
- Fail with a Git guard error when detected project manifest/lockfile paths escape the repository.
- Discover Ruff validation from actual `[tool.ruff]` TOML configuration instead of plain-text substring matches.
- Honor repository-relative scan exclusions such as `packages/legacy` in addition to basename exclusions.
- Clarify that a rejected in-repository report destination falls back to the default external report directory for its failure report.

### Validation

The hardening branch is covered by regression tests for the externally reported edge cases and cross-platform CI on Windows and Ubuntu with Python 3.12 and 3.13.

## 0.1.1 — 2026-08-28

A-Scanner V0.1.1 hardens real-world Windows/npm behavior and repository-boundary safety without changing the project's deterministic design.

### Fixed

- Resolve Windows executable shims before subprocess execution while preserving argument-array execution with `shell=False`.
- Fail closed when npm inventory output is malformed, contains a top-level error, or otherwise cannot be trusted.
- Re-run npm inventory after updates and roll the repository back when post-update inventory cannot be verified.
- Accept valid array-shaped detail records from `npm outdated --json` and normalize them without inventing conflicting version values.
- Exclude `.worktrees` from recursive discovery by default so a scan of one Git working tree does not silently cross into linked worktrees.

### Improved

- Render dependency inventory failures as unavailable rather than as misleading zero-update results.
- Make direct updates, compatibility ceilings, transitive updates, and result status clearer in human-readable reports.

### Validation

V0.1.1 was exercised with cross-platform CI on Windows and Linux using Python 3.12 and 3.13, plus live read-only and controlled apply acceptance runs against real uv, npm, and mixed repositories.

## 0.1.0 — 2026-08-07

Initial deterministic A-Scanner baseline.

### Added

- Recursive discovery of locked Python/uv and Node/npm projects.
- Read-only `--check` mode.
- Controlled latest-compatible `--apply` mode.
- Clean-Git enforcement before mutation.
- Baseline and post-update validation gates.
- Repository fingerprinting around validation and package-manager execution.
- Verified rollback when apply-mode validation or integrity checks fail.
- Human-readable text reports and versioned JSON evidence.
- Configurable validation commands using argument arrays rather than shell command strings.
- External report storage so read-only scans do not modify target repositories.

## Project status

A-Scanner is alpha-quality software. The current release intentionally supports a narrow deterministic scope: locked uv/Python projects, locked npm/Node projects, and mixed repositories containing both. It does not use an LLM at runtime, rewrite application source code, cross declared compatibility ceilings, commit, or push target repositories.
