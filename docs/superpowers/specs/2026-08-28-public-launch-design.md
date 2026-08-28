# A-Scanner V0.1.1 Public Launch Design

## Goal

Prepare the existing A-Scanner repository for a public GitHub launch without changing the released V0.1.1 runtime, rewriting Git history, or moving the existing `v0.1.1` tag.

## Release model

- The existing repository becomes the public source repository.
- Existing Git history is preserved exactly as developed.
- The annotated `v0.1.1` tag remains immutable and continues to identify the accepted V0.1.1 runtime source.
- Public-facing documentation may advance on `main` after the V0.1.1 tag.
- Downloadable wheel and source-distribution artifacts are built from the exact `v0.1.1` tag, not from later documentation commits.
- A GitHub Release is created for the existing `v0.1.1` tag only after package artifacts are built and smoke-tested.
- PyPI publication is deferred until the GitHub release has been exercised by public installation.

## Public documentation

The public README must:

- describe A-Scanner as a deterministic dependency/deprecation scanner and compatible updater;
- state current version `0.1.1` without implying V1 is complete;
- document both `--check` and controlled `--apply` usage;
- document GitHub Release wheel installation as the initial public distribution path;
- document all canonical discovery exclusions, including `.worktrees`;
- explain the apply safety boundary and rollback behavior in plain language;
- state clearly that A-Scanner itself contains no LLM runtime;
- distinguish the software runtime from the human-AI collaboration through which it was developed;
- link to architecture, safety, roadmap, contributing, security, and changelog material.

## Changelog

Add a concise `CHANGELOG.md` that records:

- V0.1.1 Windows executable/shim resolution for npm while preserving `shell=False`;
- fail-closed npm inventory validation;
- post-update inventory revalidation and rollback on failure;
- support for valid array-shaped `npm outdated --json` detail records;
- clearer dependency/report rendering;
- `.worktrees` exclusion to preserve the selected Git working-tree boundary;
- V0.1.0 as the original deterministic baseline.

The changelog must not claim that an independent Codex security scan or independent Codex PR review was completed.

## Package artifacts

Build artifacts from an isolated checkout of `v0.1.1` using `uv build`.

Expected artifacts:

- `a_scanner-0.1.1-py3-none-any.whl`
- `a_scanner-0.1.1.tar.gz`

Before publication:

1. verify the checkout resolves exactly to the accepted V0.1.1 commit;
2. build both artifacts;
3. install the wheel into an isolated tool/environment;
4. verify `a-scan --version` reports `0.1.1`;
5. run a read-only smoke scan against a disposable supported repository or fixture;
6. record SHA-256 checksums for both artifacts.

## GitHub Release

Create a GitHub Release attached to the existing `v0.1.1` tag after the artifact gate passes. Attach the wheel, source distribution, and checksum file. Release notes should summarize user-visible V0.1.1 fixes and link readers to the repository safety documentation.

## Visibility gate

Repository visibility changes from private to public only after:

- current-tree and reachable-history privacy review is accepted by the repository owner;
- public documentation PR is merged with green CI;
- package artifacts are built from `v0.1.1` and smoke-tested;
- GitHub Release assets are ready;
- final repository metadata and links are reviewed.

The visibility change is a separate consequential action and must be explicitly authorized at the final gate.

## Non-goals

This launch does not:

- modify V0.1.1 runtime behavior;
- move or rewrite `v0.1.1`;
- rewrite repository history;
- publish to PyPI;
- add an LLM or agent runtime to A-Scanner;
- publish the Byte Dev Journal or LinkedIn article as part of the software-release mechanics.
