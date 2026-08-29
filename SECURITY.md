# Security Policy

## Reporting

Please report security issues privately to the repository owner before opening a public issue.

## Important operating assumptions

A-Scanner invokes local package managers and repository-defined validation commands. Those tools
can execute code from the repository or downloaded packages. A-Scanner is not a sandbox.

Only scan trusted repositories and trusted package registries. Review `a-scanner.toml` before
running `--apply`.

For npm projects, A-Scanner disables npm lifecycle scripts during its update step by default using
`npm update --save --ignore-scripts`. This reduces one code-execution surface but does **not** make
APPLY safe for untrusted repositories: validation commands, package-manager tooling, build
backends, and other repository tooling may still execute code. Setting `[npm].ignore_scripts =
false` deliberately enables npm install lifecycle hooks and should be done only for trusted input.

A-Scanner fails closed when an explicitly requested config file is missing, when npm manifest or
lockfile JSON cannot be trusted, when uv outdated JSON no longer has a recognized package-tree
shape, when detected project metadata escapes the repository, or when a non-ignored untracked file
larger than 100 MiB would make validation fingerprinting unbounded.

Reports are written atomically outside the repository and are restricted to mode `0600` where POSIX
permission semantics are available. Reports may contain stdout/stderr emitted by external tools,
which can themselves print credentials or sensitive data; protect the report directory accordingly.

Configured warning regexes are length-bounded and reject obvious nested-repeat patterns, but
A-Scanner does not claim to be a general-purpose regex sandbox.

A-Scanner does not upload repository content or include telemetry in V0.1.
