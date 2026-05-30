"""Tests for the imported-profile-token consensus analysis (Phase 3b-1).

``plan_from_sites`` is the pure decision core: group each tool's imported
``@PROFILE@`` *site* by the macro file that defines the token, then decide per
file whether the profile-using importers **agree** on a single target profile
(the precondition for an in-place token bump; otherwise report-and-skip).
``profile_token_site`` extracts one tool's site from its ``ToolDocument``.
"""

from __future__ import annotations

from pathlib import Path

from galaxy_tool_xml.binding import load_tool
from galaxy_tool_xml.profiles import latest_profile

from galaxy_tool_refactor_registry.macro_profile import (
    ProfileTokenSite,
    plan_from_sites,
    profile_token_site,
)


def _site(tool: str, macro_file: str, target: str | None) -> ProfileTokenSite:
    return ProfileTokenSite(
        tool=Path(tool),
        macro_file=Path(macro_file),
        token_name="@PROFILE@",
        target=target,
    )


def test_plan_agrees_when_importers_share_one_target() -> None:
    sites = [_site("a.xml", "m.xml", "26.1"), _site("b.xml", "m.xml", "26.1")]
    [plan] = plan_from_sites(sites)
    assert plan.macro_file == Path("m.xml")
    assert plan.token_name == "@PROFILE@"
    assert plan.agree is True
    assert plan.target == "26.1"
    assert plan.importers == (Path("a.xml"), Path("b.xml"))


def test_plan_diverges_when_importers_disagree() -> None:
    sites = [_site("a.xml", "m.xml", "24.2"), _site("b.xml", "m.xml", "26.1")]
    [plan] = plan_from_sites(sites)
    assert plan.agree is False
    assert plan.target is None  # no safe single bump


def test_plan_does_not_agree_when_an_importer_validates_nowhere() -> None:
    sites = [_site("a.xml", "m.xml", "26.1"), _site("b.xml", "m.xml", None)]
    [plan] = plan_from_sites(sites)
    assert plan.agree is False
    assert plan.target is None


def test_plan_single_importer_agrees_trivially() -> None:
    [plan] = plan_from_sites([_site("a.xml", "m.xml", "26.1")])
    assert plan.agree is True
    assert plan.target == "26.1"
    assert plan.importers == (Path("a.xml"),)


def test_plan_groups_distinct_macro_files_separately() -> None:
    sites = [_site("a.xml", "m.xml", "26.1"), _site("c.xml", "n.xml", "24.2")]
    plans = plan_from_sites(sites)
    assert [p.macro_file for p in plans] == [Path("m.xml"), Path("n.xml")]


def _write_tool(directory: Path, name: str, body: str) -> Path:
    path = directory / name
    path.write_text(body, encoding="utf-8")
    return path


def test_profile_token_site_for_imported_token(tmp_path: Path) -> None:
    (tmp_path / "macros.xml").write_text(
        '<macros><token name="@PROFILE@">19.01</token></macros>', encoding="utf-8"
    )
    tool = _write_tool(
        tmp_path,
        "tool.xml",
        '<tool id="m" name="M" version="1.0.0" profile="@PROFILE@">'
        "<macros><import>macros.xml</import></macros>"
        "<command><![CDATA[echo x]]></command>"
        '<inputs/><outputs><data name="o"/></outputs></tool>',
    )
    site = profile_token_site(load_tool(tool))
    assert site is not None
    assert site.tool == tool
    assert site.macro_file == (tmp_path / "macros.xml")
    assert site.token_name == "@PROFILE@"
    assert site.target == latest_profile()  # validates at latest despite 19.01 token


def test_profile_token_site_none_for_inline_token(tmp_path: Path) -> None:
    tool = _write_tool(
        tmp_path,
        "inline.xml",
        '<tool id="m" name="M" version="1.0.0" profile="@PROFILE@">'
        '<macros><token name="@PROFILE@">19.01</token></macros>'
        "<command><![CDATA[echo x]]></command>"
        '<inputs/><outputs><data name="o"/></outputs></tool>',
    )
    assert profile_token_site(load_tool(tool)) is None  # inline is GTX007 3a's job


def test_profile_token_site_none_for_literal_profile(tmp_path: Path) -> None:
    tool = _write_tool(
        tmp_path,
        "literal.xml",
        '<tool id="m" name="M" version="1.0.0" profile="24.1">'
        "<command><![CDATA[echo x]]></command>"
        '<inputs/><outputs><data name="o"/></outputs></tool>',
    )
    assert profile_token_site(load_tool(tool)) is None
