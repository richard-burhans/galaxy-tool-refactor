# Security Policy

## Reporting a vulnerability

Please report security vulnerabilities **privately**, not in a public issue.

Use GitHub's private vulnerability reporting: go to the repository's
[**Security** tab → **Report a vulnerability**](https://github.com/richard-burhans/galaxy-tool-refactor/security/advisories/new).
This opens a private advisory visible only to you and the maintainers.

Please include enough to reproduce: affected package(s) and version, a minimal
example, and the impact you observed. We aim to acknowledge a report within a
week and will coordinate a fix and disclosure with you.

## Scope

This project parses and transforms untrusted Galaxy tool XML. The most relevant
classes of issue are:

- **Parser/transform safety** — crashes, hangs, or unbounded resource use on
  crafted tool XML, macro files, or `<help>` reStructuredText.
- **Behaviour-preservation breaks** — a "fixable" rule that silently changes what
  a tool *does* (not just how it reads). These are treated seriously; the project
  holds fixes to a by-construction soundness bar (`docs/behavior_preservation.md`,
  `docs/proofs/`). A reproducible counter-example to a shipped fix is in scope.

The library does **not** execute tool commands or fetch untrusted code at runtime;
it operates on the XML document. Findings that require an attacker to already have
arbitrary local execution are generally out of scope.

## Supported versions

Pre-1.0, only the latest released version (all eight packages, lockstep-versioned)
receives security fixes.
