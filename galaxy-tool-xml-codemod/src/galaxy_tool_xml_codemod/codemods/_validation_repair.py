"""Shared snapshot/restore helper for validation-driven codemods.

The validation-driven codemods (``FixTypos``, ``NormalizeBooleanValues``) try a
mutation, re-validate, and revert when it does not restore validity. Reverting
must keep the *live* root element's identity — the frozen ``Module`` holds the
document by reference and the corpus sweep reads it after ``apply`` returns — so
the tree is rewritten in place from a deep-copied snapshot rather than swapped.
"""

from __future__ import annotations

import copy

from lxml import etree


def restore_root(live: etree._Element, source: etree._Element, /) -> None:
    """Overwrite *live*'s entire state in place from *source*.

    ``live`` keeps its identity; its tag, attributes, text, tail, and children
    are rewritten from a deep copy of ``source``. Children are grafted as deep
    copies so a reused snapshot stays pristine across attempts.
    """
    live.tag = source.tag
    live.text = source.text
    live.tail = source.tail
    live.attrib.clear()
    live.attrib.update(source.attrib)
    for child in list(live):
        live.remove(child)
    for child in source:
        live.append(copy.deepcopy(child))
