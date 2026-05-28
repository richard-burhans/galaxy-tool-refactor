# Corpus data (fine-grained)

Per-tool data tables emitted alongside the aggregate
`docs/*_corpus_stats.md` artifacts by `scripts/corpus_check.py`. Each
table is provided as both **JSON** (an array of objects) and **TSV** (a
header row plus one tab-separated row per tool).

## Files

| Source | JSON | TSV |
|---|---|---|
| github | `corpus_data.json` | `corpus_data.tsv` |
| toolshed | `toolshed_corpus_data.json` | `toolshed_corpus_data.tsv` |
| combined | `combined_corpus_data.json` | `combined_corpus_data.tsv` |

## Per-source schema (`corpus_data.*`, `toolshed_corpus_data.*`)

| Column | Description |
|---|---|
| `repo` | github: name from `corpus_sources.json`; toolshed: `<owner>/<name>` |
| `version` | github: full git SHA from the local clone; toolshed: short hg changeset from `corpus/galaxy-toolshed/manifest.json` (or `unknown` for clones fetched before the manifest existed) |
| `path` | XML file path relative to its repository directory |
| `tool_id` | post-macro-expansion `@id` on the `<tool>` element; falls back to the raw `@id` (often a macro-token string) on expansion failure |
| `sha256` | sha256 of the XML file's bytes |

## Combined schema (`combined_corpus_data.*`)

The five columns above, plus:

| Column | Description |
|---|---|
| `profile_raw` | literal `profile` attribute on the un-expanded tree, or `(none)` |
| `profile_expanded` | `profile` after macro expansion, or `(none)` / `(expansion failed)` |
| `newest_valid` | newest vendored profile that validates the tool, or `(none)` |
| `expansion_failure_reason` | category for the first macro-expansion error when expansion failed; `null` in JSON (empty string in TSV) when the tool's macros expanded cleanly |
| `no_valid_reason` | category for why no vendored profile accepts the tool when its validity vector is empty; `null` in JSON (empty string in TSV) when at least one profile validates |
| `presence` | cross-source presence keyed on `tool_id`: `github_only` / `toolshed_only` / `both`, or the empty string when `tool_id` itself is empty. The same value is stamped on every row sharing the same `tool_id`, regardless of which source the row came from. |
| `valid_<profile>` | one column per vendored profile (`valid_16.10`, `valid_17.01`, …, `valid_26.1`), value `1` if the tool validates against that profile's XSD and `0` otherwise; integers in JSON, `0` / `1` literals in TSV |

The combined artifact records **all occurrences** of each tool — one row
per `(source, repo, path)` triple, even when two repositories ship the
same bytes. The aggregate counts in `docs/combined_corpus_stats.md`
remain deduplicated by sha256, so a row count in the combined data file
typically exceeds the "Swept N unique tools" line in the markdown by the
number of duplicates dropped (see the Sources table there).

The `valid_<profile>` columns together form each tool's full **validity
vector** — the same vector `newest_valid_profile` scans newest-first.
The vector is **not guaranteed contiguous**: a tool can be valid at
profile A, invalid at a later profile B, then valid again at C (see
`docs/decisions.md` §10.3). Downstream consumers should treat each
column independently rather than assuming a single contiguous range.

## Failure-mode detail pages

Every combined sweep also writes `failures/` (one markdown per
failure-reason category) plus a `failures/README.md` index. The
reason cells in the two failure tables of
`docs/combined_corpus_stats.md` are markdown links into these files;
each detail page lists the failing tools with a clickable URL into
their upstream source (github.com, gitlab.com, or the Galaxy
ToolShed) at the captured version. Tools are deduplicated by sha256
so the counts match the aggregate stats.

## Regeneration

```sh
uv run python -m scripts.corpus_check validate --source github
uv run python -m scripts.corpus_check validate --source toolshed
uv run python -m scripts.corpus_check validate --source combined
```

Each invocation refreshes the data files for that source together with
the corresponding markdown artifact. Partial sweeps (`--limit`,
`--repo`, or `--no-stats`) leave both untouched.
