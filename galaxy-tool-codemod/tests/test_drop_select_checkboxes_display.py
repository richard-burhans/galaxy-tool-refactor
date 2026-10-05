"""Tests for ``DropSelectCheckboxesDisplay`` (GTR106).

``display`` picks a widget and nothing else -- it is absent from ``from_json``,
``to_param_dict_string``, ``get_initial_value`` and all of ``evaluation.py`` -- so
removing it cannot change the submitted value or the rendered command. That is what
makes this practice a fixer rather than an advisory.

A red-team pass confirmed the behaviour claims and broke one precondition, pinned
below: ``optional`` defaults to ``multiple`` for ``select`` **only**.
"""

from __future__ import annotations

from galaxy_tool_codemod.codemods.drop_select_checkboxes_display import (
    DropSelectCheckboxesDisplay,
)
from galaxy_tool_codemod.parse import parse_module

_HEAD = b'<tool id="m" name="M" version="1.0.0" profile="24.0">'


def _tool(inputs: bytes) -> bytes:
    return _HEAD + b"<inputs>" + inputs + b"</inputs><outputs/></tool>"


_CONSISTENT = (
    b'<param name="fmt" type="select" multiple="true" optional="true" '
    b'display="checkboxes"><option value="a">a</option></param>'
)


def test_drops_the_attribute_and_nothing_else() -> None:
    module = parse_module(_tool(_CONSISTENT))
    changes = list(DropSelectCheckboxesDisplay().detect(module))
    assert len(changes) == 1 and changes[0].code == "GTR106"
    DropSelectCheckboxesDisplay().apply(module)
    param = module.document.root.find("inputs/param")
    assert param.get("display") is None
    # everything that decides the submitted value is untouched
    assert param.get("multiple") == "true"
    assert param.get("optional") == "true"
    assert param.get("type") == "select"


def test_is_idempotent() -> None:
    module = parse_module(_tool(_CONSISTENT))
    DropSelectCheckboxesDisplay().apply(module)
    assert list(DropSelectCheckboxesDisplay().detect(module)) == []


def test_leaves_an_inconsistent_select_to_gtr076() -> None:
    """Dropping ``display`` there would settle a contradiction the author may have
    meant the other way: the missing ``multiple="true"`` may be the real omission."""
    module = parse_module(
        _tool(
            b'<param name="fmt" type="select" display="checkboxes">'
            b'<option value="a">a</option></param>'
        )
    )
    assert list(DropSelectCheckboxesDisplay().detect(module)) == []


def test_leaves_radio_alone() -> None:
    module = parse_module(
        _tool(
            b'<param name="fmt" type="select" display="radio">'
            b'<option value="a">a</option></param>'
        )
    )
    assert list(DropSelectCheckboxesDisplay().detect(module)) == []


def test_ignores_a_test_param() -> None:
    module = parse_module(
        _HEAD + b"<inputs/><outputs/><tests><test>"
        b'<param name="fmt" type="select" multiple="true" optional="true" '
        b'display="checkboxes"/></test></tests></tool>'
    )
    assert list(DropSelectCheckboxesDisplay().detect(module)) == []


def test_optional_follows_multiple_for_select_only() -> None:
    """⛔ ``data_column``/``drill_down`` do NOT default ``optional`` to ``multiple``.

    ``tools/parameters/basic.py``: ``SelectToolParameter`` passes
    ``parse_optional(self.multiple)``, but ``ColumnListParameter`` passes
    ``parse_optional(False)`` and ``DrillDownSelectToolParameter`` inherits
    ``ToolParameter``'s ``parse_optional()``, whose default is ``False``. Assuming the
    select rule for all three made this codemod act on a ``data_column`` that Galaxy
    sees as non-optional -- the very contradiction it promises to leave alone.
    """
    for ptype in (b"data_column", b"drill_down"):
        module = parse_module(
            _tool(
                b'<param name="cols" type="' + ptype + b'" data_ref="in1" '
                b'display="checkboxes" multiple="true"/>'
            )
        )
        assert list(DropSelectCheckboxesDisplay().detect(module)) == [], ptype
    # an EXPLICIT optional="true" on the same types is still acted on
    module = parse_module(
        _tool(
            b'<param name="cols" type="data_column" data_ref="in1" '
            b'display="checkboxes" multiple="true" optional="true"/>'
        )
    )
    assert len(list(DropSelectCheckboxesDisplay().detect(module))) == 1
