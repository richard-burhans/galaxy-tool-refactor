"""Codemod: drop ``display="checkboxes"`` from a select-like ``<param>`` (GTR106).

IUC leaves the widget to Galaxy. ``display`` is **presentation only** — it changes
which control the form renders, never the parameter's value space, the submitted
value, or the rendered command — so removing it is behaviour-preserving by
construction, which is why this practice is a fixer rather than an advisory.

Scope is deliberately narrow. Only ``checkboxes`` is dropped, and only from a
``<param>`` under ``<inputs>`` whose ``display`` agrees with its ``multiple`` /
``optional`` attributes, because:

- ``display="radio"`` is **not** cosmetic in the same way for a user filling the form
  (it forces a single visible choice set) and IUC does not object to it, so it is left
  alone.
- a ``checkboxes`` select that *disagrees* with ``multiple``/``optional`` is GTR076's
  finding -- an inconsistency a human should look at, since dropping the attribute
  would silently resolve a contradiction the author may have meant the other way
  (``multiple="true"`` may be the thing that is missing). Those are skipped here and
  keep reporting through GTR076.

``optional``'s default when the attribute is absent is **per type**, not uniform: see
``_OPTIONAL_FOLLOWS_MULTIPLE``. ⚠ One consequence is worth stating plainly: for a
``data_column`` / ``drill_down`` carrying ``display="checkboxes" multiple="true"`` and
no explicit ``optional``, Galaxy sees ``optional=False``, so this codemod now correctly
declines -- but GTR076 will *not* pick it up either, because GTR076 reimplements
planemo's ``InputsSelectMandatoryCheckboxes`` and inherits planemo's own
defaults-to-``multiple`` assumption. That handoff is therefore incomplete for those two
types by inheritance, and widening it belongs in a planemo-parity change, not here.

Idempotent: after the drop there is no ``display`` to match.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from galaxy_tool_refactor_rules.meta import RuleMeta

from galaxy_tool_codemod.change import Change
from galaxy_tool_codemod.codemod import CodemodCommand

if TYPE_CHECKING:
    from collections.abc import Iterable

    from galaxy_tool_codemod.cursor import Cursor

_IUC = "https://galaxy-iuc-standards.readthedocs.io/en/latest/best_practices/tool_xml.html"

#: Param types for which Galaxy honours ``display``, mapped to what ``optional``
#: defaults to when the attribute is absent. **Only ``select`` defaults it to
#: ``multiple``** (``tools/parameters/basic.py``: ``parse_optional(self.multiple)`` for
#: ``SelectToolParameter``); ``data_column`` passes ``parse_optional(False)`` and
#: ``drill_down`` inherits ``ToolParameter``'s ``parse_optional()``, whose own default
#: is ``False``. Assuming the select rule for all three made this codemod act on a
#: ``data_column`` that Galaxy in fact sees as non-optional -- i.e. exactly the
#: ``checkboxes``/``optional`` contradiction it promises to leave alone.
_OPTIONAL_FOLLOWS_MULTIPLE = frozenset({"select"})
_DISPLAY_PARAM_TYPES = frozenset({"select", "data_column", "drill_down"})


def _string_as_bool(value: str | None, default: bool, /) -> bool:
    """Galaxy's ``string_as_bool`` with an explicit default for an absent value."""
    if value is None:
        return default
    return value.lower() in ("true", "yes", "on", "1")


def _under_inputs(cursor: Cursor, /) -> bool:
    """Whether *cursor* sits anywhere under an ``<inputs>`` (an input definition)."""
    node = cursor.parent()
    while node is not None:
        if node.tag == "inputs":
            return True
        node = node.parent()
    return False


class DropSelectCheckboxesDisplay(CodemodCommand):
    """Drop ``display="checkboxes"``; the widget is Galaxy's choice, not the tool's."""

    meta: ClassVar[RuleMeta] = RuleMeta(
        code="GTR106",
        summary=(
            "Drop display=\"checkboxes\" from a select param (IUC leaves the widget"
            " to Galaxy)."
        ),
        since="0.3.10",
        cite=_IUC,
        order=55,
        rulesets=frozenset({"default", "iuc", "strict"}),
    )

    def detect_Param(self, cursor: Cursor) -> Iterable[Change]:
        if cursor.get_attribute("display") != "checkboxes":
            return
        ptype = cursor.get_attribute("type")
        if ptype not in _DISPLAY_PARAM_TYPES:
            return
        if not _under_inputs(cursor):
            return
        multiple = _string_as_bool(cursor.get_attribute("multiple"), False)
        optional_default = multiple if ptype in _OPTIONAL_FOLLOWS_MULTIPLE else False
        optional = _string_as_bool(cursor.get_attribute("optional"), optional_default)
        if not (multiple and optional):
            return  # inconsistent with multiple/optional: GTR076's to report
        name = cursor.get_attribute("name") or cursor.get_attribute("argument") or "?"
        yield Change(
            code=self.meta.code,
            sourceline=cursor.sourceline,
            xpath=cursor.xpath,
            message=(
                f"drop display=\"checkboxes\" from '{name}' (presentation only; IUC"
                " leaves the widget to Galaxy)"
            ),
            mutate=lambda: cursor.delete_attribute("display"),
        )
