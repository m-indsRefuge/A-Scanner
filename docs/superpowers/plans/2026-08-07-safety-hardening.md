# A-Scanner V0.1 C02 Safety Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Repair the concrete orchestration, Git-integrity, report-boundary, configuration-validation, and rollback defects found in the repository-wide audit while preserving the deterministic uv/npm V0.1 contract.

**Architecture:** Keep `engine.execute()` as the orchestration owner, `git_guard.py` as the Git source of truth, and `config.py` as the configuration validation boundary. Add a deterministic worktree fingerprint so validation integrity checks compare actual tracked/non-ignored-untracked content rather than only porcelain status. Preserve report schema version `1` and existing adapters.

**Tech Stack:** Python 3.12+, `uv`, `pytest`, `ruff`, Git, GitHub Actions on Windows/Linux and Python 3.12/3.13.

## Global Constraints

- Branch: `build/a-scanner-v0.1-c02-safety-hardening`.
- Base commit: `f1cae260d4a2a297e3c1558e2d36209afc9b2b6a` plus approved C02 spec/plan commits only.
- Approved design: `docs/superpowers/specs/2026-08-07-safety-hardening-design.md`.
- Preserve uv/npm manifest-lockfile detection, adapter command semantics, CLI arguments, report schema version `1`, and C01 discovery behavior.
- No new runtime dependencies.
- Use red-green TDD for every production behavior change.
- Use a draft PR against `build/a-scanner-v0.1-c01-discovery-exclusion-repair` as the runtime red/green gate because this web session does not execute the repository locally.
- Do not merge until repository validation, self-scan acceptance, and the complete Windows/Linux × Python 3.12/3.13 CI matrix are green.

## File Structure

- Modify `src/a_scanner/git_guard.py`: explicit status failure, deterministic repository fingerprint, rollback verification containment.
- Modify `src/a_scanner/config.py`: structural validation and warning-regex validation.
- Modify `src/a_scanner/engine.py`: report-path preflight, apply-project preflight, validation integrity checks and rollback classification.
- Create `tests/test_engine.py`: orchestration regression coverage.
- Modify `tests/test_git_guard.py`: Git failure/fingerprint/rollback regressions.
- Modify `tests/test_config.py`: malformed configuration regressions.
- Modify `a-scanner.toml`, `README.md`, `docs/ARCHITECTURE.md`, `docs/V1-CONTRACT.md`, `docs/SAFETY-MODEL.md`: finish C01 alignment and document C02 safety boundaries.

---

### Task 1: Establish Git-guard red regressions

**Files:**
- Modify: `tests/test_git_guard.py`

**Interfaces:**
- Consumes: `changed_files(root, runner)`, `rollback(root, expected_head, runner)`, `inspect_git(root, runner)`.
- Produces: red evidence for explicit status failure, rollback verification containment, and content fingerprint behavior.

- [ ] **Step 1: Add a minimal scripted runner fixture**

Add a test-only runner whose `run()` returns supplied `CommandResult` objects in sequence. Keep it in `tests/test_git_guard.py`.

- [ ] **Step 2: Add failing status-inspection test**

Add:

```python
def test_changed_files_raises_when_git_status_fails(tmp_path: Path) -> None:
    runner = ScriptedRunner(
        CommandResult(
            argv=["git", "status"],
            cwd=str(tmp_path),
            exit_code=1,
            stdout="",
            stderr="status failed",
            duration_seconds=0.0,
        )
    )

    with pytest.raises(GitGuardError, match="working-tree change"):
        changed_files(tmp_path, runner)
```

- [ ] **Step 3: Add failing rollback-verification test**

Use a real temporary Git repository, monkeypatch `a_scanner.git_guard.inspect_git` to raise `GitGuardError` only at the final verification call, and assert `rollback(...) is False`.

- [ ] **Step 4: Add fingerprint behavior tests**

Define the required interface in tests as:

```python
fingerprint = fingerprint_worktree(root, runner)
```

Prove the fingerprint changes when:

1. tracked file contents change while `git status` path classification stays the same;
2. a non-ignored untracked file's contents change without changing its path.

- [ ] **Step 5: Commit red tests**

Commit message:

```text
test: reproduce Git integrity failures
```

- [ ] **Step 6: Open draft PR and verify red CI**

Open a draft PR from C02 to C01 and verify the CI failures are limited to the new Git-guard assertions. Do not implement until the red failures are observed.

---

### Task 2: Implement Git-guard integrity primitives

**Files:**
- Modify: `src/a_scanner/git_guard.py`

**Interfaces:**
- Produces: `fingerprint_worktree(root: Path, runner: CommandRunner) -> str`.
- Changes: `changed_files()` raises `GitGuardError` when `git status` fails; `rollback()` returns `False` when final inspection raises.

- [ ] **Step 1: Make `changed_files()` explicit on status failure**

Replace the silent `return []` branch with:

```python
raise GitGuardError("Unable to inspect Git working-tree changes.")
```

- [ ] **Step 2: Add deterministic fingerprint helper**

Implement `fingerprint_worktree()` with `hashlib.sha256()` over:

1. current `HEAD` text;
2. `git diff --binary --no-ext-diff HEAD` output;
3. sorted non-ignored untracked paths from `git ls-files --others --exclude-standard -z`;
4. each untracked path plus its file bytes when it is a regular file.

Every Git command failure raises `GitGuardError`. Hash relative path text using UTF-8 with surrogate-safe replacement. Do not include ignored directories.

- [ ] **Step 3: Contain rollback verification failure**

Wrap only the final `inspect_git()` verification in `try/except GitGuardError` and return `False` on that exception.

- [ ] **Step 4: Verify green CI**

Push implementation commit:

```text
fix: harden Git state inspection
```

Verify the draft PR CI becomes green before continuing.

---

### Task 3: Establish malformed-configuration red regressions

**Files:**
- Modify: `tests/test_config.py`

**Interfaces:**
- Consumes: `load_config(repository, config_path)`.
- Produces: deterministic `ConfigError` requirements for malformed tables, warning patterns, and validation entries.

- [ ] **Step 1: Add malformed table cases**

Parameterize TOML inputs covering:

```toml
scan = "invalid"
warning = "invalid"
validation = "invalid"
```

Each must raise `ConfigError` with the corresponding table name.

- [ ] **Step 2: Add warning pattern cases**

Cover:

```toml
[warning]
patterns = "deprecated"
```

and arrays containing `""`, whitespace-only values, non-string values, and invalid regex such as `"["`.

- [ ] **Step 3: Add validation command container cases**

Cover non-array `commands`, non-table command entries, empty/non-string argv elements, and invalid `name`/`cwd` container values. Assert stable `ConfigError` message fragments.

- [ ] **Step 4: Commit red tests and verify red CI**

Commit:

```text
test: reproduce malformed configuration failures
```

Verify only the new config assertions fail.

---

### Task 4: Implement strict configuration validation

**Files:**
- Modify: `src/a_scanner/config.py`

**Interfaces:**
- Public `load_config()` signature unchanged.

- [ ] **Step 1: Validate tables before `.get()` use**

Use `collections.abc.Mapping` and a focused helper:

```python
def _table(data: Mapping[str, object], key: str) -> Mapping[str, object]:
    value = data.get(key, {})
    if not isinstance(value, Mapping):
        raise ConfigError(f"[{key}] must be a table.")
    return value
```

- [ ] **Step 2: Validate warning patterns**

Require an array of non-empty strings. Compile each with `re.compile(pattern, re.IGNORECASE)` inside `load_config()` and convert `re.error` into `ConfigError` naming the invalid entry.

- [ ] **Step 3: Validate validation commands**

Require `commands` to be a list, each entry to be a mapping, `argv` to be a non-empty list of non-empty strings, and optional `name`/`cwd` to be strings when present. Blank name falls back to `Validation N`; blank cwd falls back to `.`.

- [ ] **Step 4: Verify green CI**

Commit:

```text
fix: validate scanner configuration structure
```

Verify complete CI green before continuing.

---

### Task 5: Establish engine orchestration red regressions

**Files:**
- Create: `tests/test_engine.py`

**Interfaces:**
- Consumes: `execute(ScanOptions(...))`, `Mode`, report statuses/events.
- Produces: public-behavior regression coverage for report boundaries, apply preflight, and validation integrity.

- [ ] **Step 1: Add Git repository fixture helper**

Create a real temporary Git repo with configured fixture identity, one committed `tracked.txt`, and optional minimal `pyproject.toml`/`uv.lock` files. Use subprocess argument arrays only.

- [ ] **Step 2: Add report-boundary tests**

Assert:

- report directory equal to repository root -> `preflight_failed`, report persisted to default external location rather than requested path;
- report directory below repository -> same;
- external report directory -> accepted in check mode.

Monkeypatch `a_scanner.engine.default_report_directory` to a test-owned external directory so evidence location is deterministic.

- [ ] **Step 3: Add apply-without-project test**

Run `Mode.APPLY` on a clean Git repository with no locked uv/npm project and assert `preflight_failed` plus an event stating apply requires a supported locked project.

- [ ] **Step 4: Add baseline integrity tests**

Use a minimal uv project and monkeypatch `a_scanner.engine.UvAdapter` with a test adapter that returns a simple `ProjectRecord` without network/package-manager inspection. Configure validation commands that:

1. edit committed `tracked.txt`;
2. create an empty Git commit.

Assert `baseline_failed`, no adapter update call, and integrity event evidence.

- [ ] **Step 5: Add post-update integrity tests**

The fake adapter's update method changes a committed dependency file. Configure post-validation commands that:

1. alter `tracked.txt`;
2. alter a file already modified by the updater;
3. create an empty Git commit.

Assert the run does not accept the state and uses rollback; verified rollback -> `validation_failed_rolled_back`.

- [ ] **Step 6: Add post-validation Git-inspection failure test**

Monkeypatch the engine's Git inspection/fingerprint boundary so the post-validation verification raises `GitGuardError`. Assert controlled rollback classification rather than an uncaught exception.

- [ ] **Step 7: Commit red tests and verify red CI**

Commit:

```text
test: reproduce orchestration safety failures
```

Verify red failures correspond only to these new C02 behaviors.

---

### Task 6: Implement engine safety boundaries

**Files:**
- Modify: `src/a_scanner/engine.py`

**Interfaces:**
- Consumes `fingerprint_worktree()` from Task 2.
- Public `execute()` and `ScanOptions` signatures unchanged.

- [ ] **Step 1: Validate requested report path after Git-root resolution**

Add:

```python
def _report_directory_is_inside_repository(repository: Path, directory: Path) -> bool:
    resolved = directory.expanduser().resolve()
    return resolved == repository or repository in resolved.parents
```

When invalid, append a preflight event and call `_finish(..., report_directory=None)` so failure evidence goes to the default external location.

- [ ] **Step 2: Enforce apply project preflight**

When discovery is empty:

- check mode -> preserve `check_completed`;
- apply mode -> keep `preflight_failed`, add explicit event, finish.

- [ ] **Step 3: Verify baseline validation integrity**

Before baseline validation capture expected `HEAD` and `fingerprint_worktree()`. After validation, inspect Git and fingerprint again. Command failure remains `baseline_failed`. A changed HEAD or changed fingerprint is also `baseline_failed`, records an integrity event, and prevents update execution.

- [ ] **Step 4: Verify post-update validation integrity**

After package updates and before post-validation capture expected HEAD and fingerprint. After post-validation, re-inspect. If command validation fails or HEAD/fingerprint differs, call rollback and classify as `validation_failed_rolled_back` or `rollback_failed`.

- [ ] **Step 5: Keep Git inspection errors controlled**

Allow `GitGuardError` from changed-file/fingerprint inspection to flow into existing controlled exception handling before updates; after updates, catch verification errors at the post-validation boundary and attempt rollback because repository mutation may already exist.

- [ ] **Step 6: Verify green CI**

Commit:

```text
fix: enforce orchestration safety invariants
```

Verify complete draft PR CI green.

---

### Task 7: Finish C01/C02 documentation alignment

**Files:**
- Modify: `a-scanner.toml`
- Modify: `README.md`
- Modify: `docs/ARCHITECTURE.md`
- Modify: `docs/V1-CONTRACT.md`
- Modify: `docs/SAFETY-MODEL.md`

**Interfaces:**
- Documentation only; no behavior changes.

- [ ] **Step 1: Make repository exclusion config additive-only**

Use:

```toml
[scan]
# Canonical environment, cache, test-workspace, and build exclusions are automatic.
# Add repository-specific directory names here; entries are matched by directory name.
exclude = []
```

- [ ] **Step 2: Add README project-discovery contract**

Document all canonical C01 exclusions, additive directory-name matching, and no `.gitignore` parsing.

- [ ] **Step 3: Add architecture flow**

Document canonical + configured exclusions -> normalized pruning, plus validation Git fingerprint checkpoints around baseline/post-update validation.

- [ ] **Step 4: Update V1 contract**

Document discovery exclusions, apply requires a supported locked project, explicit report destinations cannot be inside the repository, and validation commands cannot silently contribute accepted repository changes.

- [ ] **Step 5: Update safety model**

Clarify validation commands may execute trusted repository tooling, but A-Scanner fingerprints Git-visible state around validation and rejects/rolls back unexpected mutation.

- [ ] **Step 6: Commit documentation**

Commit:

```text
docs: define scanner safety boundaries
```

---

### Task 8: Full acceptance and CI closeout

**Files:**
- No source changes expected.

- [ ] **Step 1: Confirm complete PR diff**

Review changed filenames and per-file patches. Reject unrelated changes.

- [ ] **Step 2: Verify CI matrix**

Require all four matrix combinations to pass:

- Ubuntu / Python 3.12
- Ubuntu / Python 3.13
- Windows / Python 3.12
- Windows / Python 3.13

The workflow itself runs sync, Ruff lint, Ruff format check, pytest, and build.

- [ ] **Step 3: Run local acceptance gate where repository execution is available**

Run:

```text
uv sync --locked
uv run ruff check .
uv run ruff format --check .
uv run python -m compileall -q src tests
uv run pytest -W error
uv build
```

If this web session cannot execute the repository, do not claim this local gate; use CI as executed evidence and require the PowerShell acceptance command locally before merge.

- [ ] **Step 4: Read-only self-scan acceptance**

Run `a-scan <repo> --check` with an external report directory and prove exactly one uv project, external report paths, unchanged HEAD, unchanged status, and zero warnings.

- [ ] **Step 5: Final branch review**

Invoke `superpowers:verification-before-completion`, then `superpowers:finishing-a-development-branch`. Do not merge until every required executed gate has evidence.
