"""Coarse detection for validation-driven codemods.

The structural reorderers compute a per-occurrence change list directly. The
validation-driven codemods (``FixTypos``, ``UpdateProfile``, ``UpgradeToLatest``
and the per-step upgrades) cannot: they branch on re-validation, so there is no
static change list to pre-compute. Their detect phase is therefore **coarse** —
it answers only "would applying this codemod change the tool?" by running the
codemod on a throwaway copy and comparing the serialised tree. When the answer
is yes it yields a single ``Change`` located at the root ``<tool>`` whose thunk
runs the real ``apply``; otherwise it yields nothing.

This keeps detect/apply parity (detect yields ⇔ apply mutates) for the sweep's
parity gate without pretending to a precision these codemods cannot offer; the
per-occurrence lint value concentrates in the structural and detect-only rules.
See ``docs/decisions.md`` § on the detect/fix split.
"""

from __future__ import annotations

import copy
from collections.abc import Iterator

from galaxy_tool_source.document import ToolDocument
from lxml import etree

from galaxy_tool_codemod.change import Change
from galaxy_tool_codemod.codemod import CodemodCommand
from galaxy_tool_codemod.module import Module


def coarse_detect(
    codemod: CodemodCommand, module: Module, /, *, message: str
) -> Iterator[Change]:
    """Yield one root-level ``Change`` iff applying *codemod* would alter *module*.

    Runs a fresh instance of *codemod* on a deep copy of *module* and compares
    the serialised tree before and after. Both snapshots come from the copy, so
    any representation shift introduced by ``deepcopy`` cancels out and only a
    real mutation registers. The yielded change is located on the *original*
    tree's root and its thunk applies *codemod* to the original module.

    The copy keeps the original's ``source_path`` so the validation-driven
    codemods resolve macro ``<import>``s the same way they do on the real
    document — without it the copy would validate differently and detect would
    drift from apply.
    """
    work = Module(
        ToolDocument(
            copy.deepcopy(module.document.tree),
            source_path=module.document.source_path,
        )
    )
    before = etree.tostring(work.document.tree)
    type(codemod)().apply(work)
    after = etree.tostring(work.document.tree)
    if after == before:
        return
    root = module.cursor
    yield Change(
        code=codemod.meta.code,
        sourceline=root.sourceline,
        xpath=root.xpath,
        message=message,
        mutate=lambda: codemod.apply(module),
    )
