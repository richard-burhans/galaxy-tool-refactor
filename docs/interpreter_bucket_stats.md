# Interpreter-rewrite bucket statistics

Sizes the auto-fixable population for a `16_04_fix_interpreter` codemod
(GTR016; see `upgrade_research/16_04_fix_interpreter.md`). Tools carrying a
deprecated `<command interpreter=…>` are split by whether the codemod can
mechanically rewrite them to `interpreter '$__tool_directory__/script'`.
Buckets are computed by the codemod's own eligibility predicate
(`galaxy_tool_xml_codemod.codemods._interpreter`), so the A + A-missing
total is exactly what the codemod rewrites.

Regenerate with (needs the corpus, so not run in CI):

```sh
uv run python -m scripts.measure interpreter-bucket-split
```

Unique `<tool>` files (sha256-deduped): **9,358**. With a
`<command interpreter=…>`: **1,728** (the table shares below are of this population).

## Buckets

| Bucket | Tools | Share | Meaning |
|---|--:|--:|---|
| **A — auto-fixable** | 1,407 | 81.4% | any non-empty interpreter (incl. flags / `java -jar` — the legacy composition is verbatim concatenation) + literal leading script that exists beside the XML |
| A-missing | 28 | 1.6% | structurally A but the named script isn't co-located — still rewritten (the codemod has no file-exists gate; the split is a measurement refinement) |
| B — leading Cheetah / non-literal | 293 | 17.0% | command starts with a `#`-directive or `$var`, so the script isn't statically first |
| empty `interpreter=""` | 0 | 0.0% | legacy gated on `if interpreter:` — the attribute was ignored, so there is no composition to reproduce |

Buckets **A + A-missing** (1,435 tools) are the codemod's target — the file-exists split is a measurement-only refinement, not a codemod gate (`fix_interpreter.py` calls the eligibility predicate with no `tool_dir`). Only **B** (and the degenerate empty attribute) remains detect/warn-only (the §23 upgrade warning) — the rendered first token needs author intent or a richer parse.

## Interpreter values

| `interpreter=` | Tools | Histogram |
|---|--:|---|
| `python` | 984 | ██████████████████████████████ |
| `perl` | 374 | ███████████ |
| `bash` | 224 | ███████ |
| `Rscript` | 58 | ██ |
| `docker` | 20 | █ |
| `sh` | 16 |  |
| `python2.7` | 15 |  |
| `java -jar ` | 10 |  |
| `java -jar` | 9 |  |
| `python3` | 5 |  |
| `command` | 3 |  |
| `/usr/bin/php` | 2 |  |
| `Rscript --vanilla` | 2 |  |
| `/usr/local/anaconda/bin/python` | 1 |  |
| `Rscript --no-save` | 1 |  |
| `export DISPLAY=:995; java -jar ` | 1 |  |
| `python -W ignore` | 1 |  |
| `python -W ignore::DeprecationWarning` | 1 |  |
| `ruby` | 1 |  |
