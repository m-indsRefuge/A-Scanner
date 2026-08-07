# A-Scanner V0.1 C02 Safety Hardening Design

## Status

Approved for planning on 2026-08-07.

## Goal

Harden A-Scanner's orchestration and evidence boundaries so `--check` remains repository-file read-only, `--apply` cannot accept repository state that was mutated outside the package-update phase, malformed configuration fails deterministically, and Git inspection failures cannot be mistaken for a clean/no-change result.

## Scope

C02 fixes concrete defects discovered during the repository-wide audit of branch `build/a-scanner-v0.1-c01-discovery-exclusion-repair` at `f1cae260d4a2a297e3c1558e2d36209afc9b2b6a`.

In scope:

1. Guard repository invariants around configured/discovered validation commands.
2. Make Git status inspection failures explicit rather than equivalent to "no changes".
3. Reject `--apply` when no supported locked project is detected.
4. Reject report destinations that resolve inside the target repository.
5. Validate configuration structure and warning regexes before execution.
6. Make rollback verification return a deterministic failure result when final Git inspection fails.
7. Add engine-level regression coverage for the above state transitions.
8. Finish the C01 exclusion-policy documentation/config alignment on the C02 branch.
9. Run repository-wide validation and CI before merge.

Out of scope:

- New package-manager adapters.
- Source-code migration or automated repair of target repositories.
- Runtime upgrades.
- Full uv `latest_compatible` normalization.
- Golden report/schema acceptance beyond regressions needed by the defects above.
- Scheduling, GitHub Action orchestration, MCP, or LLM integration.

Those remain V1 or post-V1 roadmap work.

## Safety invariants

### Repository read-only invariant for check mode

A `--check` run must not write files below the resolved target repository root. Default reports remain external. An explicit `--report-directory` that resolves to the repository root or any descendant is rejected during preflight.

### Apply-mode project invariant

`--apply` requires at least one supported locked uv or npm project. If discovery returns none, the run fails preflight with a non-zero CLI result rather than returning `check_completed`.

### Validation integrity invariant

Validation commands are trusted executable commands, but their effects are not implicitly accepted as dependency-update changes.

Before each validation phase, A-Scanner records the expected Git `HEAD` and status boundary. After the validation phase completes, it re-inspects Git state. The following are failures:

- `HEAD` changed during validation.
- Baseline validation dirtied a repository that was clean at intake.
- Post-update validation changed repository files beyond the state produced by the package-update phase.
- Git state cannot be inspected after validation.

For baseline failures, A-Scanner does not attempt dependency updates. For post-update integrity failures, A-Scanner uses the existing rollback path and records the failure in report events.

### Git inspection invariant

A Git inspection error must remain distinguishable from an empty change set. `changed_files()` must not silently convert a failed `git status` command into `[]`.

The preferred design is to raise `GitGuardError` when status inspection fails and let the engine classify that as a controlled failure. Callers that truly need a best-effort result must opt into that behavior explicitly; C02 does not add such a mode.

### Rollback invariant

Rollback verification is a boolean boundary. If reset or clean fails, or if the final Git inspection fails, `rollback()` returns `False`. It must not propagate a verification-time `GitGuardError` past the rollback boundary.

### Configuration invariant

Malformed `a-scanner.toml` input must produce deterministic `ConfigError` evidence rather than incidental `AttributeError`, `TypeError`, or regex compilation exceptions.

C02 validates:

- top-level TOML tables used by A-Scanner are mappings;
- `[scan].exclude` is an array of non-empty strings;
- `[warning].patterns` is an array of non-empty strings;
- each warning pattern compiles as a valid regular expression;
- `[[validation.commands]]` is an array of tables;
- each command has a non-empty string `argv` array;
- optional command `name` and `cwd` values resolve to strings without permitting invalid container types.

The public schema version remains `1`.

## Architecture

### Engine orchestration

`engine.execute()` remains the single state-machine owner. C02 adds small Git-state verification helpers rather than distributing orchestration logic into adapters.

Proposed flow for apply mode:

```text
PREFLIGHT
  -> PROJECT DISCOVERY
  -> INVENTORY BEFORE
  -> CAPTURE BASELINE GIT STATE
  -> BASELINE VALIDATION
  -> VERIFY BASELINE GIT INVARIANTS
  -> APPLY PACKAGE UPDATES
  -> CAPTURE POST-UPDATE GIT STATE
  -> INVENTORY AFTER
  -> POST-UPDATE VALIDATION
  -> VERIFY POST-VALIDATION GIT INVARIANTS
  -> ACCEPT OR ROLLBACK
  -> REPORT
```

The package adapters retain their existing responsibilities and public interfaces.

### Git guard

`git_guard.py` remains the source of truth for Git inspection, change enumeration, and rollback.

Changes are limited to:

- explicit failure from `changed_files()` when `git status` fails;
- rollback verification catching `GitGuardError` and returning `False`;
- small comparison helpers only if they reduce duplication in `engine.py` without changing public behavior unnecessarily.

### Reporting boundary

`report.py` keeps persistence/rendering responsibilities. The repository-boundary validation belongs before persistence, preferably in engine preflight or a focused report-path resolver, so an invalid destination never reaches `persist_report()`.

The report schema stays at version `1` unless a new field becomes strictly necessary. C02 should prefer existing `events`, `status`, and validation evidence over schema expansion.

## Error classification

C02 preserves existing statuses where they accurately describe the failure:

- malformed config, invalid report path, unsupported apply target: `preflight_failed`;
- baseline command failure or baseline integrity violation: `baseline_failed`;
- post-update validation or post-validation integrity violation followed by verified rollback: `validation_failed_rolled_back`;
- failed rollback verification: `rollback_failed`.

No new status is introduced unless tests demonstrate that an existing status would materially misrepresent the state.

## Testing strategy

All behavior changes use red-green TDD.

### New engine coverage

Create `tests/test_engine.py` with fixture repositories and a controllable fake runner or narrowly patched command boundary. Tests must assert report status/events and Git invariants rather than internal helper implementation.

Required regression cases:

1. `--apply` equivalent engine execution fails preflight when no supported locked project exists.
2. Report directory equal to repository root is rejected.
3. Report directory nested below repository is rejected.
4. External report directory remains accepted.
5. Baseline validation command that modifies a tracked file causes baseline failure and prevents update execution.
6. Baseline validation command that changes `HEAD` causes baseline failure.
7. Post-update validation that adds unrelated repository changes triggers rollback.
8. Post-update validation that changes `HEAD` triggers rollback.
9. Git inspection failure after validation becomes controlled failure evidence.

### Git guard coverage

Extend `tests/test_git_guard.py`:

- `changed_files()` raises `GitGuardError` when status inspection fails;
- rollback returns `False` when final inspection fails.

### Config coverage

Extend `tests/test_config.py` with malformed table/container cases and invalid warning regexes. Every case must fail with `ConfigError` and a stable, user-readable message fragment.

### Existing coverage

All existing C01 discovery tests remain unchanged and must stay green.

## C01 documentation alignment

The C02 branch will absorb the unfinished Task 4 documentation work so no local uncommitted C01 file is required for completion.

Required updates:

- `a-scanner.toml`: repository additions only (`exclude = []`) with comments explaining canonical exclusions are automatic.
- `README.md`: project-discovery section documenting canonical exclusions, additive directory-name semantics, and no `.gitignore` interpretation.
- `docs/ARCHITECTURE.md`: canonical + configured exclusion flow into normalized pruning.
- `docs/V1-CONTRACT.md`: discovery exclusion rule and the C02 safety invariants where they are part of the public contract.
- `docs/SAFETY-MODEL.md`: clarify validation commands may execute arbitrary trusted repository tooling, but A-Scanner verifies Git integrity around them.

## Validation and acceptance

A C02 merge candidate must have fresh evidence for:

```text
uv sync --locked
uv run ruff check .
uv run ruff format --check .
uv run python -m compileall -q src tests
uv run pytest -W error
uv build
```

A read-only self-scan must then prove:

- exactly one root uv project is discovered;
- reports are written outside the repository;
- `HEAD` is unchanged;
- Git status is unchanged;
- no pytest cache warning occurs.

Finally, the pull request CI matrix must pass on Ubuntu and Windows for Python 3.12 and 3.13 before merge.

## Branching and isolation

Implementation branch: `build/a-scanner-v0.1-c02-safety-hardening`.

The branch starts from `f1cae260d4a2a297e3c1558e2d36209afc9b2b6a`. It is intentionally separate from the local C01 worktree so local uncommitted edits are not overwritten or incorporated accidentally.

## Completion criteria

C02 is complete only when:

- each identified concrete defect has a regression test that was observed failing before its fix;
- all regression and existing tests pass with warnings treated as errors;
- lint, format, compile, build, and self-scan acceptance gates pass;
- the PR CI matrix is green;
- documentation matches implemented behavior;
- no unrelated roadmap features are bundled into the milestone.
