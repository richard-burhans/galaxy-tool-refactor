# Macro profile-token ownership (Phase-3b decision input)

Reproduced-by: `uv run python -m scripts.measure macro-profile-ownership`.

When a tool's `profile=` is a macro token (e.g. `@PROFILE@`), where is the
token defined, is that file shared, and — if shared — do the importers
agree on the target profile? These numbers decide whether Phase 3b must
fork shared macro files (copy-on-write) or can edit them in place.

## Where the profile token is defined

| Placement | Tools |
|---|--:|
| profile= is a macro token | 1486 |
| └ defined inline (handled in Phase 3a) | 102 |
| └ in a directly-imported file | 1382 |
| └ deeper in the import chain | 0 |
| └ unresolved (token not found) | 2 |

## Defining-file ownership (imported tokens only)

Of the 1382 imported-token tools:

| Defining file | Tools |
|---|--:|
| sole-owned (1 importer) → edit in place | 1099 (79.5%) |
| shared (≥2 importers) → fork candidate | 283 (20.5%) |

## Do shared files' importers agree on the target profile?

The headline: if importers of a shared defining file almost always want the
same newest-valid profile, forking is usually unnecessary (an in-place bump
would satisfy them all).

| Shared defining file | Files |
|---|--:|
| importers agree on one target | 46 |
| importers diverge | 0 |
| indeterminate (none validate) | 0 |
| total shared defining files | 46 |
| └ with ≥2 profile-using importers (agreement actually tested) | 45 |

## Scan-soundness and path rewriting

| Metric | Count |
|---|--:|
| tool `<macros><import>` statements | 4762 |
| └ path contains `..` | 0 |
| └ path is absolute | 0 |
| defining file in tool's own directory | 1382 |
| defining file elsewhere | 0 |

