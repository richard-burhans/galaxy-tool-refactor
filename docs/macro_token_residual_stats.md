# Macro token-supplied datatype residual (Phase-2b sizing)

Sizes what Phase 2a (literal `format`/`ftype` normalization) leaves on the
table: tools still stuck below the latest profile that reach a newer one
only when the **token-supplied** datatype values are also normalized — a
`format="@FORMAT@"` whose `<token>` value is coercible (e.g. `GTiff`).
Both fixes are *locate-in-source* (the token's definition), so this sizes
the cheap Phase-2 consumer; a near-zero count means the heavyweight
expansion-provenance layer (M1) is unjustified for datatypes (see the 2b
design note). Sound: temp-copy, normalize literals (baseline) then
literals+token-values, count only a strict profile increase from the tokens.

Regenerate with (needs the corpus, so not run in CI):

```sh
uv run python -m scripts.measure macro-token-datatype-residual
```

Unique `<tool>` files (sha256-deduped): **9,358**; with a
coercible token-supplied `format`/`ftype` and stuck below latest: **0**.

## Tools unstuck by normalizing the token value (beyond Phase 2a)

- **Residual tools:** 0
- helping token defined **inline** only (Upgrade24_1 extension): 0
- **imported** token involved (macro_profile-shape consensus): 0
