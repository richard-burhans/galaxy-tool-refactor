"""Partition sub-rules: grouping, selection-tree expansion, display, and the
soundness guard (the fix ``.1`` and advisory ``.2`` halves partition cleanly)."""

from __future__ import annotations

from galaxy_tool_xml.binding import load_tool

from galaxy_tool_refactor_registry.registry import (
    all_handles,
    display_code,
    expand_codes,
    known_codes,
    parent_codes,
    partition_groups,
)
from galaxy_tool_refactor_registry.resolve import resolve_codes

_GROUPS = {
    "GTR018": ("GTR018.1", "GTR018.2"),  # <command> CDATA
    "GTR019": ("GTR019.1", "GTR019.2"),  # <help> CDATA
    "GTR020": ("GTR020.1", "GTR020.2"),  # single-quote $var
    "GTR089": ("GTR089.1", "GTR089.2"),  # <help> RST repair / residual
}


def _tool(*, command: str, inputs: str = "<inputs/>") -> bytes:
    return (
        '<tool id="t" name="T" version="1.0.0" profile="24.0">'
        f"{command}{inputs}<outputs><data name=\"o\"/></outputs></tool>"
    ).encode()


def test_partition_groups_and_parent_codes() -> None:
    assert partition_groups() == _GROUPS
    assert parent_codes() == frozenset(_GROUPS)


def test_parent_codes_are_selectable_but_not_handles() -> None:
    # A parent is selectable (in known_codes) but is not itself a rule handle.
    assert parent_codes() <= known_codes()
    handles = all_handles()
    assert all(parent not in handles for parent in parent_codes())


def test_expand_codes() -> None:
    assert expand_codes(frozenset({"GTR020"})) == {"GTR020.1", "GTR020.2"}
    assert expand_codes(frozenset({"GTR020.2"})) == {"GTR020.2"}  # child passes through
    assert expand_codes(frozenset({"GTR001"})) == {"GTR001"}  # flat passes through


def test_display_code_collapses_children_to_parent() -> None:
    assert display_code("GTR020.1") == "GTR020"
    assert display_code("GTR020.2") == "GTR020"
    assert display_code("GTR001") == "GTR001"  # flat rule keeps its own code


def test_select_parent_pulls_both_children() -> None:
    assert resolve_codes(select=["GTR020"]) == {"GTR020.1", "GTR020.2"}


def test_ignore_one_child_drops_only_it() -> None:
    strict = resolve_codes(rulesets=["strict"])
    assert {"GTR020.1", "GTR020.2"} <= strict
    assert resolve_codes(rulesets=["strict"], ignore=["GTR020.2"]) == strict - {
        "GTR020.2"
    }
    assert resolve_codes(rulesets=["strict"], ignore=["GTR020"]) == strict - {
        "GTR020.1",
        "GTR020.2",
    }


def test_default_ruleset_has_fix_child_not_advisory_child() -> None:
    default = resolve_codes(rulesets=["default"])
    for fix, advisory in _GROUPS.values():
        assert fix in default and advisory not in default


def test_single_quote_partition_is_sound() -> None:
    """The fix (GTR020.1) and advisory (GTR020.2) partition the unquoted vars: the
    provable ``$input`` is the fix's, the non-provable ``$ref`` is the advisory's —
    disjoint and together exhaustive."""
    handles = all_handles()
    document = load_tool(
        _tool(
            command="<command><![CDATA[prog $input $ref]]></command>",
            inputs='<inputs><param name="input" type="data"/></inputs>',
        )
    )
    fixed = handles["GTR020.1"].detect(document)
    flagged = handles["GTR020.2"].detect(document)
    assert len(fixed) == 1  # one change covering the provable $input
    assert [v.message for v in flagged] == [
        "unquoted Cheetah variable $ref in <command> — single-quote it as '$ref'"
    ]
    assert "$input" not in flagged[0].message  # the fix's var is never re-flagged


def test_cdata_partition_is_sound() -> None:
    """Per element, exactly one of {fix GTR018.1, advisory GTR018.2} fires: a
    wrappable body is the fix's, a mixed-content body is the advisory's."""
    handles = all_handles()
    fix, advisory = handles["GTR018.1"], handles["GTR018.2"]
    wrappable = load_tool(_tool(command="<command>echo hi</command>"))
    mixed = load_tool(_tool(command="<command>echo <a/> hi</command>"))
    assert len(fix.detect(wrappable)) == 1 and advisory.detect(wrappable) == []
    assert fix.detect(mixed) == [] and len(advisory.detect(mixed)) == 1
