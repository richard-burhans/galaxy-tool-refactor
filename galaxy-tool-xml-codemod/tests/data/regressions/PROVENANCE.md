# Codemod regression fixtures

One subdirectory per retained tool. Each subdir holds the original
`tool.xml` (and any macro files it `<import>`s) as found in the
upstream source repository at the cited commit, plus any provenance
needed to trace the fixture back to its origin.

Fixtures are appended automatically by
`scripts/corpus_check.py codemod` when a corpus tool fails idempotence
or post-codemod validation. Each entry below records:

- the fixture directory name,
- the source corpus repository,
- the original path within that repository,
- the upstream commit at sweep time,
- the failure signature (``status:codemod-class``).

Replayed in the fast test suite by `tests/test_regressions.py`.
