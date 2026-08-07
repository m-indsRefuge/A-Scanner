# A-Scanner

A-Scanner is a lightweight deterministic command-line tool that inspects a Git repository,
finds supported dependency projects, records deprecation warnings, upgrades dependencies to
their latest **compatible** versions, validates the repository, and rolls tracked repository
changes back when validation fails.

A-Scanner V0.1 supports:

- Python projects using `uv` with `pyproject.toml` and `uv.lock`
- Node projects using `npm` with `package.json` and `package-lock.json`
- Mixed repositories containing both ecosystems
- Read-only scanning with `--check`
- Controlled latest-compatible updates with `--apply`
- Clean-Git enforcement before modification
- Configured or conservatively discovered validation commands
- Human-readable and versioned JSON reports
- Deterministic rollback of tracked and newly-created untracked repository files

A-Scanner does not modify application source code, cross compatibility boundaries, replace
abandoned libraries, upgrade runtimes, commit, push, or use an LLM.

## Install for development

```powershell
uv sync --all-groups
uv run a-scan . --check
```

Install as an isolated command from a local checkout:

```powershell
uv tool install .
a-scan . --check
```

## Usage

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

Exclusions are exact directory names rather than paths or glob expressions. A configured name is
pruned wherever that directory occurs below the scanned repository. Matching follows platform
path-case semantics. A-Scanner does not read or interpret `.gitignore` files for discovery.

## Safety boundary

`--apply` requires:

1. A Git repository.
2. A clean working tree.
3. At least one supported locked uv or npm project.
4. A passing baseline validation gate that leaves Git-visible state unchanged.
5. A passing post-update validation gate that does not change the package-update state.

A-Scanner fingerprints tracked changes and non-ignored untracked files around validation. A
validation command that changes `HEAD` or Git-visible content is rejected. After dependency
updates, such a validation integrity failure triggers rollback just like a failed validation
command.

When post-update validation fails, A-Scanner restores tracked files to the original commit and
removes untracked, non-ignored files created during the run. Ignored environments such as `.venv`
and `node_modules` are not deleted.

`--check` stores reports outside the target repository. An explicit `--report-directory` must also
resolve outside the repository; an in-repository destination is rejected and the preflight failure
report is written to the default external location.

Package-manager and validation commands may resolve remote metadata, download packages, build
distributions, execute package lifecycle hooks, and run repository code. Run A-Scanner only
against repositories, package sources, and validation commands you trust.

## Configuration

`a-scanner.toml` uses argument arrays rather than shell command strings:

```toml
schema_version = 1

[[validation.commands]]
name = "Tests"
argv = ["uv", "run", "pytest"]
cwd = "."
```

Configured warning patterns must be valid regular expressions. Invalid configuration is rejected
during preflight with deterministic error evidence.

See [docs/V1-CONTRACT.md](docs/V1-CONTRACT.md) and
[docs/SAFETY-MODEL.md](docs/SAFETY-MODEL.md).

## Status

This repository is the V0.1 implementation baseline for the A-Scanner V1 build. The deterministic
core now includes project-discovery exclusions and validation/Git-integrity hardening. Remaining
V1 work is tracked in [docs/ROADMAP.md](docs/ROADMAP.md).
