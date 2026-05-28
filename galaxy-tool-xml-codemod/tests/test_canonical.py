"""Tests for the ``CANONICAL_CODEMODS`` public contract."""

from __future__ import annotations

from galaxy_tool_xml_codemod.canonical import CANONICAL_CODEMODS
from galaxy_tool_xml_codemod.codemod import CodemodCommand
from galaxy_tool_xml_codemod.codemods.reorder_param_attributes import (
    ReorderParamAttributes,
)
from galaxy_tool_xml_codemod.codemods.reorder_tool_attributes import (
    ReorderToolAttributes,
)


def test_canonical_set_includes_both_attribute_reorder_codemods() -> None:
    """Both structural attribute-reorder codemods are in the canonical set."""
    assert ReorderParamAttributes in CANONICAL_CODEMODS
    assert ReorderToolAttributes in CANONICAL_CODEMODS


def test_canonical_codemods_are_all_codemod_commands() -> None:
    """Every member of the canonical set is a ``CodemodCommand`` subclass."""
    for codemod_cls in CANONICAL_CODEMODS:
        assert issubclass(codemod_cls, CodemodCommand)


def test_canonical_set_is_a_tuple() -> None:
    """``CANONICAL_CODEMODS`` is a tuple — the contract surface is immutable."""
    assert isinstance(CANONICAL_CODEMODS, tuple)
