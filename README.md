# A-Scanner

A-Scanner is a lightweight deterministic command-line tool for inspecting and safely updating locked dependency projects inside a Git repository.

It discovers supported Python/uv and Node/npm projects, records deprecation warnings, identifies dependency updates, applies only latest-compatible changes when requested, validates the repository before and after mutation, and rolls repository changes back when safety or validation gates fail.

**Current release:** `v0.1.1`  
**Status:** Alpha

A-Scanner itself contains **no LLM or agent runtime**. It is intentionally deterministic. The project was developed through sustained human-AI engineering collaboration, but every scan and update decision performed by the released tool follows explicit code, package-manager output, configuration, and validation results.

## What V0.1.1 supports

- Python projects using `uv` with `pyproject.toml` and `uv.lock`
- Node projects using `npm` with `package.json` and `package-lock.json`
- Mixed repositories containing both ecosystems
- Read-only scanning with `--check`
- Controlled latest-compatible updates with `--apply`
- Clean-Git enforcement before modification
- Configured or conservatively discovered validation commands
- Human-readable and versioned JSON reports
- Deterministic rollback of tracked and newly-created untracked repository files
- Windows npm command-shim resolution while retaining `shell=False`
- Fail-closed handling when npm dependency inventory cannot be trusted
- Linked Git worktree isolation through the default `.worktrees` discovery exclusion

A-Scanner does not modify application source code, cross declared compatibility boundaries, replace abandoned libraries, upgrade runtimes, commit, push, or use an LLM at runtime.

## Install

### GitHub Release wheel

The initial public distribution is a wheel attached to the GitHub Release for `v0.1.1`.

After downloading `a_scanner-0.1.1-py3-none-any.whl` from the Releases page:

```powershell
uv tool install .\a_scanner-0.1.1-py3-none-any.whl
```

Verify the installed command:

```powershell
a-scan --version
```

### Development checkout

```powershell
uv sync --all-groups
uv run a-scan . --check
```

Install as an isolated command from a local checkout:

```powershell
uv tool install .
a-scan . --check
```

## Quick start

Read-only scan:

```powershell
a-scan C:\path\to\repository --check
```

Apply compatible updates:

```powershell
a-scan C:\path\to\repository --apply
```

Print the persisted report as JSON:

```powershell
a-scan . --check --format json
```

Use an explicit configuration file:

```powershell
a-scan . --apply --config a-scanner.toml
```

## Project discovery

A-Scanner recognizes only locked uv and npm projects. Recursive discovery always prunes these canonical directory names before inspection:

```text
.git
.worktrees
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

`.worktrees` is excluded by default so a scan of one Git working tree does not silently recurse into linked worktrees that represent separate working-tree boundaries.

Repository configuration extends the canonical exclusion list; it does not replace it:

```toml
schema_version = 1

[scan]
exclude = ["generated", "vendor-cache"]
```

Exclusions are exact directory names rather than paths or glob expressions. A configured name is pruned wherever that directory occurs below the scanned repository. Matching follows platform path-case semantics. A-Scanner does not read or interpret `.gitignore` files for discovery.

## Safety boundary

`--check` is the default way to inspect a repository without requesting dependency mutation. Reports are stored outside the target repository so the scan itself does not create Git-visible changes there.

`--apply` requires:

1. A Git repository.
2. A clean working tree.
3. At least one supported locked uv or npm project.
4. A passing baseline validation gate that leaves Git-visible state unchanged.
5. Native package updates that keep `HEAD` unchanged and modify only detected manifest/lockfile paths in Git-visible state.
6. A passing post-update validation gate that leaves the package-update state unchanged.

A-Scanner fingerprints tracked changes and non-ignored untracked files around validation. If baseline validation changes `HEAD` or Git-visible content, A-Scanner restores the clean intake state and reports `baseline_failed`; failed restoration becomes `rollback_failed`.

Native package-manager updates may change the detected dependency manifests and lockfiles and may change ignored package environments. A successful updater that moves `HEAD` or changes any other Git-visible path is rejected and rolled back. A controlled exception after update execution begins also enters rollback rather than leaving partial update changes behind.

After dependency updates, a validation command that changes `HEAD`, changes Git-visible content, or cannot be verified is rejected and the original intake state is restored. Failed rollback verification is reported as `rollback_failed`.

An explicit `--report-directory` must resolve outside the scanned repository; an in-repository destination is rejected and the preflight-failure report is written to the default external location.

Package-manager and validation commands may resolve remote metadata, download packages, build distributions, execute package lifecycle hooks, and run repository code. Run A-Scanner only against repositories, package sources, and validation commands you trust.

For the detailed model, see [docs/SAFETY-MODEL.md](docs/SAFETY-MODEL.md).

## Configuration

`a-scanner.toml` uses argument arrays rather than shell command strings:

```toml
schema_version = 1

[[validation.commands]]
name = "Tests"
argv = ["uv", "run", "pytest"]
cwd = "."
```

`schema_version` must be the integer `1`. Configured warning patterns must be valid regular expressions. Invalid configuration is rejected during preflight with deterministic error evidence.

## Project documentation

- [Changelog](CHANGELOG.md)
- [Architecture](docs/ARCHITECTURE.md)
- [Safety model](docs/SAFETY-MODEL.md)
- [V1 contract](docs/V1-CONTRACT.md)
- [Roadmap](docs/ROADMAP.md)
- [Contributing](CONTRIBUTING.md)
- [Security policy](SECURITY.md)

## Development status

`v0.1.1` is the current alpha release. The deterministic core is intentionally narrow and focuses on locked uv/npm dependency workflows, repository-integrity enforcement, evidence-rich reporting, and verified rollback.

Future work is tracked in [docs/ROADMAP.md](docs/ROADMAP.md). The V1 contract documents the intended direction; functionality described there should not be assumed released unless it is also documented here or in the changelog.

## License

A-Scanner is released under the [MIT License](LICENSE).
