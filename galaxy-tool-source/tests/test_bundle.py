"""Tests for the tier-1 tool bundle and its atomic cross-file parameter rename.

A ``ToolBundle`` is a tool plus its transitively-imported macro files. Its rename
fixes the silent bug in the single-file rename: a param defined in the tool but
referenced only inside an imported macro is now rewritten in **both** files, or the
whole rename bails. Skipped when CT3 is absent (the macro ``<command>`` rewrite needs
the faithful lexer).
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("Cheetah")

from galaxy_tool_source.bundle import (  # noqa: E402
    BundleRenameOutcome,
    load_bundle,
    rename_param_in_bundle,
)


def _write(directory: Path, name: str, body: str) -> Path:
    path = directory / name
    path.write_text(body, encoding="utf-8")
    return path


# The pal2nal shape: the tool defines the param + <expand>s the command; the macro
# file carries the <command> fragment that references the param.
def _pal2nal(directory: Path) -> Path:
    _write(
        directory,
        "macros.xml",
        "<macros><xml name='command'>"
        "<command detect_errors='exit_code'><![CDATA[pal2nal '$protein_alignment']]>"
        "</command></xml></macros>",
    )
    return _write(
        directory,
        "pal2nal.xml",
        "<tool id='pal2nal'><macros><import>macros.xml</import></macros>"
        "<inputs><param name='protein_alignment' type='data'/></inputs>"
        "<expand macro='command'/></tool>",
    )


# --- load_bundle ----------------------------------------------------------------


def test_load_bundle_resolves_imports(tmp_path: Path) -> None:
    tool = _pal2nal(tmp_path)
    bundle = load_bundle(tool)
    assert bundle.tool.root.tag == "tool"
    assert [macro.source_path.name for macro in bundle.macros] == ["macros.xml"]
    assert bundle.unparseable == ()


def test_load_bundle_records_unparseable_macro(tmp_path: Path) -> None:
    _write(tmp_path, "macros.xml", "<macros><xml name='c'><command>$x</command")
    tool = _write(
        tmp_path,
        "tool.xml",
        "<tool id='t'><macros><import>macros.xml</import></macros>"
        "<command>run</command></tool>",
    )
    bundle = load_bundle(tool)
    assert bundle.macros == ()
    assert [path.name for path in bundle.unparseable] == ["macros.xml"]


# --- the cross-file rename (the silent-bug fix) ---------------------------------


def test_rename_spills_into_sole_macro(tmp_path: Path) -> None:
    bundle = load_bundle(_pal2nal(tmp_path))
    outcome = rename_param_in_bundle(
        bundle, old="protein_alignment", new="aln"
    )
    assert not outcome.bailed
    # The definition in the tool AND the reference in the macro are both rewritten.
    assert bundle.tool.root.find("inputs/param").get("name") == "aln"
    assert "$aln" in bundle.macros[0].root.find(".//command").text
    assert "$protein_alignment" not in bundle.macros[0].root.find(".//command").text
    assert outcome.renamed == 2
    assert [path.name for path in outcome.edited_macros] == ["macros.xml"]


def test_unrelated_macro_member_is_not_a_bail(tmp_path: Path) -> None:
    # The tool defines + references the param itself; an imported macro that never
    # mentions it reports not-found and must NOT abort the rename.
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
    bundle = load_bundle(tool)
    outcome = rename_param_in_bundle(bundle, old="old", new="new")
    assert not outcome.bailed
    assert outcome.edited_macros == ()  # the macro was untouched
    assert bundle.tool.root.find("command").text == "run $new"


def test_shadowed_macro_reference_bails_whole_bundle(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "macros.xml",
        "<macros><xml name='command'>"
        "<command>#set $old = 1\nrun $old</command></xml></macros>",
    )
    tool = _write(
        tmp_path,
        "tool.xml",
        "<tool id='t'><macros><import>macros.xml</import></macros>"
        "<inputs><param name='old'/></inputs><expand macro='command'/></tool>",
    )
    bundle = load_bundle(tool)
    outcome = rename_param_in_bundle(bundle, old="old", new="new")
    assert outcome.bailed
    assert outcome.reason == "shadowed"
    assert outcome.bail_member.name == "macros.xml"


def test_macro_defining_param_is_renamed_across_bundle(tmp_path: Path) -> None:
    # The param is defined inside a "common inputs" macro (not the tool). The bare
    # <param name=> and the command ref are both rewritten in the macro file.
    _write(
        tmp_path,
        "macros.xml",
        "<macros><xml name='inputs'><param name='old' type='data'/></xml>"
        "<xml name='command'><command>run '$old'</command></xml></macros>",
    )
    tool = _write(
        tmp_path,
        "tool.xml",
        "<tool id='t'><macros><import>macros.xml</import></macros>"
        "<expand macro='inputs'/><expand macro='command'/></tool>",
    )
    bundle = load_bundle(tool)
    outcome = rename_param_in_bundle(bundle, old="old", new="new")
    assert not outcome.bailed
    assert bundle.macros[0].root.find(".//param").get("name") == "new"
    assert "$new" in bundle.macros[0].root.find(".//command").text


def test_absent_param_is_not_found(tmp_path: Path) -> None:
    bundle = load_bundle(_pal2nal(tmp_path))
    outcome = rename_param_in_bundle(bundle, old="absent", new="new")
    assert outcome.bailed
    assert outcome.reason == "not-found"


def test_invalid_and_noop_names_bail(tmp_path: Path) -> None:
    bundle = load_bundle(_pal2nal(tmp_path))
    assert rename_param_in_bundle(
        bundle, old="protein_alignment", new="not valid"
    ).reason == "invalid-name"
    assert rename_param_in_bundle(
        bundle, old="protein_alignment", new="protein_alignment"
    ).reason == "no-op"


def test_outcome_is_dataclass() -> None:
    outcome = BundleRenameOutcome(
        members=(), renamed=0, bailed=True, reason="x", bail_member=None
    )
    assert outcome.reason == "x"
    assert outcome.edited_macros == ()
