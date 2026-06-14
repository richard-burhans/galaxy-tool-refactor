"""Tests for GTR098 ValidDatatypes and GTR099 DatatypesCustomConf."""

from __future__ import annotations

from pathlib import Path

from galaxy_tool_source.binding import load_tool

from galaxy_tool_lint.checks.datatypes import DatatypesCustomConf, ValidDatatypes


def _codes(violations: object) -> list[str]:
    return [v.code for v in violations]


# --------------------------------------------------------------------------- #
# GTR099 DatatypesCustomConf
# --------------------------------------------------------------------------- #


def test_custom_conf_flagged_when_sibling_file_present(tmp_path: Path) -> None:
    (tmp_path / "datatypes_conf.xml").write_text(
        "<datatypes><registration/></datatypes>", encoding="utf-8"
    )
    (tmp_path / "tool.xml").write_text(
        '<tool id="t"><command>run</command></tool>', encoding="utf-8"
    )
    document = load_tool(tmp_path / "tool.xml")
    violations = list(DatatypesCustomConf().detect(document))
    assert _codes(violations) == ["GTR099"]


def test_custom_conf_silent_when_absent(tmp_path: Path) -> None:
    (tmp_path / "tool.xml").write_text(
        '<tool id="t"><command>run</command></tool>', encoding="utf-8"
    )
    document = load_tool(tmp_path / "tool.xml")
    assert list(DatatypesCustomConf().detect(document)) == []


def test_custom_conf_silent_without_source_path() -> None:
    # Parsed from bytes -> no source dir to look beside.
    document = load_tool(b'<tool id="t"><command>run</command></tool>')
    assert list(DatatypesCustomConf().detect(document)) == []


# --------------------------------------------------------------------------- #
# GTR098 ValidDatatypes
# --------------------------------------------------------------------------- #


def test_unknown_datatype_flagged() -> None:
    document = load_tool(
        b'<tool id="t"><inputs>'
        b'<param name="i" type="data" format="notarealdatatype"/>'
        b"</inputs></tool>"
    )
    violations = list(ValidDatatypes().detect(document))
    assert _codes(violations) == ["GTR098"]


def test_known_datatype_clean() -> None:
    document = load_tool(
        b'<tool id="t"><inputs>'
        b'<param name="i" type="data" format="fasta"/>'
        b"</inputs></tool>"
    )
    assert list(ValidDatatypes().detect(document)) == []


def test_case_mismatch_flagged() -> None:
    # The registry is lowercase; "FASTA" is therefore unknown (matches Galaxy).
    document = load_tool(
        b'<tool id="t"><inputs>'
        b'<param name="i" type="data" format="FASTA"/>'
        b"</inputs></tool>"
    )
    assert _codes(list(ValidDatatypes().detect(document))) == ["GTR098"]


def test_comma_separated_formats_flag_only_the_unknown() -> None:
    document = load_tool(
        b'<tool id="t"><inputs>'
        b'<param name="i" type="data" format="fasta,bogus,bam"/>'
        b"</inputs></tool>"
    )
    violations = list(ValidDatatypes().detect(document))
    assert len(violations) == 1
    assert "bogus" in violations[0].message


def test_param_auto_or_input_format_flagged() -> None:
    for value in ("auto", "input"):
        document = load_tool(
            f'<tool id="t"><inputs>'
            f'<param name="i" type="data" format="{value}"/>'
            f"</inputs></tool>".encode()
        )
        violations = list(ValidDatatypes().detect(document))
        assert _codes(violations) == ["GTR098"], value


def test_output_auto_format_skipped() -> None:
    document = load_tool(
        b'<tool id="t"><outputs>'
        b'<data name="o" format="auto"/>'
        b"</outputs></tool>"
    )
    assert list(ValidDatatypes().detect(document)) == []


def test_output_format_input_gated_by_profile() -> None:
    # No profile -> Galaxy default 16.01 (<=16.04): "input" skipped, clean.
    legacy = load_tool(
        b'<tool id="t"><outputs><data name="o" format="input"/></outputs></tool>'
    )
    assert list(ValidDatatypes().detect(legacy)) == []
    # profile > 16.04: "input" is no longer a free pass -> flagged as unknown.
    modern = load_tool(
        b'<tool id="t" profile="21.05"><outputs>'
        b'<data name="o" format="input"/></outputs></tool>'
    )
    assert _codes(list(ValidDatatypes().detect(modern))) == ["GTR098"]


def test_macro_token_format_skipped() -> None:
    # A @…@ token is resolved by macro expansion; planemo lints the expanded tree.
    document = load_tool(
        b'<tool id="t"><inputs>'
        b'<param name="i" type="data" format="@FMT@"/>'
        b"</inputs></tool>"
    )
    assert list(ValidDatatypes().detect(document)) == []


def test_help_format_attribute_ignored() -> None:
    # "format" in <help> means markup, not a datatype.
    document = load_tool(
        b'<tool id="t"><help format="markdown">text</help></tool>'
    )
    assert list(ValidDatatypes().detect(document)) == []


def test_ftype_and_ext_attributes_checked() -> None:
    document = load_tool(
        b'<tool id="t"><tests><test>'
        b'<param name="i" ftype="bogusftype"/>'
        b'<output name="o" ext="bogusext"/>'
        b"</test></tests></tool>"
    )
    assert _codes(list(ValidDatatypes().detect(document))) == ["GTR098", "GTR098"]


def test_tool_local_custom_conf_silences_its_own_types(tmp_path: Path) -> None:
    (tmp_path / "datatypes_conf.xml").write_text(
        '<datatypes><registration>'
        '<datatype extension="customtype"/></registration></datatypes>',
        encoding="utf-8",
    )
    (tmp_path / "tool.xml").write_text(
        '<tool id="t"><inputs>'
        '<param name="i" type="data" format="customtype"/>'
        "</inputs></tool>",
        encoding="utf-8",
    )
    document = load_tool(tmp_path / "tool.xml")
    assert list(ValidDatatypes().detect(document)) == []
