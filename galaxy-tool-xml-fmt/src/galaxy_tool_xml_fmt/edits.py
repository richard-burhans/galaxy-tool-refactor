"""Discriminated-union ``Edit`` type and the ``apply_edits`` dispatcher.

Each ``Edit`` variant is a frozen dataclass describing one canonical-form
mutation. ``apply_edits`` walks an iterable of edits and dispatches via
``match/case`` — the single place that mutates the lxml tree, and the
single place that honours the CDATA whitespace-only guard (via
``serializer.safe_set_text`` / ``safe_set_tail``). Individual rules stay
pure: they describe what to change, they do not touch the tree
themselves.

``NoOp`` is retained as a test affordance for cases that exercise the
pipeline without mutating the tree.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, TypeAlias

from galaxy_tool_xml_fmt.serializer import safe_set_tail, safe_set_text

if TYPE_CHECKING:
    from collections.abc import Iterable

    from lxml import etree


@dataclass(frozen=True)
class NoOp:
    """Sentinel edit; emits no tree mutation."""


@dataclass(frozen=True)
class SetText:
    """Set ``element.text`` if the current value is whitespace-only.

    The CDATA-safety guard lives in ``safe_set_text``; this edit will
    silently skip elements whose ``.text`` carries non-whitespace
    content (which is what CDATA looks like at the Python level).
    """

    element: etree._Element
    value: str


@dataclass(frozen=True)
class SetTail:
    """Set ``element.tail`` if the current value is whitespace-only."""

    element: etree._Element
    value: str


@dataclass(frozen=True)
class ClearText:
    """Set ``element.text`` to ``None`` if the current value is whitespace-only.

    Distinct from ``SetText``: ``ClearText`` removes the text entirely,
    letting lxml serialise the element as ``<foo/>``. ``SetText("")``
    would leave an empty string in place, which lxml emits as
    ``<foo></foo>``.
    """

    element: etree._Element


Edit: TypeAlias = NoOp | SetText | SetTail | ClearText


def apply_edits(edits: Iterable[Edit]) -> None:
    """Apply each edit to its element, dispatching by variant.

    The single place trivia mutations land: ``SetText`` / ``SetTail`` go through
    the CDATA-safe setters, ``ClearText`` empties a whitespace-only leaf, and
    ``NoOp`` is skipped.
    """
    for edit in edits:
        match edit:
            case NoOp():
                pass
            case SetText(element=element, value=value):
                safe_set_text(element, value)
            case SetTail(element=element, value=value):
                safe_set_tail(element, value)
            case ClearText(element=element):
                if not (element.text or "").strip():
                    element.text = None
