"""Tests for the ``CANONICAL_CODEMODS`` and ``AUTO_UPGRADE_CODEMODS`` contracts."""

from __future__ import annotations

from galaxy_tool_xml_codemod.canonical import (
    AUTO_UPGRADE_CODEMODS,
    CANONICAL_CODEMODS,
)
from galaxy_tool_xml_codemod.codemod import CodemodCommand
from galaxy_tool_xml_codemod.codemods.fix_typos import FixTypos
from galaxy_tool_xml_codemod.codemods.reorder_param_attributes import (
    ReorderParamAttributes,
)
from galaxy_tool_xml_codemod.codemods.reorder_tool_attributes import (
    ReorderToolAttributes,
)
from galaxy_tool_xml_codemod.codemods.reorder_tool_children import (
    ReorderToolChildren,
)
from galaxy_tool_xml_codemod.upgrades import UpgradeToLatest


def test_canonical_set_includes_both_attribute_reorder_codemods() -> None:
    """Both structural attribute-reorder codemods are in the canonical set."""
    assert ReorderParamAttributes in CANONICAL_CODEMODS
    assert ReorderToolAttributes in CANONICAL_CODEMODS


def test_canonical_set_includes_element_reorder_codemod() -> None:
    """The element-order codemod (GTX013) is in the canonical set."""
    assert ReorderToolChildren in CANONICAL_CODEMODS


def test_canonical_reorders_attributes_before_elements() -> None:
    """Attribute-level reorders run before the element-level reorder.

    Order is a convention, not load-bearing (the reorders are independent), but
    the pipeline keeps attribute tidying ahead of element tidying.
    """
    order = {cls: i for i, cls in enumerate(CANONICAL_CODEMODS)}
    assert order[ReorderToolAttributes] < order[ReorderToolChildren]
    assert order[ReorderParamAttributes] < order[ReorderToolChildren]


def test_canonical_set_repairs_but_does_not_upgrade() -> None:
    """``FixTypos`` runs in the canonical pipeline; profile upgrade does not.

    Profile upgrade is semantic and opt-in — it lives in
    ``AUTO_UPGRADE_CODEMODS``, not the default canonical (format) pipeline.
    """
    assert FixTypos in CANONICAL_CODEMODS
    assert UpgradeToLatest not in CANONICAL_CODEMODS


def test_canonical_order_repairs_then_reorders() -> None:
    """FixTypos precedes the attribute reorderers.

    Order is load-bearing: typo repair must run before attribute order is
    tidied so the reorderers see a validatable, settled tree.
    """
    order = {cls: i for i, cls in enumerate(CANONICAL_CODEMODS)}
    assert order[FixTypos] < order[ReorderParamAttributes]
    assert order[FixTypos] < order[ReorderToolAttributes]


def test_auto_upgrade_pipeline_repairs_then_upgrades() -> None:
    """``AUTO_UPGRADE_CODEMODS`` runs ``FixTypos`` before ``UpgradeToLatest``.

    Order is load-bearing: ``UpgradeToLatest`` no-ops on a tool that validates
    nowhere, so repair must run first for a broken-and-outdated tool to upgrade
    in one pass.
    """
    assert FixTypos in AUTO_UPGRADE_CODEMODS
    assert UpgradeToLatest in AUTO_UPGRADE_CODEMODS
    order = {cls: i for i, cls in enumerate(AUTO_UPGRADE_CODEMODS)}
    assert order[FixTypos] < order[UpgradeToLatest]


def test_auto_upgrade_pipeline_does_not_reorder_attributes() -> None:
    """The upgrade pipeline is repair + version migration only, not formatting."""
    assert ReorderParamAttributes not in AUTO_UPGRADE_CODEMODS
    assert ReorderToolAttributes not in AUTO_UPGRADE_CODEMODS


def test_pipelines_are_all_codemod_commands() -> None:
    """Every member of both pipelines is a ``CodemodCommand`` subclass."""
    for codemod_cls in (*CANONICAL_CODEMODS, *AUTO_UPGRADE_CODEMODS):
        assert issubclass(codemod_cls, CodemodCommand)


def test_pipelines_are_tuples() -> None:
    """Both contracts are tuples — the contract surface is immutable."""
    assert isinstance(CANONICAL_CODEMODS, tuple)
    assert isinstance(AUTO_UPGRADE_CODEMODS, tuple)
