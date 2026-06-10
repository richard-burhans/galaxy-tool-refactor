"""Tests for the imported-macro-file ``format`` / ``ftype`` normalization pass.

Pins the macro-library analog of ``Upgrade24_1``: literal datatype values are
lowercased / stripped in place, ``@TOKEN@`` placeholders are left alone, the file is
reserialised through fmt, and the pass is idempotent. Shared-macro fixtures stand in
for the corpus ``gdal_macros.xml`` cluster.
"""

from __future__ import annotations

from pathlib import Path

from galaxy_tool_source.binding import load_macros

from galaxy_tool_refactor_registry.macro_datatype import normalize_macro_files

_MACROS = (
    "<macros>"
    '<xml name="outputs"><data name="o" format="GTiff"/></xml>'
    '<token name="@FORMAT@">gtiff</token>'
    '<xml name="more">'
    '<param name="i" type="data" format="FASTA, FASTQ"/>'
    '<data name="t" format="@FORMAT@"/>'  # placeholder — must be left alone
    '<data name="e" format=""/>'  # empty — dropped
    '<data name="ok" format="bam"/>'  # already canonical — untouched
    "</xml>"
    "</macros>"
)


def _write(tmp_path: Path) -> Path:
    path = tmp_path / "macros.xml"
    path.write_bytes(_MACROS.encode())
    return path


def test_normalize_rewrites_literals_and_writes(tmp_path: Path) -> None:
    path = _write(tmp_path)
    result = normalize_macro_files([path], write=True)
    assert len(result.edits) == 1
    assert result.edits[0].macro_file == path
    assert result.edits[0].elements_changed == 3

    after = load_macros(path).root
    fmts = {el.get("name"): el.get("format") for el in after.iter("data")}
    assert fmts["o"] == "gtiff"  # GTiff -> gtiff
    assert fmts["t"] == "@FORMAT@"  # placeholder untouched
    assert fmts["e"] is None  # empty value -> attribute dropped
    assert fmts["ok"] == "bam"  # already canonical
    param = after.find(".//param")
    assert param is not None
    assert param.get("format") == "fasta,fastq"  # lowercased + space stripped


def test_preview_does_not_write(tmp_path: Path) -> None:
    path = _write(tmp_path)
    original = path.read_bytes()
    result = normalize_macro_files([path], write=False)
    assert len(result.edits) == 1  # reported as a would-edit
    assert path.read_bytes() == original  # but the file is untouched


def test_idempotent_and_dedups_shared_file(tmp_path: Path) -> None:
    path = _write(tmp_path)
    normalize_macro_files([path], write=True)
    # A shared file passed twice is edited once; a second run is a no-op.
    again = normalize_macro_files([path, path], write=True)
    assert again.edits == ()


def test_unparseable_file_is_skipped_not_raised(tmp_path: Path) -> None:
    good = _write(tmp_path)
    bad = tmp_path / "bad.xml"
    bad.write_bytes(b"<macros><xml name='x'><not closed")
    result = normalize_macro_files([bad, good], write=True)
    assert result.unparseable == (bad,)  # recorded, not raised
    assert len(result.edits) == 1  # the good file still processed
    assert result.edits[0].macro_file == good


def test_clean_file_is_a_no_op(tmp_path: Path) -> None:
    path = tmp_path / "clean.xml"
    path.write_bytes(
        b'<macros><xml name="x"><data name="o" format="bam"/></xml></macros>'
    )
    assert normalize_macro_files([path], write=True).edits == ()
