# A-Scanner V0.1 C01 Discovery Exclusion Repair Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ensure A-Scanner discovers only real supported projects by always pruning canonical transient directories, merging repository-specific exclusions additively, and running its own tests without pytest cache warnings.

**Architecture:** `load_config()` will produce one validated, deterministic effective exclusion tuple composed of canonical defaults plus repository additions. `discover_projects()` will normalize that tuple once, prune matching directory names before traversal, and retain its current uv/npm detection and deterministic ordering. A repository-level integration test and an external self-scan acceptance gate will prove that A-Scanner reports only its root uv project.

**Tech Stack:** Python 3.12, `uv`, `pytest`, `ruff`, TOML via `tomllib`, Git, PowerShell 7 (`pwsh`).

## Global Constraints

- Milestone: `A-SCANNER-V0.1-C01-DISCOVERY-EXCLUSION-REPAIR`.
- Branch: `build/a-scanner-v0.1-c01-discovery-exclusion-repair`.
- Approved design: `docs/superpowers/specs/2026-08-06-discovery-exclusion-repair-design.md`.
- Start from branch commit `aab4c0d742b099d742e5bedc9fb970e8e96c6468` or a later plan-only descendant.
- Use an isolated Git worktree created through `superpowers:using-git-worktrees` before implementation.
- Target Python `>=3.12`; do not add runtime dependencies.
- Target PowerShell 7 for Windows validation commands.
- Preserve uv and npm manifest-lockfile detection rules.
- Preserve report schema version `1`, CLI arguments, rollback behavior, and all `--apply` behavior.
- Do not read `.gitignore` or implement ignore-pattern, glob, negation, or nested-ignore semantics.
- Canonical exclusions cannot be removed by repository configuration.
- Configured exclusions are directory names, not paths or glob patterns.
- Use TDD: establish the red failure before implementation, then obtain focused green evidence before each implementation commit.
- Do not merge the branch until the complete C01 acceptance contract passes with fresh evidence.

## File Structure

- Modify `src/a_scanner/config.py`: own canonical exclusions, validate configured additions, and construct the effective exclusion tuple.
- Modify `src/a_scanner/detector.py`: normalize exclusions and prune directories before descent.
- Modify `tests/test_config.py`: prove canonical defaults, additive merging, deterministic de-duplication, and invalid-input rejection.
- Modify `tests/test_detector.py`: prove transient-directory pruning, normalized matching, and preserved mixed-project detection.
- Create `tests/test_self_discovery.py`: prove the real A-Scanner repository resolves to exactly one root uv project even while pytest fixtures exist below `.pytest-tmp`.
- Modify `pyproject.toml`: retain repository-local `--basetemp` and disable pytest's cache provider.
- Modify `a-scanner.toml`: show only repository-specific additive exclusions.
- Modify `README.md`: document automatic canonical exclusions and additive configuration.
- Modify `docs/ARCHITECTURE.md`: document configuration-to-detector exclusion flow.
- Modify `docs/V1-CONTRACT.md`: make the exclusion behavior part of the V1 discovery contract.

---

### Task 1: Commit the red regression tests

**Files:**
- Modify: `tests/test_config.py`
- Modify: `tests/test_detector.py`

**Interfaces:**
- Consumes: existing `load_config(repository: Path, config_path: Path | None) -> ScannerConfig`; existing `discover_projects(repository: Path, excludes: tuple[str, ...]) -> list[DetectedProject]`.
- Produces: executable regression tests that define the required configuration and detector behavior before implementation.

- [ ] **Step 1: Confirm isolated branch intake**

Run from the isolated worktree:

```powershell
$expectedBranch = 'build/a-scanner-v0.1-c01-discovery-exclusion-repair'
$branch = (& git branch --show-current).Trim()
$head = (& git rev-parse HEAD).Trim()
$status = @(& git status --porcelain=v1 --untracked-files=all)

if ($branch -ne $expectedBranch) {
    throw "Unexpected branch: $branch"
}

if ($status.Count -ne 0) {
    $status | Write-Output
    throw 'C01 must start from a clean worktree.'
}

Write-Output "Branch: $branch"
Write-Output "HEAD:   $head"
```

Expected: branch is `build/a-scanner-v0.1-c01-discovery-exclusion-repair`; working tree is clean.

- [ ] **Step 2: Extend configuration imports and add red tests**

Change the import in `tests/test_config.py` to:

```python
from a_scanner.config import (
    DEFAULT_EXCLUDES,
    ConfigError,
    discover_validation_commands,
    load_config,
)
```

Append these tests:

```python
CANONICAL_EXCLUDES = (
    ".git",
    ".venv",
    "venv",
    "node_modules",
    "dist",
    "build",
    ".a-scanner",
    ".pytest-tmp",
    ".pytest_cache",
    ".ruff_cache",
    ".mypy_cache",
    "__pycache__",
    ".tox",
    ".nox",
)


def test_default_excludes_are_canonical(tmp_path: Path) -> None:
    config = load_config(tmp_path, None)

    assert DEFAULT_EXCLUDES == CANONICAL_EXCLUDES
    assert config.excludes == CANONICAL_EXCLUDES


def test_custom_excludes_extend_and_deduplicate_defaults(tmp_path: Path) -> None:
    path = tmp_path / "a-scanner.toml"
    path.write_text(
        """
schema_version = 1
[scan]
exclude = ["generated", ".venv", "generated"]
""".strip(),
        encoding="utf-8",
    )

    config = load_config(tmp_path, None)

    assert config.excludes == (*CANONICAL_EXCLUDES, "generated")


@pytest.mark.parametrize(
    "exclude_toml",
    [
        'exclude = "generated"',
        'exclude = [""]',
        'exclude = ["   "]',
        "exclude = [42]",
    ],
)
def test_rejects_invalid_exclusion_configuration(
    tmp_path: Path,
    exclude_toml: str,
) -> None:
    path = tmp_path / "a-scanner.toml"
    path.write_text(
        f"schema_version = 1\n[scan]\n{exclude_toml}\n",
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match=r"\[scan\]\.exclude"):
        load_config(tmp_path, None)
```

- [ ] **Step 3: Extend detector imports and add red tests**

Change the imports in `tests/test_detector.py` to:

```python
from pathlib import Path

import pytest

from a_scanner.config import DEFAULT_EXCLUDES
from a_scanner.detector import discover_projects
from a_scanner.models import Ecosystem
```

Append these tests:

```python
TRANSIENT_DIRECTORIES = (
    ".pytest-tmp",
    ".pytest_cache",
    ".ruff_cache",
    ".mypy_cache",
    "__pycache__",
    ".tox",
    ".nox",
)


@pytest.mark.parametrize("directory_name", TRANSIENT_DIRECTORIES)
def test_skips_canonical_transient_directories(
    tmp_path: Path,
    directory_name: str,
) -> None:
    ignored = tmp_path / directory_name / "nested"
    ignored.mkdir(parents=True)
    (ignored / "package.json").write_text("{}", encoding="utf-8")
    (ignored / "package-lock.json").write_text("{}", encoding="utf-8")

    assert discover_projects(tmp_path, DEFAULT_EXCLUDES) == []


def test_normalizes_exclusion_names_before_matching(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ignored = tmp_path / "GENERATED" / "nested"
    ignored.mkdir(parents=True)
    (ignored / "package.json").write_text("{}", encoding="utf-8")
    (ignored / "package-lock.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr("a_scanner.detector.os.path.normcase", str.casefold)

    assert discover_projects(tmp_path, ("generated",)) == []


def test_discovers_root_project_but_not_transient_nested_projects(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        "[project]\nname='root'\nversion='0.1.0'\n",
        encoding="utf-8",
    )
    (tmp_path / "uv.lock").write_text("version = 1\n", encoding="utf-8")
    transient = tmp_path / ".pytest-tmp" / "fixture"
    transient.mkdir(parents=True)
    (transient / "package.json").write_text("{}", encoding="utf-8")
    (transient / "package-lock.json").write_text("{}", encoding="utf-8")

    projects = discover_projects(tmp_path, DEFAULT_EXCLUDES)

    assert [(project.ecosystem, project.path) for project in projects] == [
        (Ecosystem.UV, tmp_path),
    ]
```

- [ ] **Step 4: Run the focused red gate**

Run:

```powershell
uv run pytest tests/test_config.py tests/test_detector.py -q
```

Expected: failures must be limited to the new C01 assertions:

- canonical defaults are incomplete;
- configured exclusions replace defaults or are not validated;
- transient directories are discovered;
- normalized matching is absent.

Do not proceed if an existing pre-C01 test fails.

- [ ] **Step 5: Commit the red-phase evidence**

Run:

```powershell
git add tests/test_config.py tests/test_detector.py
git diff --cached --check
git commit -m "test: reproduce temporary project discovery"
```

Expected: one test-only commit containing the reproducible C01 failures. This red commit is intentional; no implementation code is included.

---

### Task 2: Implement canonical exclusions and normalized pruning

**Files:**
- Modify: `src/a_scanner/config.py`
- Modify: `src/a_scanner/detector.py`
- Modify: `pyproject.toml`

**Interfaces:**
- Consumes: red tests from Task 1.
- Produces: `DEFAULT_EXCLUDES: tuple[str, ...]`; private `_merge_excludes(configured: object) -> tuple[str, ...]`; unchanged public `load_config()` and `discover_projects()` signatures.

- [ ] **Step 1: Expand canonical defaults in `config.py`**

Add `import os` with the standard-library imports and replace `DEFAULT_EXCLUDES` with:

```python
DEFAULT_EXCLUDES = (
    ".git",
    ".venv",
    "venv",
    "node_modules",
    "dist",
    "build",
    ".a-scanner",
    ".pytest-tmp",
    ".pytest_cache",
    ".ruff_cache",
    ".mypy_cache",
    "__pycache__",
    ".tox",
    ".nox",
)
```

- [ ] **Step 2: Add the focused exclusion merger**

Add this helper after `ScannerConfig`:

```python
def _merge_excludes(configured: object) -> tuple[str, ...]:
    if configured is None:
        additions: list[object] = []
    elif isinstance(configured, list):
        additions = configured
    else:
        raise ConfigError("[scan].exclude must be an array of non-empty strings.")

    merged: list[str] = []
    seen: set[str] = set()

    for index, value in enumerate((*DEFAULT_EXCLUDES, *additions), start=1):
        if not isinstance(value, str) or not value.strip():
            configured_index = index - len(DEFAULT_EXCLUDES)
            raise ConfigError(
                f"[scan].exclude entry {configured_index} must be a non-empty string."
            )

        key = os.path.normcase(value)
        if key not in seen:
            seen.add(key)
            merged.append(value)

    return tuple(merged)
```

The defaults are module-owned constants, so the validation branch can only be reached for configured additions.

- [ ] **Step 3: Make `load_config()` additive**

Replace:

```python
excludes = tuple(data.get("scan", {}).get("exclude", DEFAULT_EXCLUDES))
```

with:

```python
excludes = _merge_excludes(data.get("scan", {}).get("exclude"))
```

Do not change warning-pattern or validation-command behavior.

- [ ] **Step 4: Normalize detector matching once per discovery**

Replace the exclusion setup and directory filter in `discover_projects()` with:

```python
normalized_excludes = {os.path.normcase(value) for value in excludes}

for current, directories, filenames in os.walk(repository):
    directories[:] = sorted(
        directory
        for directory in directories
        if os.path.normcase(directory) not in normalized_excludes
    )
```

Remove the separate `directory.startswith(".a-scanner")` condition. The approved C01 contract uses normalized exact directory-name exclusions; `.a-scanner` itself remains canonical.

Do not change manifest-lockfile recognition or result ordering.

- [ ] **Step 5: Disable pytest's cache provider**

Change `pyproject.toml` to:

```toml
[tool.pytest.ini_options]
addopts = "-q --basetemp=.pytest-tmp -p no:cacheprovider"
testpaths = ["tests"]
```

Do not alter `.pytest-tmp/` in `.gitignore`.

- [ ] **Step 6: Run the focused green gate**

Run:

```powershell
uv run pytest tests/test_config.py tests/test_detector.py -q
```

Expected: all focused tests pass with zero warnings.

- [ ] **Step 7: Run static validation for changed Python files**

Run:

```powershell
uv run ruff check src/a_scanner/config.py src/a_scanner/detector.py tests/test_config.py tests/test_detector.py
uv run ruff format --check src/a_scanner/config.py src/a_scanner/detector.py tests/test_config.py tests/test_detector.py
uv run python -m compileall -q src tests
```

Expected: every command exits `0`.

If formatting is required, run:

```powershell
uv run ruff check src/a_scanner/config.py src/a_scanner/detector.py tests/test_config.py tests/test_detector.py --fix
uv run ruff format src/a_scanner/config.py src/a_scanner/detector.py tests/test_config.py tests/test_detector.py
```

Then rerun the three validation commands before committing.

- [ ] **Step 8: Commit the implementation**

Run:

```powershell
git add src/a_scanner/config.py src/a_scanner/detector.py pyproject.toml tests/test_config.py tests/test_detector.py
git diff --cached --check
git commit -m "fix: enforce canonical discovery exclusions"
```

Expected: focused tests and static gates are green before the implementation commit is created.

---

### Task 3: Add repository self-discovery proof

**Files:**
- Create: `tests/test_self_discovery.py`

**Interfaces:**
- Consumes: `load_config()` effective exclusions and `discover_projects()` normalized pruning from Task 2.
- Produces: repository-level proof that pytest-created files below `.pytest-tmp` do not become detected projects.

- [ ] **Step 1: Create the real-repository integration test**

Create `tests/test_self_discovery.py` with:

```python
from pathlib import Path

from a_scanner.config import load_config
from a_scanner.detector import discover_projects
from a_scanner.models import Ecosystem


def test_repository_self_discovery_returns_only_root_uv_project(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text("{}", encoding="utf-8")
    (tmp_path / "package-lock.json").write_text("{}", encoding="utf-8")
    repository = Path(__file__).resolve().parents[1]
    config = load_config(repository, None)

    projects = discover_projects(repository, config.excludes)

    assert len(projects) == 1
    assert projects[0].ecosystem is Ecosystem.UV
    assert projects[0].path == repository
    assert projects[0].manifest == repository / "pyproject.toml"
    assert projects[0].lockfile == repository / "uv.lock"
```

Because pytest's configured base temp is `.pytest-tmp`, `tmp_path` is a real nested npm-like fixture inside the repository. The test proves discovery prunes it while retaining the root uv project.

- [ ] **Step 2: Run the focused integration test**

Run:

```powershell
uv run pytest tests/test_self_discovery.py -q
```

Expected: `1 passed`, zero warnings.

- [ ] **Step 3: Run the complete test suite**

Run:

```powershell
uv run pytest
```

Expected: all tests pass with zero warnings. The count will be greater than the pre-C01 baseline of 14 because Tasks 1 and 3 add regression coverage.

- [ ] **Step 4: Commit the integration proof**

Run:

```powershell
git add tests/test_self_discovery.py
git diff --cached --check
git commit -m "test: prove clean repository self-discovery"
```

Expected: a test-only green commit.

---

### Task 4: Document the exclusion contract

**Files:**
- Modify: `a-scanner.toml`
- Modify: `README.md`
- Modify: `docs/ARCHITECTURE.md`
- Modify: `docs/V1-CONTRACT.md`

**Interfaces:**
- Consumes: canonical exclusion and additive configuration behavior from Tasks 2 and 3.
- Produces: user-facing and architectural documentation that matches the implemented behavior exactly.

- [ ] **Step 1: Make the repository config additive-only**

Replace the existing `[scan]` block in `a-scanner.toml` with:

```toml
[scan]
# Canonical environment, cache, test-workspace, and build exclusions are automatic.
# Add repository-specific directory names here; entries are matched by directory name.
exclude = []
```

Keep warning patterns and validation commands unchanged.

- [ ] **Step 2: Add README discovery documentation**

Insert this section after the usage examples and before `## Safety boundary`:

```markdown
## Project discovery

A-Scanner recognizes only locked uv and npm projects. Recursive discovery always prunes these
canonical directory names before inspection:

```text
.git
.venv
venv
node_modules
dist
build
.a-scanner
.pytest-tmp
.pytest_cache
.ruff_cache
.mypy_cache
__pycache__
.tox
.nox
```

Repository configuration extends this list; it does not replace the canonical exclusions:

```toml
schema_version = 1

[scan]
exclude = ["generated", "vendor-cache"]
```

Exclusions are directory names rather than paths or glob expressions. A configured name is pruned
wherever that directory occurs below the scanned repository. A-Scanner does not interpret
`.gitignore` files.
```

Use four backticks around the outer Markdown block while editing so the nested fences remain valid.

- [ ] **Step 3: Extend the architecture document**

Append this section to `docs/ARCHITECTURE.md`:

```markdown
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
prunes matches before descent. It does not parse `.gitignore`, path globs, or negation rules.
```

- [ ] **Step 4: Extend the V1 contract**

Insert this section after `## Supported ecosystem contract` in `docs/V1-CONTRACT.md`:

```markdown
## Discovery exclusion rule

A-Scanner prunes canonical environment, package-manager, cache, test-workspace, and build
directory names before recursive project detection. Repository `[scan].exclude` entries extend
that canonical list and cannot remove built-in exclusions.

Exclusion matching uses platform path-case semantics and exact immediate directory names. Entries
are not paths or glob patterns. V1 does not read or interpret `.gitignore` files.
```

- [ ] **Step 5: Validate documentation and configuration**

Run:

```powershell
uv run python -c "from pathlib import Path; from a_scanner.config import DEFAULT_EXCLUDES, load_config; config = load_config(Path('.').resolve(), None); assert config.excludes == DEFAULT_EXCLUDES; print(config.excludes)"
uv run pytest tests/test_config.py tests/test_detector.py tests/test_self_discovery.py -q
uv run ruff check .
uv run ruff format --check .
git diff --check
```

Expected: configuration resolves to the canonical tuple, focused tests pass with zero warnings, and all static gates exit `0`.

- [ ] **Step 6: Commit the documentation**

Run:

```powershell
git add a-scanner.toml README.md docs/ARCHITECTURE.md docs/V1-CONTRACT.md
git diff --cached --check
git commit -m "docs: define exclusion policy"
```

Expected: documentation accurately describes the implemented behavior and contains no unrelated changes.

---

### Task 5: Execute full C01 acceptance

**Files:**
- No repository files should change.
- Evidence output: external directory below `%LOCALAPPDATA%\A-Scanner\acceptance`.

**Interfaces:**
- Consumes: complete C01 implementation and documentation.
- Produces: fresh acceptance evidence proving validation, discovery precision, report persistence, and read-only Git invariants.

- [ ] **Step 1: Confirm clean branch state**

Run:

```powershell
$expectedBranch = 'build/a-scanner-v0.1-c01-discovery-exclusion-repair'
$branch = (& git branch --show-current).Trim()
$status = @(& git status --porcelain=v1 --untracked-files=all)

if ($branch -ne $expectedBranch) {
    throw "Unexpected branch: $branch"
}

if ($status.Count -ne 0) {
    $status | Write-Output
    throw 'Acceptance requires a clean worktree.'
}
```

Expected: correct branch and clean worktree.

- [ ] **Step 2: Run all repository validation gates**

Run each command and stop on the first non-zero exit code:

```powershell
uv sync --locked
uv run ruff check .
uv run ruff format --check .
uv run python -m compileall -q src tests
uv run pytest
uv build
```

Expected:

- lock sync exits `0`;
- Ruff lint exits `0`;
- Ruff format check exits `0`;
- Python compilation exits `0`;
- all tests pass with zero warnings;
- source distribution and wheel build successfully.

- [ ] **Step 3: Run the external read-only self-scan**

Run from PowerShell 7:

```powershell
$repository = (Get-Location).Path
$runStamp = Get-Date -Format 'yyyyMMddTHHmmss'
$evidenceDirectory = Join-Path $env:LOCALAPPDATA "A-Scanner\acceptance\c01-$runStamp"
New-Item -ItemType Directory -Path $evidenceDirectory -Force | Out-Null

$beforeHead = (& git rev-parse HEAD).Trim()
$beforeStatus = @(& git status --porcelain=v1 --untracked-files=all)
if ($beforeStatus.Count -ne 0) {
    throw 'Self-scan requires a clean worktree.'
}

& uv run a-scan . --check --report-directory $evidenceDirectory --format text
$scanExitCode = $LASTEXITCODE
if ($scanExitCode -ne 0) {
    throw "Self-scan failed with exit code $scanExitCode."
}

$jsonReports = @(Get-ChildItem -LiteralPath $evidenceDirectory -Filter '*.json' -File)
$textReports = @(Get-ChildItem -LiteralPath $evidenceDirectory -Filter '*.log' -File)
if ($jsonReports.Count -ne 1 -or $textReports.Count -ne 1) {
    throw "Expected one JSON and one text report; found $($jsonReports.Count) JSON and $($textReports.Count) text."
}

$report = Get-Content -LiteralPath $jsonReports[0].FullName -Raw | ConvertFrom-Json
$projects = @($report.projects_before)
$uvProjects = @($projects | Where-Object ecosystem -eq 'uv')
$npmProjects = @($projects | Where-Object ecosystem -eq 'npm')

if ($report.schema_version -ne 1) {
    throw "Unexpected schema version: $($report.schema_version)"
}
if ($report.mode -ne 'check' -or $report.status -ne 'check_completed') {
    throw "Unexpected scan result: mode=$($report.mode), status=$($report.status)"
}
if ($projects.Count -ne 1) {
    $projects | ConvertTo-Json -Depth 8 | Write-Output
    throw "Expected exactly one project; found $($projects.Count)."
}
if ($uvProjects.Count -ne 1 -or $npmProjects.Count -ne 0) {
    throw "Expected one uv project and zero npm projects."
}
if ([System.IO.Path]::GetFullPath($uvProjects[0].path) -ne [System.IO.Path]::GetFullPath($repository)) {
    throw "The detected uv project is not the repository root: $($uvProjects[0].path)"
}

$forbiddenNames = @(
    '.pytest-tmp',
    '.pytest_cache',
    '.ruff_cache',
    '.mypy_cache',
    '__pycache__',
    '.tox',
    '.nox',
    '.venv',
    'node_modules',
    'dist',
    'build'
)
$reportText = Get-Content -LiteralPath $jsonReports[0].FullName -Raw
foreach ($name in $forbiddenNames) {
    if ($reportText -match [regex]::Escape("\$name\")) {
        throw "Report contains a forbidden transient project path: $name"
    }
}

$afterHead = (& git rev-parse HEAD).Trim()
$afterStatus = @(& git status --porcelain=v1 --untracked-files=all)
if ($afterHead -ne $beforeHead) {
    throw "Git HEAD changed during self-scan: $beforeHead -> $afterHead"
}
if ($afterStatus.Count -ne 0) {
    $afterStatus | Write-Output
    throw 'Working tree changed during self-scan.'
}

Write-Output 'A-SCANNER-V0.1-C01-DISCOVERY-EXCLUSION-REPAIR: PASS'
Write-Output "Projects: $($projects.Count)"
Write-Output "uv projects: $($uvProjects.Count)"
Write-Output "npm projects: $($npmProjects.Count)"
Write-Output "Evidence: $evidenceDirectory"
```

Expected:

```text
A-SCANNER-V0.1-C01-DISCOVERY-EXCLUSION-REPAIR: PASS
Projects: 1
uv projects: 1
npm projects: 0
```

- [ ] **Step 4: Verify the commit series**

Run:

```powershell
git log --oneline --decorate origin/main..HEAD
git status --short --branch
```

Expected implementation history after the design and plan commits contains:

```text
test: reproduce temporary project discovery
fix: enforce canonical discovery exclusions
test: prove clean repository self-discovery
docs: define exclusion policy
```

The final working tree must be clean. Do not create a merge commit, push to `main`, or enable `--apply` as part of this task.

## Plan Self-Review

- Spec coverage: canonical exclusions, additive configuration, deterministic de-duplication, platform-aware matching, pruning before descent, pytest cache policy, self-discovery, documentation, and external acceptance all map to explicit tasks.
- Scope: no `.gitignore` parsing, new ecosystem, report schema, rollback, update selection, or `--apply` change is included.
- Placeholder scan: no `TODO`, `TBD`, unspecified test, or undefined helper remains.
- Type consistency: `_merge_excludes(configured: object) -> tuple[str, ...]`, `ScannerConfig.excludes`, `load_config()`, and `discover_projects()` signatures are consistent across tasks.
- Commit consistency: the plan preserves the four approved implementation commit subjects and keeps the initial red commit test-only.