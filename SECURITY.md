# Security Policy

## Reporting

Please report security issues privately to the repository owner before opening a public issue.

## Important operating assumptions

A-Scanner invokes local package managers and repository-defined validation commands. Those tools
can execute code from the repository or downloaded packages. A-Scanner is not a sandbox.

Only scan trusted repositories and trusted package registries. Review `a-scanner.toml` before
running `--apply`.

A-Scanner does not upload repository content or include telemetry in V0.1.
