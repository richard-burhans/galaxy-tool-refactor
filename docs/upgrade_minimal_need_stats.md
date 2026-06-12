# Upgrade minimal-need statistics

How the **shipped minimal-bump** `galaxy-tool-refactor upgrade` default
treats the corpus: keep a tool's `profile=` when it validates there (after a
`FixTypos` repair), and otherwise bump only to the **minimum** vendored profile
at or above its baseline that validates. This inverts the behavior-gate
walk (codemod `docs/decisions.md` §45, now the opt-in `--modernize`; the
default is §50), and this page sizes how often the default changes nothing at
all.

A tool's baseline is its declared `profile=`, or Galaxy's `16.01` default when
undeclared (`behavior_gate.resolved_baseline`). No-profile tools are reported
as a separate cohort; the settled policy leaves them undeclared (declaring a
profile is `--modernize`'s job), sized by the kept-undeclared count below.

Regenerate with (needs the corpus, so not run in CI):

```sh
uv run python -m scripts.measure upgrade-minimal-need
```

Unique `<tool>` files (sha256-deduped): **9,373**. Latest vendored
profile: `26.1`. Deployment ceiling (the newest profile across the
major public Galaxy servers): `25.1`.

## What the default does

**Kept untouched: 7,195 (76.8%)**. Bumped to a minimum valid profile: 1,482 (15.8%).

| Class | Tools | Share | Declared cohort | No-profile cohort |
|---|--:|--:|--:|--:|
| kept | 7,195 | 76.8% | 3,099 | 4,096 |
| bump-direct | 1,481 | 15.8% | 558 | 923 |
| bump-step-assisted | 1 | 0.0% | 1 | 0 |
| unreachable | 694 | 7.4% | 27 | 667 |
| unplaceable | 2 | 0.0% | 2 | 0 |

`kept` = validates at its baseline (no bump). `bump-direct` / `bump-step-assisted` = invalid at the baseline, moved up to the minimum valid profile (the latter needed a structural upgrade codemod first). `unreachable` = validates nowhere at or above the baseline. `unplaceable` = an unresolved `@PROFILE@` token (the gate fails closed).

## Where the minimal bumps land

Of the 1,482 bumped tools, **0** land above the deployment ceiling `25.1` (a minimum valid profile the lagging public servers cannot yet install; validity still wins, so these bump regardless).

| Minimum valid profile | Tools | Histogram |
|---|--:|---|
| 17.01 | 98 | █████ |
| 17.05 | 13 | █ |
| 17.09 | 5 |  |
| 18.01 | 9 |  |
| 18.05 | 33 | ██ |
| 18.09 | 1 |  |
| 19.01 | 2 |  |
| 19.05 | 120 | ██████ |
| 19.09 | 627 | ██████████████████████████████ |
| 20.01 | 80 | ████ |
| 20.05 | 15 | █ |
| 20.09 | 5 |  |
| 21.01 | 153 | ███████ |
| 21.09 | 73 | ███ |
| 22.01 | 36 | ██ |
| 22.05 | 12 | █ |
| 23.0 | 10 |  |
| 23.1 | 71 | ███ |
| 24.0 | 73 | ███ |
| 24.1 | 29 | █ |
| 24.2 | 6 |  |
| 25.0 | 4 |  |
| 25.1 | 7 |  |
