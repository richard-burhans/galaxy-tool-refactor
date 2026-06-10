# Upgrade profile-shift statistics

Where `galaxy-tool-refactor upgrade` moves a tool's profile: the profile it
**declares** (no-profile defaulted to Galaxy's `16.01` runtime default — the
"as reported, or as defaulted" baseline) vs the profile it **reaches** after
the `UpgradeToLatest` pipeline runs. This differs from
`combined_corpus_stats.md`'s *newest valid profile distribution* (the
pre-upgrade validity ceiling): here the structural upgrade codemods
(GTR007-012) actually run, so a tool stuck below its ceiling by a
restrict-transition climbs. `UpgradeToLatest`-only (no `FixTypos`); the
runtime-gated fixes (GTR014/015) don't change `profile=`. See
`profile_upgrades.md` and codemod `docs/decisions.md` §11-14.

Regenerate with (needs the corpus, so not run in CI):

```sh
uv run python -m scripts.measure upgrade-profile-shift
```

Unique `<tool>` files (sha256-deduped): **9,358**. Latest vendored profile: `26.1`.

## Shift summary

| Measure | Tools | Share |
|---|--:|--:|
| At latest **before** upgrade (declared = `26.1`) | 0 | 0.0% |
| At latest **after** upgrade | 8,583 | 91.7% |
| Advanced (reached a newer profile) | 7,139 | 76.3% |
| Unchanged (same profile) | 0 | 0.0% |
| Macro-token / unplaceable baseline | 1,486 | 15.9% |
| Validates nowhere after upgrade | 734 | 7.8% |

## Declared (defaulted) profile distribution — before

| Profile | Tools | % | Histogram |
|---|--:|--:|---|
| 16.01 | 5,697 | 60.9% | ██████████████████████████████ |
| 16.04 | 88 | 0.9% |  |
| 16.07 | 180 | 1.9% | █ |
| 16.10 | 4 | 0.0% |  |
| 17.01 | 7 | 0.1% |  |
| 17.05 | 14 | 0.1% |  |
| 17.09 | 4 | 0.0% |  |
| 18.01 | 90 | 1.0% |  |
| 18.05 | 1 | 0.0% |  |
| 18.09 | 24 | 0.3% |  |
| 19.01 | 36 | 0.4% |  |
| 19.05 | 13 | 0.1% |  |
| 19.09 | 2 | 0.0% |  |
| 20.01 | 181 | 1.9% | █ |
| 20.5 | 1 | 0.0% |  |
| 20.05 | 136 | 1.5% | █ |
| 20.09 | 25 | 0.3% |  |
| 21.01 | 24 | 0.3% |  |
| 21.05 | 408 | 4.4% | ██ |
| 21.09 | 110 | 1.2% | █ |
| 22.01 | 30 | 0.3% |  |
| 22.04 | 1 | 0.0% |  |
| 22.05 | 414 | 4.4% | ██ |
| 22.09 | 4 | 0.0% |  |
| 23.0 | 170 | 1.8% | █ |
| 23.00 | 1 | 0.0% |  |
| 23.1 | 27 | 0.3% |  |
| 23.2 | 36 | 0.4% |  |
| 23.02 | 1 | 0.0% |  |
| 23.05 | 1 | 0.0% |  |
| 24.0 | 30 | 0.3% |  |
| 24.1 | 17 | 0.2% |  |
| 24.01 | 3 | 0.0% |  |
| 24.2 | 52 | 0.6% |  |
| 25.0 | 16 | 0.2% |  |
| 25.1 | 24 | 0.3% |  |
| (macro/unparseable) | 1,486 | 15.9% | ████████ |

## Reached profile distribution — after `upgrade`

| Profile | Tools | % | Histogram |
|---|--:|--:|---|
| 21.05 | 1 | 0.0% |  |
| 21.09 | 1 | 0.0% |  |
| 24.1 | 39 | 0.4% |  |
| 26.1 | 8,583 | 91.7% | ██████████████████████████████ |
| (none) | 734 | 7.8% | ███ |

`(none)` = validates at no profile after the run. Because this is `UpgradeToLatest`-only, these are the tools that need a `FixTypos` repair first (the full `galaxy-tool-refactor upgrade` runs `FixTypos` before `UpgradeToLatest`, so it would carry many of them further). A sub-latest literal profile (e.g. `24.1`) is a genuine sticking point — no registered upgrade codemod advances it. The macro-token baselines counted above are not lost: they appear here at the profile they actually reached.
