"""Tests for the ``canonical_codemods()`` and ``AUTO_UPGRADE_CODEMODS`` contracts.

``canonical_codemods()`` is **derived**: the codemods declaring the ``"default"``
ruleset, ordered by ``meta.order``. These pin both the derivation and the
front-to-back order it must reproduce.
"""

from __future__ import annotations

from galaxy_tool_codemod.canonical import (
    AUTO_UPGRADE_CODEMODS,
    canonical_codemods,
)
from galaxy_tool_codemod.catalog import coded_codemods
from galaxy_tool_codemod.codemod import CodemodCommand
from galaxy_tool_codemod.codemods.fix_typos import FixTypos
from galaxy_tool_codemod.codemods.reorder_param_attributes import (
    ReorderParamAttributes,
)
from galaxy_tool_codemod.codemods.reorder_tool_attributes import (
    ReorderToolAttributes,
)
from galaxy_tool_codemod.codemods.reorder_tool_children import (
    ReorderToolChildren,
)
from galaxy_tool_codemod.upgrades import UpgradeToLatest


def test_canonical_is_the_default_ruleset_ordered_by_meta() -> None:
    """The set is exactly the ``"default"``-ruleset codemods, ``meta.order``-sorted."""
    expected = sorted(
        (cls for cls in coded_codemods() if "default" in cls.meta.rulesets),
        key=lambda cls: cls.meta.order,
    )
    assert list(canonical_codemods()) == expected


def test_canonical_front_to_back_roster_is_pinned() -> None:
    """The derived pipeline's exact roster + order, pinned literally.

    The derivation test above moves with the metadata, so it cannot catch an
    accidental retag (a codemod gaining/losing ``"default"``) or an order edit.
    This literal pin is the acknowledgement gate: growing or reordering the
    pipeline must update it deliberately (the repo's explicit-list convention).
    """
    assert [cls.meta.code for cls in canonical_codemods()] == [
        "GTR006",  # FixTypos
        "GTR017",  # NormalizeBooleanValues
        "GTR089.1",  # RepairHelpRst
        "GTR035.1",  # TrimAttributeWhitespace (requirement version; GTR035 partition)
        "GTR036",  # ReplaceOutputElement
        "GTR037",  # DropRedundantParamName
        "GTR002",  # ReorderParamAttributes
        "GTR005",  # ReorderToolAttributes
        "GTR013",  # ReorderToolChildren
        "GTR018.1",  # WrapCommandCdata
        "GTR019.1",  # WrapHelpCdata
        "GTR020.1",  # SingleQuoteCommandVars
    ]


def test_canonical_orders_are_unique() -> None:
    """No two default-ruleset codemods share a ``meta.order``.

    A duplicate order would make the derived pipeline's tie-break the implicit
    ``coded_codemods()`` listing order — deterministic but silent; fail loudly
    instead.
    """
    orders = [cls.meta.order for cls in canonical_codemods()]
    assert len(orders) == len(set(orders))


def test_canonical_set_includes_both_attribute_reorder_codemods() -> None:
    """Both structural attribute-reorder codemods are in the canonical set."""
    assert ReorderParamAttributes in canonical_codemods()
    assert ReorderToolAttributes in canonical_codemods()


def test_canonical_set_includes_element_reorder_codemod() -> None:
    """The element-order codemod (GTR013) is in the canonical set."""
    assert ReorderToolChildren in canonical_codemods()


def test_canonical_reorders_attributes_before_elements() -> None:
    """Attribute-level reorders run before the element-level reorder.

    Order is a convention, not load-bearing (the reorders are independent), but
    the pipeline keeps attribute tidying ahead of element tidying.
    """
    order = {cls: i for i, cls in enumerate(canonical_codemods())}
    assert order[ReorderToolAttributes] < order[ReorderToolChildren]
    assert order[ReorderParamAttributes] < order[ReorderToolChildren]


def test_canonical_set_repairs_but_does_not_upgrade() -> None:
    """``FixTypos`` runs in the canonical pipeline; profile upgrade does not.

    Profile upgrade is semantic and opt-in — it lives in
    ``AUTO_UPGRADE_CODEMODS``, not the default canonical (format) pipeline.
    """
    assert FixTypos in canonical_codemods()
    assert UpgradeToLatest not in canonical_codemods()


def test_canonical_order_repairs_then_reorders() -> None:
    """FixTypos precedes the attribute reorderers.

    Order is load-bearing: typo repair must run before attribute order is
    tidied so the reorderers see a validatable, settled tree.
    """
    order = {cls: i for i, cls in enumerate(canonical_codemods())}
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
    for codemod_cls in (*canonical_codemods(), *AUTO_UPGRADE_CODEMODS):
        assert issubclass(codemod_cls, CodemodCommand)


def test_pipelines_are_tuples() -> None:
    """Both contracts are tuples — the contract surface is immutable."""
    assert isinstance(canonical_codemods(), tuple)
    assert isinstance(AUTO_UPGRADE_CODEMODS, tuple)
