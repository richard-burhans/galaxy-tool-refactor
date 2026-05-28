"""Tests for the ``CANONICAL_CODEMODS`` public contract."""

from __future__ import annotations

from galaxy_tool_xml_codemod.canonical import CANONICAL_CODEMODS
from galaxy_tool_xml_codemod.codemod import CodemodCommand
from galaxy_tool_xml_codemod.codemods.fix_typos import FixTypos
from galaxy_tool_xml_codemod.codemods.reorder_param_attributes import (
    ReorderParamAttributes,
)
from galaxy_tool_xml_codemod.codemods.reorder_tool_attributes import (
    ReorderToolAttributes,
)
from galaxy_tool_xml_codemod.codemods.update_profile import UpdateProfile


def test_canonical_set_includes_both_attribute_reorder_codemods() -> None:
    """Both structural attribute-reorder codemods are in the canonical set."""
    assert ReorderParamAttributes in CANONICAL_CODEMODS
    assert ReorderToolAttributes in CANONICAL_CODEMODS


def test_canonical_set_includes_repair_and_profile_codemods() -> None:
    """``FixTypos`` and ``UpdateProfile`` run as part of the canonical pipeline."""
    assert FixTypos in CANONICAL_CODEMODS
    assert UpdateProfile in CANONICAL_CODEMODS


def test_canonical_order_repairs_then_profiles_then_reorders() -> None:
    """FixTypos precedes UpdateProfile, and both precede the attribute reorderers.

    Order is load-bearing: typo repair must run before the profile is read off a
    now-validatable tree, and the profile must be set before ``ReorderToolAttributes``
    positions an added ``profile=`` attribute.
    """
    order = {cls: i for i, cls in enumerate(CANONICAL_CODEMODS)}
    assert order[FixTypos] < order[UpdateProfile]
    assert order[UpdateProfile] < order[ReorderToolAttributes]
    assert order[UpdateProfile] < order[ReorderParamAttributes]


def test_canonical_codemods_are_all_codemod_commands() -> None:
    """Every member of the canonical set is a ``CodemodCommand`` subclass."""
    for codemod_cls in CANONICAL_CODEMODS:
        assert issubclass(codemod_cls, CodemodCommand)


def test_canonical_set_is_a_tuple() -> None:
    """``CANONICAL_CODEMODS`` is a tuple — the contract surface is immutable."""
    assert isinstance(CANONICAL_CODEMODS, tuple)
