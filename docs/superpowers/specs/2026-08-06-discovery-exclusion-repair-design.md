# A-Scanner V0.1 C01 Discovery Exclusion Repair Design

**Status:** Approved design awaiting written-spec review  
**Milestone:** `A-SCANNER-V0.1-C01-DISCOVERY-EXCLUSION-REPAIR`  
**Branch:** `build/a-scanner-v0.1-c01-discovery-exclusion-repair`

## 1. Purpose

A-Scanner V0.1 passed its first read-only self-scan safety acceptance, but the scan incorrectly discovered uv and npm fixture projects under `.pytest-tmp`. Pytest also emitted a cache warning because `.pytest_cache` was not writable on the Windows host.

C01 repairs discovery precision without changing update behavior. The milestone must ensure that transient environments, caches, test workspaces, and build outputs cannot be mistaken for real dependency projects during recursive repository discovery.

## 2. Scope

C01 includes:

- A canonical exclusion set for transient environments, package-manager directories, caches, test workspaces, and build outputs.
- Additive repository configuration so user exclusions extend rather than replace canonical exclusions.
- Platform-aware exclusion matching on Windows and other supported platforms.
- Pytest configuration that avoids both the inaccessible global temp link and the unwritable `.pytest_cache` path.
- Regression tests for excluded directories, additive configuration, mixed-repository discovery, and repository self-discovery.
- Documentation of the discovery and exclusion contract.

C01 does not include:

- Reading or interpreting `.gitignore` files.
- Git ignore-pattern semantics, negation rules, or nested ignore files.
- New package ecosystems.
- Changes to dependency resolution, update selection, rollback, reporting schema, or `--apply` behavior.
- Source-code modification.

## 3. Root Cause

`discover_projects()` currently prunes a directory only when its immediate name exactly matches one of the configured exclusions. The default list omits `.pytest-tmp`, `.pytest_cache`, `.ruff_cache`, `__pycache__`, and several other common transient directories.

`load_config()` currently replaces the default exclusions when `[scan].exclude` is present. A repository can therefore accidentally remove canonical safety exclusions by defining one custom entry.

The accepted self-scan consequently traversed `.pytest-tmp` and reported temporary test fixtures as real projects.

## 4. Canonical Exclusion Policy

A-Scanner shall always exclude these directory names from recursive discovery:

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

These entries are canonical safety exclusions. Repository configuration may add entries but may not remove them.

The effective exclusion sequence shall be constructed as:

```text
canonical defaults + configured additions
```

Duplicates shall be removed deterministically while preserving first occurrence order.

## 5. Matching Semantics

Discovery shall compare directory names using `os.path.normcase()` so matching follows the platform's path-case behavior:

- Windows comparisons are case-insensitive.
- Case-sensitive platforms retain case-sensitive behavior.

The detector shall continue pruning directories before descending into them. Excluded directories must not be traversed, inspected, or reported.

Exclusions remain directory-name exclusions, not path-glob patterns. An entry such as `generated` excludes any directory whose immediate name normalizes to `generated` anywhere below the repository root.

## 6. Configuration Contract

`ScannerConfig.excludes` shall contain the complete effective exclusion tuple.

When no configuration file exists, it shall equal the canonical defaults.

When `[scan].exclude` exists, each entry shall be validated as a non-empty string. Valid configured entries shall be appended to the canonical defaults and de-duplicated deterministically.

Invalid exclusion entries shall raise `ConfigError` and stop the scan before discovery.

The repository's example `a-scanner.toml` shall list only repository-specific additions if any are needed. Documentation shall state that canonical exclusions are automatic and do not need to be repeated.

## 7. Pytest Cache Policy

A-Scanner's own test configuration shall use:

```toml
[tool.pytest.ini_options]
addopts = "-q --basetemp=.pytest-tmp -p no:cacheprovider"
testpaths = ["tests"]
```

`.pytest-tmp/` shall remain ignored by Git and excluded by A-Scanner discovery.

The pytest cache provider is not required by this test suite. Disabling it prevents writes to `.pytest_cache` and removes the Windows permission warning without relocating another mutable cache into the repository.

## 8. Component Changes

### `src/a_scanner/config.py`

- Expand `DEFAULT_EXCLUDES` to the canonical set.
- Add a focused helper that validates, combines, and deterministically de-duplicates configured exclusions.
- Preserve canonical defaults even when `[scan].exclude` is present.
- Raise `ConfigError` for non-string or empty configured entries.

### `src/a_scanner/detector.py`

- Normalize the effective exclusion names once before traversal.
- Normalize each candidate directory name before membership testing.
- Continue sorting retained directories for deterministic traversal.
- Preserve existing uv and npm project detection rules and final result ordering.

### `tests/test_config.py`

Add tests proving:

- Default configuration contains the full canonical exclusion set.
- Custom exclusions extend defaults.
- Duplicate entries are removed deterministically.
- Invalid entries raise `ConfigError`.

### `tests/test_detector.py`

Add tests proving:

- `.pytest-tmp`, `.pytest_cache`, `.ruff_cache`, `.mypy_cache`, `__pycache__`, `.tox`, and `.nox` are pruned.
- A project manifest below an excluded directory is never reported.
- Windows-style case variation is excluded when `os.path.normcase()` is case-folding.
- Existing mixed uv/npm discovery remains unchanged.
- A repository-root uv project remains discoverable while transient nested fixtures are ignored.

### `pyproject.toml`

- Disable pytest's cache provider while retaining the repository-local base temp directory.

### Documentation

Update `README.md`, `docs/ARCHITECTURE.md`, `docs/V1-CONTRACT.md`, and `a-scanner.toml` to distinguish canonical exclusions from repository-specific additions.

## 9. Data Flow

1. CLI resolves the repository and configuration path.
2. `load_config()` loads the file or creates a default configuration.
3. Canonical exclusions and configured additions are validated and merged.
4. `discover_projects()` normalizes the effective exclusions.
5. `os.walk()` prunes matching directory names before descent.
6. Only retained directories are inspected for supported manifest-lockfile pairs.
7. Detected projects remain deterministically sorted and proceed through the existing scan pipeline.

## 10. Error Handling

- Invalid configuration fails before repository traversal.
- Discovery does not silently ignore malformed configured exclusion values.
- Missing configuration retains the canonical safe behavior.
- No new warnings or partial-success statuses are introduced.
- `--check` remains read-only and `--apply` behavior remains unchanged.

## 11. Test and Validation Strategy

Implementation shall use test-driven development:

1. Add failing regression tests reproducing temporary project discovery and replacement of canonical exclusions.
2. Verify the tests fail for the expected reasons.
3. Implement the smallest configuration and detector changes that satisfy the contract.
4. Run focused tests, then the complete suite.
5. Run the full repository validation gates.
6. Run a real read-only self-scan and inspect its persisted report.

Required validation commands:

```powershell
uv sync --locked
uv run ruff check .
uv run ruff format --check .
uv run python -m compileall -q src tests
uv run pytest
uv build
uv run a-scan . --check --report-directory <external-evidence-directory>
```

## 12. Acceptance Contract

C01 passes only when fresh executed evidence proves:

```text
Pytest:                    all tests pass, zero warnings
Ruff lint:                 pass
Ruff format:               pass
Python compilation:        pass
Package build:             pass

Self-scan projects:        1
Self-scan uv projects:     1
Self-scan npm projects:    0
Temporary projects:        0

Self-scan exit code:       0
Git HEAD:                  unchanged during self-scan
Working tree after scan:   clean
Reports:                   persisted externally
--apply behavior:          untouched
```

The self-scan report must identify only the repository-root A-Scanner uv project. It must not contain any path under `.pytest-tmp`, `.pytest_cache`, `.ruff_cache`, `.mypy_cache`, `__pycache__`, `.tox`, `.nox`, `.venv`, `node_modules`, `dist`, or `build`.

## 13. Commit Structure

Implementation should use these independently reviewable commits:

```text
test: reproduce temporary project discovery
fix: enforce canonical discovery exclusions
test: prove clean repository self-discovery
docs: define exclusion policy
```

No implementation commit may be created until its focused tests pass. The branch shall not be merged until the complete acceptance contract passes.