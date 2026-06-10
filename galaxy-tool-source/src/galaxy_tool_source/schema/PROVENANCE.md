# Vendored Galaxy Tool XSDs — Provenance

This directory holds vendored copies of Galaxy's tool definition schema
(`galaxy.xsd`), one `galaxy-<version>.xsd` file per Galaxy release that ships
it. They are internal, permanent assets of this repository.

## Methodology

`scripts/fetch_schemas.py` lists the `release_*` branches of
`galaxyproject/galaxy` via the GitHub REST `git/matching-refs` endpoint, then
downloads `galaxy.xsd` from each branch — trying
`lib/galaxy/tool_util/xsd/galaxy.xsd` first and the older
`lib/galaxy/tools/xsd/galaxy.xsd` second. Releases that ship neither (they
predate the XSD) are skipped. Each commit SHA below is the branch head at
retrieval time.

## Vendored schemas

| Version | Release branch | Commit | Path in repo | Source URL | Retrieved |
| --- | --- | --- | --- | --- | --- |
| 26.1 | release_26.1 | 0040ec81df48eb2684447837627fb4f76d013263 | `lib/galaxy/tool_util/xsd/galaxy.xsd` | https://raw.githubusercontent.com/galaxyproject/galaxy/release_26.1/lib/galaxy/tool_util/xsd/galaxy.xsd | 2026-05-27 |
| 26.0 | release_26.0 | cb36b7065a5736135f6ec56b16aab792176fce55 | `lib/galaxy/tool_util/xsd/galaxy.xsd` | https://raw.githubusercontent.com/galaxyproject/galaxy/release_26.0/lib/galaxy/tool_util/xsd/galaxy.xsd | 2026-05-22 |
| 25.1 | release_25.1 | ad8e40de4a42e80e4064716d5342ad0952f53ce2 | `lib/galaxy/tool_util/xsd/galaxy.xsd` | https://raw.githubusercontent.com/galaxyproject/galaxy/release_25.1/lib/galaxy/tool_util/xsd/galaxy.xsd | 2026-05-22 |
| 25.0 | release_25.0 | 48c78404f68e4e081ae0dbc011c5dc99dbc66357 | `lib/galaxy/tool_util/xsd/galaxy.xsd` | https://raw.githubusercontent.com/galaxyproject/galaxy/release_25.0/lib/galaxy/tool_util/xsd/galaxy.xsd | 2026-05-22 |
| 24.2 | release_24.2 | 7e8182b9efccd1e9ef2135c0e200f64f63d42a3d | `lib/galaxy/tool_util/xsd/galaxy.xsd` | https://raw.githubusercontent.com/galaxyproject/galaxy/release_24.2/lib/galaxy/tool_util/xsd/galaxy.xsd | 2026-05-22 |
| 24.1 | release_24.1 | 7e216fda581e16bc3757a66cfc4ce91efe3c0d39 | `lib/galaxy/tool_util/xsd/galaxy.xsd` | https://raw.githubusercontent.com/galaxyproject/galaxy/release_24.1/lib/galaxy/tool_util/xsd/galaxy.xsd | 2026-05-22 |
| 24.0 | release_24.0 | e61a74b4fbddbc39720246a3221b4da6a2288d11 | `lib/galaxy/tool_util/xsd/galaxy.xsd` | https://raw.githubusercontent.com/galaxyproject/galaxy/release_24.0/lib/galaxy/tool_util/xsd/galaxy.xsd | 2026-05-22 |
| 23.2 | release_23.2 | 7d4b3de58fd3627e930e9ed413b272f2f0ee1675 | `lib/galaxy/tool_util/xsd/galaxy.xsd` | https://raw.githubusercontent.com/galaxyproject/galaxy/release_23.2/lib/galaxy/tool_util/xsd/galaxy.xsd | 2026-05-22 |
| 23.1 | release_23.1 | 205e32f88445a161e376c2171403c75c2334a8d6 | `lib/galaxy/tool_util/xsd/galaxy.xsd` | https://raw.githubusercontent.com/galaxyproject/galaxy/release_23.1/lib/galaxy/tool_util/xsd/galaxy.xsd | 2026-05-22 |
| 23.0 | release_23.0 | 262d48a71166d2e778de1bdee839157c8385c6fc | `lib/galaxy/tool_util/xsd/galaxy.xsd` | https://raw.githubusercontent.com/galaxyproject/galaxy/release_23.0/lib/galaxy/tool_util/xsd/galaxy.xsd | 2026-05-22 |
| 22.05 | release_22.05 | 3e511c1b2b970ad016e8575c5c6f947cc7648a31 | `lib/galaxy/tool_util/xsd/galaxy.xsd` | https://raw.githubusercontent.com/galaxyproject/galaxy/release_22.05/lib/galaxy/tool_util/xsd/galaxy.xsd | 2026-05-22 |
| 22.01 | release_22.01 | 101d4a6d41e9118849f946f0418580d3121400d6 | `lib/galaxy/tool_util/xsd/galaxy.xsd` | https://raw.githubusercontent.com/galaxyproject/galaxy/release_22.01/lib/galaxy/tool_util/xsd/galaxy.xsd | 2026-05-22 |
| 21.09 | release_21.09 | 0a039981bb2465064595f789c28a1ba1a765e7a9 | `lib/galaxy/tool_util/xsd/galaxy.xsd` | https://raw.githubusercontent.com/galaxyproject/galaxy/release_21.09/lib/galaxy/tool_util/xsd/galaxy.xsd | 2026-05-22 |
| 21.05 | release_21.05 | 9a9c4a8eb85211d627d5dbe3573656eb9c22e2e3 | `lib/galaxy/tool_util/xsd/galaxy.xsd` | https://raw.githubusercontent.com/galaxyproject/galaxy/release_21.05/lib/galaxy/tool_util/xsd/galaxy.xsd | 2026-05-22 |
| 21.01 | release_21.01 | b1da9d832eb8e4155d4f194a9e17b4a6b41319c9 | `lib/galaxy/tool_util/xsd/galaxy.xsd` | https://raw.githubusercontent.com/galaxyproject/galaxy/release_21.01/lib/galaxy/tool_util/xsd/galaxy.xsd | 2026-05-22 |
| 20.09 | release_20.09 | 13ab9430b369b6172621e34e3b3d4ca264a04356 | `lib/galaxy/tool_util/xsd/galaxy.xsd` | https://raw.githubusercontent.com/galaxyproject/galaxy/release_20.09/lib/galaxy/tool_util/xsd/galaxy.xsd | 2026-05-22 |
| 20.05 | release_20.05 | 99b3d29e69c905996c6c26296a89650b7ee1755b | `lib/galaxy/tool_util/xsd/galaxy.xsd` | https://raw.githubusercontent.com/galaxyproject/galaxy/release_20.05/lib/galaxy/tool_util/xsd/galaxy.xsd | 2026-05-22 |
| 20.01 | release_20.01 | ae59839ab0d098cb6838aae7182508cd33628053 | `lib/galaxy/tool_util/xsd/galaxy.xsd` | https://raw.githubusercontent.com/galaxyproject/galaxy/release_20.01/lib/galaxy/tool_util/xsd/galaxy.xsd | 2026-05-22 |
| 19.09 | release_19.09 | f0a269c1912fa5caba760cde32df415e8e2329b6 | `lib/galaxy/tool_util/xsd/galaxy.xsd` | https://raw.githubusercontent.com/galaxyproject/galaxy/release_19.09/lib/galaxy/tool_util/xsd/galaxy.xsd | 2026-05-22 |
| 19.05 | release_19.05 | d48c4a467853a92175a49e1ce8b1cdaf75c3af1d | `lib/galaxy/tools/xsd/galaxy.xsd` | https://raw.githubusercontent.com/galaxyproject/galaxy/release_19.05/lib/galaxy/tools/xsd/galaxy.xsd | 2026-05-22 |
| 19.01 | release_19.01 | ed282c2818c3df0b548ed288e9a000f23ac91bcb | `lib/galaxy/tools/xsd/galaxy.xsd` | https://raw.githubusercontent.com/galaxyproject/galaxy/release_19.01/lib/galaxy/tools/xsd/galaxy.xsd | 2026-05-22 |
| 18.09 | release_18.09 | 80aa2f8ea40813e162ec4caac552609b54d7d95d | `lib/galaxy/tools/xsd/galaxy.xsd` | https://raw.githubusercontent.com/galaxyproject/galaxy/release_18.09/lib/galaxy/tools/xsd/galaxy.xsd | 2026-05-22 |
| 18.05 | release_18.05 | 0299798a4f4e6a08841d10acc8953c9b5dac3af9 | `lib/galaxy/tools/xsd/galaxy.xsd` | https://raw.githubusercontent.com/galaxyproject/galaxy/release_18.05/lib/galaxy/tools/xsd/galaxy.xsd | 2026-05-22 |
| 18.01 | release_18.01 | 9cdfd18f5027fdd0fec87a0982771c87d6a5640e | `lib/galaxy/tools/xsd/galaxy.xsd` | https://raw.githubusercontent.com/galaxyproject/galaxy/release_18.01/lib/galaxy/tools/xsd/galaxy.xsd | 2026-05-22 |
| 17.09 | release_17.09 | b04b3d949baaf32c9a9d9127c5a61250ffb580dd | `lib/galaxy/tools/xsd/galaxy.xsd` | https://raw.githubusercontent.com/galaxyproject/galaxy/release_17.09/lib/galaxy/tools/xsd/galaxy.xsd | 2026-05-22 |
| 17.05 | release_17.05 | e0a06a36e22deb1a391bc3afd45c993f29052731 | `lib/galaxy/tools/xsd/galaxy.xsd` | https://raw.githubusercontent.com/galaxyproject/galaxy/release_17.05/lib/galaxy/tools/xsd/galaxy.xsd | 2026-05-22 |
| 17.01 | release_17.01 | 61e6fd11424a9036573db2bf3ef9a8bee9d6b19a | `lib/galaxy/tools/xsd/galaxy.xsd` | https://raw.githubusercontent.com/galaxyproject/galaxy/release_17.01/lib/galaxy/tools/xsd/galaxy.xsd | 2026-05-22 |
| 16.10 | release_16.10 | 267037fa7a3488cd4e24a5fce89eb84326669005 | `lib/galaxy/tools/xsd/galaxy.xsd` | https://raw.githubusercontent.com/galaxyproject/galaxy/release_16.10/lib/galaxy/tools/xsd/galaxy.xsd | 2026-05-22 |

## Third-party attribution

These XSD files are extracted verbatim from the Galaxy project
(`galaxyproject/galaxy`, <https://github.com/galaxyproject/galaxy>) and
remain subject to that project's license. They are redistributed here
unmodified as a convenience for offline, profile-aware validation.
