# A-Scanner V0.1.1 Public Launch Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prepare A-Scanner V0.1.1 for a safe public GitHub launch with polished public documentation and verified downloadable package artifacts.

**Architecture:** Keep the released runtime immutable at `v0.1.1`. Advance only public-facing documentation on `main`, then build and smoke-test wheel/sdist artifacts from an isolated checkout of the exact release tag before creating the GitHub Release and changing repository visibility.

**Tech Stack:** Python 3.12+, uv, Hatchling, Git, GitHub Actions, GitHub Releases.

**Spec:** `docs/superpowers/specs/2026-08-28-public-launch-design.md`

## Global Constraints

- Do not move, rewrite, or recreate the existing `v0.1.1` tag.
- Do not rewrite repository history.
- Do not change V0.1.1 runtime behavior during launch preparation.
- Build release artifacts from the exact `v0.1.1` tag, not later documentation commits.
- Do not publish to PyPI in this launch phase.
- Do not change repository visibility until the final explicit authorization gate.
- Do not claim an independent Codex security scan or independent Codex PR review was completed.

---

### Task 1: Public README

**Files:**
- Modify: `README.md`

**Interfaces:**
- Consumes: V0.1.1 runtime behavior and safety model already documented in the repository.
- Produces: public installation, usage, discovery-boundary, safety, and project-context documentation.

- [ ] **Step 1: Update the opening and status language**

Describe A-Scanner as a released alpha-quality deterministic CLI at version `0.1.1`, not as a V0.1 implementation baseline.

- [ ] **Step 2: Add public installation guidance**

Document initial GitHub Release wheel installation with:

```powershell
uv tool install .\a_scanner-0.1.1-py3-none-any.whl
```

Keep local-development installation separate.

- [ ] **Step 3: Correct project discovery documentation**

Add `.worktrees` to the canonical exclusion list and explain that it prevents a parent scan from crossing into separate linked Git working trees.

- [ ] **Step 4: Add runtime/collaboration distinction**

State that A-Scanner itself is deterministic and contains no LLM runtime, while acknowledging that the project was developed through sustained human-AI engineering collaboration.

- [ ] **Step 5: Add public project links**

Link `CHANGELOG.md`, `CONTRIBUTING.md`, `SECURITY.md`, `docs/ARCHITECTURE.md`, `docs/SAFETY-MODEL.md`, and `docs/ROADMAP.md`.

- [ ] **Step 6: Review README claims against source**

Confirm every behavioral claim is already supported by V0.1.1 code/tests and no future functionality is presented as released.

### Task 2: Changelog

**Files:**
- Create: `CHANGELOG.md`

**Interfaces:**
- Consumes: accepted V0.1.0 and V0.1.1 engineering history.
- Produces: concise release history for repository visitors and GitHub Release notes.

- [ ] **Step 1: Add V0.1.1 entry**

Record Windows command-shim resolution, fail-closed npm inventory semantics, post-update revalidation/rollback, valid array-shaped npm inventory support, report clarity improvements, and `.worktrees` discovery isolation.

- [ ] **Step 2: Add V0.1.0 entry**

Record the initial deterministic uv/npm scanning, check/apply modes, validation gates, reporting, clean-Git enforcement, and rollback baseline.

- [ ] **Step 3: Audit wording**

Do not describe the tag as signed and do not claim external review/security work that did not occur.

### Task 3: Documentation PR Gate

**Files:**
- Review: `README.md`
- Review: `CHANGELOG.md`
- Review: `docs/superpowers/specs/2026-08-28-public-launch-design.md`
- Review: `docs/superpowers/plans/2026-08-28-public-launch.md`

**Interfaces:**
- Consumes: Tasks 1-2.
- Produces: mergeable launch-documentation candidate.

- [ ] **Step 1: Run repository checks in the isolated worktree**

```powershell
uv sync --all-groups
uv run ruff check .
uv run ruff format --check .
uv run pytest
uv build

git diff --check
```

Expected: all commands exit `0`.

- [ ] **Step 2: Inspect the diff**

```powershell
git status --short
git diff --stat
git diff -- README.md CHANGELOG.md docs/superpowers/specs/2026-08-28-public-launch-design.md docs/superpowers/plans/2026-08-28-public-launch.md
```

Expected: documentation-only launch preparation.

- [ ] **Step 3: Open a PR to `main`**

Title: `docs: prepare A-Scanner v0.1.1 public launch`

- [ ] **Step 4: Require green cross-platform CI before merge**

Expected matrix: Ubuntu/Windows × Python 3.12/3.13 all successful.

### Task 4: Build Exact V0.1.1 Artifacts

**Files:**
- No tracked repository changes.
- Output: external release staging directory.

**Interfaces:**
- Consumes: immutable tag `v0.1.1` resolving to accepted release commit.
- Produces: wheel, source distribution, checksum manifest.

- [ ] **Step 1: Create isolated detached release checkout**

From the canonical repository:

```powershell
$releaseWorktree = 'C:\Users\nolan\AIProjects\a-scanner-v0.1.1-release-build'
git worktree add --detach $releaseWorktree v0.1.1
```

- [ ] **Step 2: Verify exact release source**

```powershell
git -C $releaseWorktree rev-parse HEAD
git -C $releaseWorktree describe --tags --exact-match
```

Expected commit:

```text
18a89c31dbf23ba3ca0be3ac7b62f40826abc706
```

Expected tag: `v0.1.1`.

- [ ] **Step 3: Build artifacts**

```powershell
Push-Location $releaseWorktree
try {
    uv build
}
finally {
    Pop-Location
}
```

Expected:

```text
dist/a_scanner-0.1.1-py3-none-any.whl
dist/a_scanner-0.1.1.tar.gz
```

- [ ] **Step 4: Verify wheel installation**

```powershell
$toolDir = Join-Path $env:TEMP 'a-scanner-v0.1.1-tool'
$env:UV_TOOL_DIR = $toolDir
uv tool install "$releaseWorktree\dist\a_scanner-0.1.1-py3-none-any.whl"
uv tool run --from "$releaseWorktree\dist\a_scanner-0.1.1-py3-none-any.whl" a-scan --version
```

Expected version: `0.1.1`.

- [ ] **Step 5: Generate SHA-256 checksums**

```powershell
Get-FileHash "$releaseWorktree\dist\a_scanner-0.1.1-py3-none-any.whl" -Algorithm SHA256
Get-FileHash "$releaseWorktree\dist\a_scanner-0.1.1.tar.gz" -Algorithm SHA256
```

Record both hashes in `SHA256SUMS.txt` in the external release staging directory.

### Task 5: GitHub Release and Public Visibility

**Files:**
- No tracked runtime changes.

**Interfaces:**
- Consumes: merged documentation PR and verified Task 4 artifacts.
- Produces: public GitHub repository and downloadable V0.1.1 release.

- [ ] **Step 1: Draft GitHub Release notes from `CHANGELOG.md`**

Include supported ecosystems, safety boundary, V0.1.1 fixes, alpha status, and links to safety/architecture docs.

- [ ] **Step 2: Create release for existing `v0.1.1` tag**

Attach:

```text
a_scanner-0.1.1-py3-none-any.whl
a_scanner-0.1.1.tar.gz
SHA256SUMS.txt
```

- [ ] **Step 3: Verify release/tag integrity**

Confirm the public release remains attached to `v0.1.1` and that the tag still resolves to `18a89c31dbf23ba3ca0be3ac7b62f40826abc706`.

- [ ] **Step 4: Request final explicit authorization to make the repository public**

Do not change visibility before this approval.

- [ ] **Step 5: Change repository visibility to public**

After approval, publish the existing repository without rewriting history.

- [ ] **Step 6: Perform public-side installation smoke test**

Download the wheel from the public GitHub Release, install it with `uv tool install`, and run `a-scan --version` plus one read-only `--check` against a disposable supported repository.
