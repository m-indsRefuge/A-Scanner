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

## Safety boundary

`--apply` requires:

1. A Git repository.
2. A clean working tree.
3. At least one supported locked ecosystem.
4. A passing baseline validation gate.
5. A passing post-update validation gate.

When post-update validation fails, A-Scanner restores tracked files to the original commit and
removes untracked files created during the run. Ignored environments such as `.venv` and
`node_modules` are not deleted.

Package-manager commands may resolve remote metadata, download packages, build distributions,
and execute package lifecycle hooks. Run A-Scanner only against repositories and package sources
you trust.

## Configuration

`a-scanner.toml` uses argument arrays rather than shell command strings:

```toml
schema_version = 1

[[validation.commands]]
name = "Tests"
argv = ["uv", "run", "pytest"]
cwd = "."
```

See [docs/V1-CONTRACT.md](docs/V1-CONTRACT.md) and
[docs/SAFETY-MODEL.md](docs/SAFETY-MODEL.md).

## Status

This scaffold is the V0.1 implementation baseline for the A-Scanner V1 build. It is intentionally
small and deterministic. The V1 acceptance process should prove the behaviour against isolated
fixture repositories before using `--apply` on production work.
