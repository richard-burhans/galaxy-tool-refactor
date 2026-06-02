# Cheetah command/configfile complexity statistics

A **heuristic** (regex, not a Cheetah parse) survey of how complex the
Cheetah-templated sections of corpus tools are — backing
`upgrade_research/cheetah_variable_rewriting.md`, which assesses whether
variables in those sections can be located/rewritten mechanically.

Galaxy Cheetah-processes `<command>`, inline `<configfile>` (XML tools'
default engine), env-var templates, and output `label`s (`lib/galaxy/tools/evaluation.py:767,952`, `tools/actions/__init__.py:1091`).
This survey covers the two large ones: `<command>` and inline `<configfile>`.
Because it is a regex heuristic, directive counts are roughly a **lower**
bound (a construct can hide) and shape counts roughly an **upper** bound (a
`$x` inside a `##` comment or `#raw` block still matches).

Regenerate with (needs the corpus, so not run in CI):

```sh
uv run python -m scripts.measure cheetah-command-complexity
```

## Overview

| Measure | Tools | Share |
|---|--:|--:|
| Unique `<tool>` files (sha256-deduped) | 9,358 | — |
| Have a `<command>` | 9,318 | 99.6% |
| `<command>` is **trivial** (no Cheetah directive) | 3,928 | 42.2% of commands |
| `<command>` has a Cheetah directive | 5,390 | 57.8% of commands |
| Have an inline `<configfile>` (also Cheetah) | 851 | 9.1% |
| Have an `<expand>` (macro inclusion) | 4,527 | 48.4% |
| Have any Cheetah text (command + inline configfile) | 9,333 | 99.7% |

Feature counts below are over the **9,333** tools with Cheetah text (command and/or inline configfile).

## Directives

| Construct | Tools | Share |
|---|--:|--:|
| #if | 5,113 | 54.8% |
| #for | 1,438 | 15.4% |
| #set | 1,533 | 16.4% |
| #def | 21 | 0.2% |
| #import | 707 | 7.6% |
| #echo | 186 | 2.0% |
| #while | 1 | 0.0% |
| #try | 10 | 0.1% |
| #raw | 15 | 0.2% |
| #slurp | 38 | 0.4% |

## Variable shapes

| Construct | Tools | Share |
|---|--:|--:|
| ${...} braced | 3,947 | 42.3% |
| $x.y dotted attribute | 5,297 | 56.8% |
| $x[...] indexing | 246 | 2.6% |
| $x(...) call | 1,169 | 12.5% |
| $__x__ Galaxy special | 2,705 | 29.0% |
| $UPPER env-style | 1,650 | 17.7% |

## Rewrite hazards

| Construct | Tools | Share |
|---|--:|--:|
| ## Cheetah comment | 1,840 | 19.7% |
| \$ escaped dollar | 1,706 | 18.3% |

## Macro interplay

| Construct | Tools | Share |
|---|--:|--:|
| @TOKEN@ macro token | 1,488 | 15.9% |

The `#set` / `#for` / `#def` rows are the scope-introducing hazards: each
binds Cheetah-local names that can shadow tool parameters, so a parameter
rename cannot be a blind textual substitution. See the research doc for what
this implies for feasibility.
