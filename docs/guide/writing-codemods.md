# Writing a codemod

A *codemod* is a structural fix: it rewrites the tool tree (reorder attributes, drop a
redundant one, rewrite an output element) while preserving behaviour. Codemods live in
tier 2, `galaxy-tool-codemod`, and this page is the short version of how to add one. The
authoritative, step-by-step workflow is the `add-codemod` skill in the repository
(`.claude/skills/add-codemod/`); the architecture context is
[`ARCHITECTURE.md`](https://github.com/richard-burhans/galaxy-tool-refactor/blob/main/ARCHITECTURE.md).

## The two principles

1. **TDD first.** Write the failing test, then the minimum code to pass. One test module
   per source module.
2. **Detect is the primitive.** A codemod *reports* exactly what it will change as a list
   of `Change` objects; the base class derives `apply` from that. You do not write a
   separate mutation pass for an ordinary codemod, so detect and fix can never disagree.

The public surface a test drives:

```python
from galaxy_tool_codemod.parse import parse_module

module = parse_module(b"<tool>...</tool>")     # or a Path
changes = MyCodemod().detect(module)            # list[Change], non-mutating
MyCodemod().apply(module)                        # mutates the tree in place
```

## A minimal codemod

This is the real shape of `DropRedundantParamName` (GTR037), which drops a `<param>`
`name` that its `argument` already implies:

```python
from typing import ClassVar
from galaxy_tool_refactor_rules.meta import RuleMeta
from galaxy_tool_codemod.change import Change
from galaxy_tool_codemod.codemod import CodemodCommand


class DropRedundantParamName(CodemodCommand):
    meta: ClassVar[RuleMeta] = RuleMeta(
        code="GTR037",                      # the next free code (the registry asserts no collision)
        summary="Drop a <param> 'name' that equals the name its 'argument' implies.",
        since="0.0.1",
        rulesets=frozenset({"default", "iuc", "strict"}),
    )

    def detect_Param(self, cursor):         # dispatch by tag: <param> -> detect_Param
        argument = cursor.get_attribute("argument")
        name = cursor.get_attribute("name")
        if argument is None or name is None or name != argument.lstrip("-").replace("-", "_"):
            return
        yield Change(
            code=self.meta.code,
            sourceline=cursor.sourceline,
            xpath=cursor.xpath,
            message=f"drop redundant name='{name}' (argument '{argument}' implies it)",
            mutate=lambda: cursor.delete_attribute("name"),
        )
```

The pieces:

- **Subclass `CodemodCommand`** and set `meta: ClassVar[RuleMeta]` with the next free GTR
  code, a `summary`, and `since`. `applies_to` defaults to `{"tool"}`; opt into
  `"macro"` only for a rule that is generic across both.
- **`detect_<TagPascalCase>` methods** are dispatched by element tag (`<param>` →
  `detect_Param`, `<change_format>` → `detect_ChangeFormat`). Each `yield`s a `Change`
  whose `mutate` is a zero-argument closure over `Cursor` primitives:
  `set_attribute` / `delete_attribute` / `rename_attribute` / `rename_tag` /
  `reorder_attributes` / `reorder_children` / `remove` / `add_child` / `set_text`.
- The fix must hold **by construction for novel tools**, with a Galaxy-source or schema
  citation, never "no corpus tool does this." That argument is recorded in a proof doc
  (see the [rule proofs](proofs/index.md)); a guard test fails CI if a fixable rule ships
  without one.

## Registering it

- **Always** add the class to `catalog.py::coded_codemods()`. This is what the cross-tier
  registry enumerates, and it asserts GTR codes do not collide.
- Add it to `canonical.py::canonical_codemods()` **only if** it is safe, idempotent, and
  `profile=`-preserving. That is what makes it run under `format` and the `iuc` ruleset.
  Mind the order: `FixTypos` runs first, attribute reorders before child reorders.
- No registry edits are needed: `galaxy-tool-refactor-registry` derives its handles from
  these two functions.

## Proving it on the corpus

Sweep the new codemod over the tool corpus to check idempotence and post-fix validity,
and to retain any real-world failure as a regression fixture:

```console
$ uv run python -m scripts.corpus_check codemod \
    galaxy_tool_codemod.codemods.drop_redundant_param_name:DropRedundantParamName
```

Any tool that breaks is copied into `tests/data/regressions/` and picked up
automatically by `tests/test_regressions.py`. Investigate and fix every retained
failure, then run the pre-PR audit before opening a pull request.

A codemod that must branch on re-validation (like `FixTypos` or `UpgradeToLatest`) is the
exception: it overrides `apply` with bespoke logic and supplies a coarse `detect`. The
`add-codemod` skill covers that variant and the profile-upgrade (`upgrade_vN`) case.
