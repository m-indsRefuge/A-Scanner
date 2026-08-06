# Contributing

A-Scanner is safety-sensitive because it modifies dependency manifests and lockfiles.

Before proposing a change:

```powershell
uv sync --all-groups
uv run ruff check .
uv run ruff format --check .
uv run pytest
uv build
```

Changes affecting update, validation, rollback, subprocess execution, report schemas, or Git
handling require focused tests that prove both success and failure behaviour.

Do not weaken the clean-working-tree gate or add automatic source-code edits to the deterministic
core without a documented contract revision.
