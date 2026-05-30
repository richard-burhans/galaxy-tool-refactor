# Macro corpus statistics

Phase-0 measurements for the macro-aware refactoring plan: how Galaxy
tool macros are organised across the combined corpus (parsing, sharing,
tokens, `<yield>`), and how often a macro-token `profile=` is stale. These
numbers gate the macro-aware design decisions (shared-macro edit policy,
token-aware profile upgrades, deferring `<yield>`).

Regenerate with:

```sh
uv run python -m scripts.measure macro-topology
```

Unique `<tool>` files (sha256-deduped): **9,358** (3,638 non-`<tool>`-root or unparseable XML files skipped — including the macro libraries themselves).

## Macro organisation

| Bucket | Tools | Share |
|---|--:|--:|
| No macros | 4,233 | 45.2% |
| Inline `<macros>` only | 648 | 6.9% |
| Imports a macro file | 4,477 | 47.8% |

Tools with an unresolved `<import>` (target missing on disk): **1**.

## Construct usage

| Construct | Tools | Share |
|---|--:|--:|
| `<expand>` | 4,527 | 48.4% |
| `<yield>` (tool + its macro files) | 3,051 | 32.6% |
| `<yield name=...>` (named) | 44 | 0.5% |
| defines `<macro>` | 128 | 1.4% |

`<yield>` appears in the inline or imported macros of a third of tools,
but named yields and tool-defined `<macro>`s are rare. v1 must therefore
**preserve** `<yield>`/`<macro>` faithfully; yield-aware *editing*
(resolving parameterized macros) can still defer to a later phase.

## Shared macro files (blast-radius input)

Distinct imported macro files: **3,368**; imported by more than one tool: **203**; max importers of a single file: **137**.

Importer-count distribution (how many tools import each macro file):

| Importers | Macro files |
|--:|--:|
| 1 | 3,165 |
| 2 | 84 |
| 3 | 34 |
| 4 | 13 |
| 5 | 8 |
| 6 | 6 |
| 7 | 9 |
| 8 | 7 |
| 9 | 8 |
| 10 | 2 |
| 11 | 2 |
| 12 | 6 |
| 13 | 2 |
| 14 | 1 |
| 15 | 2 |
| 16 | 2 |
| 19 | 1 |
| 20 | 2 |
| 21 | 1 |
| 22 | 1 |
| 28 | 1 |
| 29 | 2 |
| 31 | 1 |
| 34 | 1 |
| 37 | 1 |
| 40 | 1 |
| 48 | 1 |
| 62 | 1 |
| 107 | 2 |
| 137 | 1 |

Most-shared macro files:

| Importers | Macro file |
|--:|---|
| 137 | `corpus/bgruening-galaxytools/tools/openms/macros.xml` |
| 107 | `corpus/galaxy-toolshed/devteam/emboss_5/macros.xml` |
| 107 | `corpus/tools-iuc/tools/emboss_5/macros.xml` |
| 62 | `corpus/galaxy-toolshed/luis/ball/galaxy_stubs/macros.xml` |
| 48 | `corpus/tools-iuc/tools/mothur/macros.xml` |
| 40 | `corpus/galaxy-toolshed/malex/secimtools/macros.xml` |
| 37 | `corpus/galaxy-toolshed/iuc/bedtools/macros.xml` |
| 34 | `corpus/tools-iuc/tools/qiime/qiime_core/macros.xml` |
| 31 | `corpus/galaxy-toolshed/devteam/picard/picard_macros.xml` |
| 29 | `corpus/galaxy-toolshed/avowinkel/picard/picard_macros.xml` |
| 29 | `corpus/galaxy-toolshed/devteam/picard_plus/picard_macros.xml` |
| 28 | `corpus/galaxy-toolshed/frogs/frogs/macros.xml` |
| 22 | `corpus/galaxy-toolshed/nilesh/rseqc/rseqc_macros.xml` |
| 21 | `corpus/galaxy-toolshed/rnateam/vienna_rna/macros.xml` |
| 20 | `corpus/galaxy-toolshed/bgruening/text_processing/macros.xml` |

## Tokens

`profile=` is a macro token: **1,486** (token defined inline 102 / in an imported file 1,384 / unresolved 0). `version=` is a token: **4,325**.

Notable token names (tools that define or import them):

| Token | Tools |
|---|--:|
| `@TOOL_VERSION@` | 2,933 |
| `@VERSION_SUFFIX@` | 2,152 |
| `@WRAPPER_VERSION@` | 704 |
| `@GALAXY_VERSION@` | 193 |
| `@PROFILE@` | 1,435 |
| `@TOOL_CITATION@` | 13 |

## Stale macro-token profiles (token-aware upgrade target)

Of the tools whose `profile=` is a macro token, how the token's
*expanded* value compares to the newest profile the tool validates at
(profiles compared with `packaging.version`). **Upgradeable** is the
motivating case: rewriting the token *definition* would advance the
tool, where today's `UpdateProfile` would clobber the `@TOKEN@`
reference with a literal.

| Outcome | Tools |
|---|--:|
| profile= is a macro token | 1,486 |
| └ upgradeable (token value stale) | 1,485 |
| └ already current | 0 |
| └ token ahead of validity | 0 |
| └ validates at no profile | 1 |
| └ unparseable profile value | 0 |

Upgradeable exemplars (`raw` → expands → validates):

- `data_managers/data_manager_bmtagger_index_builder/data_manager/bmtagger.xml`: `@PROFILE@` → 24.0 → validates 26.1
- `data_managers/data_manager_build_amrfinderplus/data_manager/data_manager_build_amrfinderplus.xml`: `@PROFILE@` → 21.05 → validates 26.1
- `data_managers/data_manager_build_bakta_database/data_manager/bakta_build_database.xml`: `@PROFILE@` → 21.05 → validates 26.1
- `data_managers/data_manager_build_bracken_database/data_manager/bracken_build_database.xml`: `@PROFILE@` → 24.0 → validates 26.1
- `data_managers/data_manager_build_coreprofiler/data_manager/data_manager_build_coreprofiler_download.xml`: `@PROFILE@` → 22.05 → validates 26.1
- `data_managers/data_manager_build_kraken2_database/data_manager/kraken2_build_database.xml`: `@PROFILE@` → 24.0 → validates 26.1
- `data_managers/data_manager_build_staramr/data_manager/data_manager_build_staramr_download.xml`: `@PROFILE@` → 22.05 → validates 26.1
- `data_managers/data_manager_checkm2/data_manager/checkm2_datamanager.xml`: `@PROFILE@` → 23.1 → validates 26.1
- `data_managers/data_manager_fetch_plasmidfinder/data_manager/plasmidfinder_fetch_database.xml`: `@PROFILE@` → 21.05 → validates 26.1
- `data_managers/data_manager_groot_database_downloader/data_manager/data_manager_groot_database_downloader.xml`: `@PROFILE@` → 22.05 → validates 26.1

