"""Tests for shared-macros version tokenization (create / merge / consensus)."""

from __future__ import annotations

from pathlib import Path

from galaxy_tool_refactor_registry.version_token_share import plan_shared_tokenization


def _tool(*, version: str, req: str = "1.20", imports: str | None = None) -> bytes:
    macros = f"<macros><import>{imports}</import></macros>" if imports else ""
    return (
        f'<tool id="t" name="T" version="{version}" profile="24.0">'
        f"{macros}"
        "<command><![CDATA[echo x]]></command>"
        f'<requirements><requirement type="package" version="{req}">samtools'
        "</requirement></requirements>"
        '<inputs><param name="i" type="text"/></inputs>'
        '<outputs><data name="o"/></outputs></tool>'
    ).encode()


def test_create_new_macros_file(tmp_path: Path) -> None:
    tool = tmp_path / "tool.xml"
    tool.write_bytes(_tool(version="1.20+galaxy0"))
    plan = plan_shared_tokenization(tmp_path / "macros.xml", target_tools=[tool])
    assert plan.skip_reason is None
    assert plan.macros_created is True
    assert plan.base == "1.20" and plan.suffix == "0"
    assert plan.macros_content is not None
    assert b'<token name="@TOOL_VERSION@">1.20</token>' in plan.macros_content
    assert len(plan.tool_edits) == 1
    edit = plan.tool_edits[0]
    assert b"<import>macros.xml</import>" in edit.content
    assert b'version="@TOOL_VERSION@+galaxy@VERSION_SUFFIX@"' in edit.content


def test_consensus_two_tools_same_version(tmp_path: Path) -> None:
    a = tmp_path / "a.xml"
    b = tmp_path / "b.xml"
    a.write_bytes(_tool(version="1.20+galaxy0"))
    b.write_bytes(_tool(version="1.20+galaxy0"))
    plan = plan_shared_tokenization(tmp_path / "macros.xml", target_tools=[a, b])
    assert plan.skip_reason is None
    assert {e.path.name for e in plan.tool_edits} == {"a.xml", "b.xml"}
    for edit in plan.tool_edits:
        assert b"<import>macros.xml</import>" in edit.content


def test_divergent_versions_declined(tmp_path: Path) -> None:
    a = tmp_path / "a.xml"
    b = tmp_path / "b.xml"
    a.write_bytes(_tool(version="1.20+galaxy0", req="1.20"))
    b.write_bytes(_tool(version="2.0+galaxy0", req="2.0"))
    plan = plan_shared_tokenization(tmp_path / "macros.xml", target_tools=[a, b])
    assert plan.skip_reason is not None
    assert "disagree" in plan.skip_reason
    assert not plan.tool_edits


def test_merge_into_existing_inert(tmp_path: Path) -> None:
    # An existing shared macros file with unrelated content, imported by two tools;
    # the other importer does not use the version tokens, so the merge is inert.
    (tmp_path / "macros.xml").write_bytes(
        b'<macros><token name="@CITE@">ref</token></macros>'
    )
    tool = tmp_path / "tool.xml"
    other = tmp_path / "other.xml"
    tool.write_bytes(_tool(version="1.20+galaxy0", imports="macros.xml"))
    other.write_bytes(
        b'<tool id="o" name="O" version="9.9" profile="24.0">'
        b"<macros><import>macros.xml</import></macros>"
        b"<command><![CDATA[echo x]]></command>"
        b'<inputs/><outputs><data name="o"/></outputs></tool>'
    )
    plan = plan_shared_tokenization(tmp_path / "macros.xml", target_tools=[tool])
    assert plan.skip_reason is None, plan.skip_reason
    assert plan.macros_created is False
    assert plan.macros_content is not None
    assert b'<token name="@CITE@">ref</token>' in plan.macros_content  # kept
    assert b'<token name="@TOOL_VERSION@">1.20</token>' in plan.macros_content
    # tool already imports it: retarget only, no second <import>
    assert plan.tool_edits[0].content.count(b"<import>macros.xml</import>") == 1


def test_conflicting_token_value_declined(tmp_path: Path) -> None:
    (tmp_path / "macros.xml").write_bytes(
        b'<macros><token name="@TOOL_VERSION@">9.9</token>'
        b'<token name="@VERSION_SUFFIX@">9</token></macros>'
    )
    tool = tmp_path / "tool.xml"  # does NOT import the file (so it stays eligible)
    tool.write_bytes(_tool(version="1.20+galaxy0"))
    plan = plan_shared_tokenization(tmp_path / "macros.xml", target_tools=[tool])
    assert plan.skip_reason is not None
    assert "@TOOL_VERSION@" in plan.skip_reason and "9.9" in plan.skip_reason


def test_non_eligible_target_is_skipped(tmp_path: Path) -> None:
    tool = tmp_path / "tool.xml"
    tool.write_bytes(_tool(version="1.20"))  # no +galaxy -> not tokenizable
    plan = plan_shared_tokenization(tmp_path / "macros.xml", target_tools=[tool])
    assert plan.skip_reason == "no target tool is eligible for tokenization"
    assert [p.name for p, _r in plan.skipped] == ["tool.xml"]
