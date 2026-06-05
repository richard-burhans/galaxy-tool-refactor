"""Tests for the registry's gated cross-file rename and reverse-import map.

The tier-1 bundle rename is atomic across a tool and its macros; this tier adds the
sole-owned gate: a macro shared by another tool is never edited (the whole rename is
skipped and reported), and a rename that must edit a macro needs an importer map to
prove ownership. Skipped when CT3 is absent (the macro ``<command>`` rewrite needs the
faithful lexer).
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("Cheetah")

from galaxy_tool_refactor_registry.bundle_rename import (  # noqa: E402
    build_importer_map,
    find_references_in_bundle,
    rename_param_bundle,
    rename_param_consensus,
)


def _write(directory: Path, name: str, body: str) -> Path:
    path = directory / name
    path.write_text(body, encoding="utf-8")
    return path


def _sole_owned_tool(directory: Path) -> Path:
    """The pal2nal shape: one tool, one sole-owned macro carrying the command ref."""
    _write(
        directory,
        "macros.xml",
        "<macros><xml name='command'>"
        "<command><![CDATA[pal2nal '$protein_alignment']]></command></xml></macros>",
    )
    return _write(
        directory,
        "pal2nal.xml",
        "<tool id='pal2nal'><macros><import>macros.xml</import></macros>"
        "<inputs><param name='protein_alignment' type='data'/></inputs>"
        "<expand macro='command'/></tool>",
    )


def _shared_macro_tools(directory: Path) -> tuple[Path, Path]:
    """Two tools importing one shared macro that references the param by name."""
    _write(
        directory,
        "shared.xml",
        "<macros><xml name='command'>"
        "<command><![CDATA[run '$old']]></command></xml></macros>",
    )
    tool_a = _write(
        directory,
        "tool_a.xml",
        "<tool id='a'><macros><import>shared.xml</import></macros>"
        "<inputs><param name='old' type='data'/></inputs>"
        "<expand macro='command'/></tool>",
    )
    tool_b = _write(
        directory,
        "tool_b.xml",
        "<tool id='b'><macros><import>shared.xml</import></macros>"
        "<inputs><param name='old' type='data'/></inputs>"
        "<expand macro='command'/></tool>",
    )
    return tool_a, tool_b


# --- the importer map -----------------------------------------------------------


def test_importer_map_marks_shared_and_sole_owned(tmp_path: Path) -> None:
    tool_a, tool_b = _shared_macro_tools(tmp_path)
    _write(  # a sole-owned macro for tool_a only
        tmp_path,
        "a_only.xml",
        "<macros><token name='@X@'>1</token></macros>",
    )
    (tmp_path / "tool_a.xml").write_text(
        "<tool id='a'><macros><import>shared.xml</import><import>a_only.xml</import>"
        "</macros><inputs><param name='old' type='data'/></inputs>"
        "<expand macro='command'/></tool>",
        encoding="utf-8",
    )
    importers = build_importer_map(tmp_path)
    assert importers[(tmp_path / "shared.xml").resolve()] == frozenset(
        {tool_a.resolve(), tool_b.resolve()}
    )
    assert importers[(tmp_path / "a_only.xml").resolve()] == frozenset(
        {tool_a.resolve()}
    )


# --- the gated rename -----------------------------------------------------------


def test_sole_owned_rename_applies_and_writes(tmp_path: Path) -> None:
    tool = _sole_owned_tool(tmp_path)
    importers = build_importer_map(tmp_path)
    result = rename_param_bundle(
        tool, old="protein_alignment", new="aln", importers=importers, write=True
    )
    assert result.changed
    assert {edit.kind for edit in result.edits} == {"tool", "macro"}
    # Both files were rewritten on disk.
    assert "aln" in (tmp_path / "pal2nal.xml").read_text(encoding="utf-8")
    macro_text = (tmp_path / "macros.xml").read_text(encoding="utf-8")
    assert "$aln" in macro_text
    assert "$protein_alignment" not in macro_text


def test_shared_macro_rename_is_skipped_and_reported(tmp_path: Path) -> None:
    tool_a, tool_b = _shared_macro_tools(tmp_path)
    importers = build_importer_map(tmp_path)
    before = (tmp_path / "shared.xml").read_text(encoding="utf-8")
    result = rename_param_bundle(
        tool_a, old="old", new="new", importers=importers, write=True
    )
    assert not result.changed
    assert result.reason == "shared-macro"
    (skip,) = result.shared
    assert skip.macro_file == (tmp_path / "shared.xml").resolve()
    assert skip.other_importers == (tool_b.resolve(),)
    # Nothing was written — not the shared macro, not the tool.
    assert (tmp_path / "shared.xml").read_text(encoding="utf-8") == before
    assert "old" in (tmp_path / "tool_a.xml").read_text(encoding="utf-8")


def test_macro_edit_without_importer_map_bails(tmp_path: Path) -> None:
    tool = _sole_owned_tool(tmp_path)
    result = rename_param_bundle(tool, old="protein_alignment", new="aln")
    assert not result.changed
    assert result.reason == "macro-edit-needs-repo-root"


def test_macro_absent_from_importer_map_is_unprovable(tmp_path: Path) -> None:
    # A non-empty importer map that does NOT cover the edited macro (e.g. --repo-root
    # pointed away from the tool) must FAIL CLOSED — ownership can't be proven, so the
    # rename is skipped, not fail-open-applied (which could break an unseen tool).
    tool = _sole_owned_tool(tmp_path)
    result = rename_param_bundle(
        tool, old="protein_alignment", new="aln", importers={}, write=True
    )
    assert not result.changed
    assert result.reason == "macro-ownership-unprovable"
    assert result.unprovable == ((tmp_path / "macros.xml").resolve(),)
    assert b"protein_alignment" in tool.read_bytes()  # nothing written


def test_tool_internal_rename_needs_no_importer_map(tmp_path: Path) -> None:
    # All reference edits land in the tool, so no macro is touched and no map is needed.
    _write(
        tmp_path,
        "macros.xml",
        "<macros><xml name='reqs'><requirement>x</requirement></xml></macros>",
    )
    tool = _write(
        tmp_path,
        "tool.xml",
        "<tool id='t'><macros><import>macros.xml</import></macros>"
        "<inputs><param name='old'/></inputs><command>run $old</command></tool>",
    )
    result = rename_param_bundle(tool, old="old", new="new", write=True)
    assert result.changed
    assert [edit.kind for edit in result.edits] == ["tool"]
    assert "run $new" in (tmp_path / "tool.xml").read_text(encoding="utf-8")


def test_unparseable_macro_bails(tmp_path: Path) -> None:
    _write(tmp_path, "macros.xml", "<macros><xml name='c'><command>$old</command")
    tool = _write(
        tmp_path,
        "tool.xml",
        "<tool id='t'><macros><import>macros.xml</import></macros>"
        "<inputs><param name='old'/></inputs><command>run $old</command></tool>",
    )
    result = rename_param_bundle(tool, old="old", new="new", write=True)
    assert not result.changed
    assert result.reason == "unparseable-macro"


def test_planner_bail_propagates(tmp_path: Path) -> None:
    tool = _sole_owned_tool(tmp_path)
    result = rename_param_bundle(tool, old="absent", new="new")
    assert not result.changed
    assert result.reason == "not-found"


def test_write_false_returns_bytes_without_touching_disk(tmp_path: Path) -> None:
    tool = _sole_owned_tool(tmp_path)
    importers = build_importer_map(tmp_path)
    before = (tmp_path / "macros.xml").read_text(encoding="utf-8")
    result = rename_param_bundle(
        tool, old="protein_alignment", new="aln", importers=importers, write=False
    )
    assert result.changed
    macro_edits = [edit for edit in result.edits if edit.kind == "macro"]
    assert any(b"$aln" in edit.formatted for edit in macro_edits)
    assert (tmp_path / "macros.xml").read_text(encoding="utf-8") == before  # untouched


# --- bundle find-references -----------------------------------------------------


# --- consensus rename across shared-macro importers -----------------------------


def test_consensus_renames_all_importers(tmp_path: Path) -> None:
    tool_a, tool_b = _shared_macro_tools(tmp_path)
    importers = build_importer_map(tmp_path)
    result = rename_param_consensus(
        tool_a, old="old", new="new", importers=importers, write=True
    )
    assert result.changed
    # The shared macro AND both importing tools are rewritten, each once.
    assert {edit.path for edit in result.edits} == {
        tool_a.resolve(),
        tool_b.resolve(),
        (tmp_path / "shared.xml").resolve(),
    }
    assert set(result.tools) == {tool_a.resolve(), tool_b.resolve()}
    assert "$new" in (tmp_path / "shared.xml").read_text(encoding="utf-8")
    assert 'name="new"' in tool_a.read_text(encoding="utf-8")
    assert 'name="new"' in tool_b.read_text(encoding="utf-8")


def test_consensus_dissent_skips_the_whole_group(tmp_path: Path) -> None:
    # tool_b references the param in its OWN command but a #set local shadows it, so it
    # cannot rename cleanly -> the whole consensus group is refused, nothing is written.
    _write(
        tmp_path,
        "shared.xml",
        "<macros><xml name='command'>"
        "<command><![CDATA[run '$old']]></command></xml></macros>",
    )
    tool_a = _write(
        tmp_path,
        "a.xml",
        "<tool id='a'><macros><import>shared.xml</import></macros>"
        "<inputs><param name='old' type='data'/></inputs>"
        "<expand macro='command'/></tool>",
    )
    tool_b = _write(
        tmp_path,
        "b.xml",
        "<tool id='b'><macros><import>shared.xml</import></macros>"
        "<inputs><param name='old' type='data'/></inputs>"
        "<command>#set $old = 1\nrun $old</command></tool>",
    )
    importers = build_importer_map(tmp_path)
    before = tool_a.read_bytes()
    result = rename_param_consensus(
        tool_a, old="old", new="new", importers=importers, write=True
    )
    assert not result.changed
    assert result.reason == "no-consensus"
    assert (tool_b.resolve(), "shadowed") in result.dissenting
    assert tool_a.read_bytes() == before  # nothing written, not even the agreeing tool


def test_consensus_co_importer_not_using_param_is_left_alone(tmp_path: Path) -> None:
    # tool_c imports the shared macro but expands a DIFFERENT fragment and never uses
    # the param -> it is in the group but its own file is not rewritten.
    _write(
        tmp_path,
        "shared.xml",
        "<macros>"
        "<xml name='command'><command><![CDATA[run '$old']]></command></xml>"
        "<xml name='other'><command><![CDATA[noop]]></command></xml>"
        "</macros>",
    )
    tool_a = _write(
        tmp_path,
        "a.xml",
        "<tool id='a'><macros><import>shared.xml</import></macros>"
        "<inputs><param name='old' type='data'/></inputs>"
        "<expand macro='command'/></tool>",
    )
    tool_c = _write(
        tmp_path,
        "c.xml",
        "<tool id='c'><macros><import>shared.xml</import></macros>"
        "<expand macro='other'/></tool>",
    )
    importers = build_importer_map(tmp_path)
    result = rename_param_consensus(
        tool_a, old="old", new="new", importers=importers, write=True
    )
    assert result.changed
    assert tool_c.resolve() not in result.tools  # c never used the param
    assert "$new" in (tmp_path / "shared.xml").read_text(encoding="utf-8")


def test_consensus_not_found(tmp_path: Path) -> None:
    tool = _sole_owned_tool(tmp_path)
    importers = build_importer_map(tmp_path)
    result = rename_param_consensus(
        tool, old="absent", new="new", importers=importers
    )
    assert not result.changed
    assert result.reason == "not-found"


# --- bundle find-references -----------------------------------------------------


def test_find_references_spans_tool_and_macro(tmp_path: Path) -> None:
    tool = _sole_owned_tool(tmp_path)
    result = find_references_in_bundle(tool, name="protein_alignment")
    kinds = {ref.kind for ref in result.references}
    assert kinds == {"macro"}  # the reference lives only in the macro
    (ref,) = result.references
    assert ref.path == (tmp_path / "macros.xml").resolve()
    assert ref.reference == "$protein_alignment"
