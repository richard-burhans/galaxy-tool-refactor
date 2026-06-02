# Cheetah command/configfile complexity statistics

A **heuristic** (regex, not a Cheetah parse) survey of how complex the
Cheetah-templated sections of corpus tools are — backing
`upgrade_research/cheetah_variable_rewriting.md`, which assesses whether
variables in those sections can be located/rewritten mechanically.

Galaxy Cheetah-processes `<command>`, inline `<configfile>` (XML tools'
default engine), env-var templates, and output `label`s (`lib/galaxy/tools/evaluation.py:767,952`, `tools/actions/__init__.py:1091`).
This survey covers the two large ones: `<command>` and inline `<configfile>`.
Because it is a regex heuristic (not a Cheetah parse), counts are noisy in
**both** directions: a construct can hide from the pattern (under-count), and
a `#`-keyword or `$x` sitting inside a `##` comment or a `#raw`…`#end raw`
block still matches even though Cheetah would not treat it as live
(over-count). The directive over-count is negligible in practice (only a
handful of commands match a directive *solely* inside a comment/raw block),
so the trivial-vs-directive headline is, if anything, conservative for the
trivial (easy) subset.

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

The `##` (Cheetah comment) row is an **upper bound** on Cheetah comments: the
regex `##` also matches POSIX shell parameter expansion `${var##*/}` (a common
basename idiom in `ln -s` setups), so an unknown fraction of these tools carry
shell `##`, not a Cheetah comment — do not read its share as Cheetah-comment
prevalence. The direction is conservative (it makes the hazard-free subset look
smaller), so it does not threaten the feasibility conclusion.
