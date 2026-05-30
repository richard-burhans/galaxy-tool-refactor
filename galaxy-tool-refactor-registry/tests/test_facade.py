"""Tests for the facade entry points: run / upgrade / detect + I/O + ordering."""

from __future__ import annotations

from pathlib import Path

from galaxy_tool_xml.binding import load_tool
from galaxy_tool_xml_codemod.canonical import CANONICAL_CODEMODS
from galaxy_tool_xml_codemod.module import Module
from galaxy_tool_xml_fmt.format import format_tool_document
from galaxy_tool_xml_fmt.serializer import to_bytes

from galaxy_tool_refactor_registry import facade
from galaxy_tool_refactor_registry.registry import advisory_codes
from galaxy_tool_refactor_registry.resolve import resolve_codes


def _today_format(source: bytes) -> bytes:
    """Reproduce the app's pre-registry ``format`` pipeline for comparison."""
    document = load_tool(source)
    module = Module(document)
    for codemod_cls in CANONICAL_CODEMODS:
        codemod_cls().apply(module)
    return format_tool_document(document)


def test_iuc_preset_is_byte_identical_to_today_format(sample_bytes: bytes) -> None:
    """The regression guard: default (iuc) run == the old format pipeline."""
    out = facade.run(sample_bytes, codes=resolve_codes()).formatted
    assert out == _today_format(sample_bytes)


def test_cosmetic_preset_skips_structural_reorder(sample_bytes: bytes) -> None:
    """cosmetic does not reorder <param> attributes; iuc does."""
    cosmetic_codes = resolve_codes(preset="cosmetic")
    cosmetic = facade.run(sample_bytes, codes=cosmetic_codes).formatted
    iuc = facade.run(sample_bytes, codes=resolve_codes()).formatted
    assert cosmetic != iuc
    # The param keeps its source attribute order under cosmetic-only.
    param = cosmetic.partition(b"<param")[2]
    assert param.index(b"value=") < param.index(b"type=") < param.index(b"name=")


def test_strict_reports_advisory_but_same_bytes_as_iuc(sample_bytes: bytes) -> None:
    """Advisory rules report (notes) but never change the formatted bytes."""
    iuc = facade.run(sample_bytes, codes=resolve_codes()).formatted
    strict = facade.run(sample_bytes, codes=resolve_codes(preset="strict"))
    assert strict.formatted == iuc
    assert strict.advisory  # several IUC checks fire on this skeletal tool
    assert all(v.code in advisory_codes() for v in strict.advisory)
    assert all(note.endswith("(advisory)") for note in strict.notes)


def test_run_accepts_bytes_str_and_tooldocument(
    sample_bytes: bytes, tmp_path: Path
) -> None:
    """Path, bytes, and ToolDocument inputs all produce the same bytes."""
    from_bytes = facade.run(sample_bytes, codes=resolve_codes()).formatted
    path = tmp_path / "tool.xml"
    path.write_bytes(sample_bytes)
    from_path = facade.run(path, codes=resolve_codes()).formatted
    from_doc = facade.run(load_tool(sample_bytes), codes=resolve_codes()).formatted
    assert from_bytes == from_path == from_doc


def test_run_does_not_write_unless_asked(
    sample_bytes: bytes, tmp_path: Path
) -> None:
    path = tmp_path / "tool.xml"
    path.write_bytes(sample_bytes)
    facade.run(path, codes=resolve_codes())  # no write_path
    assert path.read_bytes() == sample_bytes  # untouched on disk


def test_run_writes_when_write_path_given(
    sample_bytes: bytes, tmp_path: Path
) -> None:
    out_path = tmp_path / "out.xml"
    result = facade.run(sample_bytes, codes=resolve_codes(), write_path=out_path)
    assert out_path.read_bytes() == result.formatted


def test_run_mutates_passed_document_in_place(sample_bytes: bytes) -> None:
    document = load_tool(sample_bytes)
    result = facade.run(document, codes=resolve_codes())
    # The same ToolDocument's tree was formatted in place.
    assert to_bytes(document.tree) == result.formatted


def test_detect_splits_fixable_and_advisory(sample_bytes: bytes) -> None:
    result = facade.detect(sample_bytes, codes=resolve_codes(preset="strict"))
    assert result.violations
    fixable = [v for v in result.violations if not result.is_advisory(v)]
    advisory = [v for v in result.violations if result.is_advisory(v)]
    assert fixable and advisory
    # Sorted by (sourceline, code).
    keys = [(v.sourceline, v.code) for v in result.violations]
    assert keys == sorted(keys)


def test_detect_does_not_mutate(sample_bytes: bytes) -> None:
    document = load_tool(sample_bytes)
    before = to_bytes(document.tree)
    facade.detect(document, codes=resolve_codes(preset="strict"))
    assert to_bytes(document.tree) == before


def test_empty_selection_serialises_unchanged(sample_bytes: bytes) -> None:
    """No codes selected → fmt serialises the (unmutated) tree, no fixes."""
    out = facade.run(sample_bytes, codes=frozenset()).formatted
    assert out == to_bytes(load_tool(sample_bytes).tree)


_UPGRADABLE = (
    b'<tool id="m" name="M" version="1.0.0" profile="24.1">'
    b"<command><![CDATA[echo x]]></command>"
    b'<inputs><param name="i" type="data" format="BAM"/></inputs>'
    b'<outputs><data name="o"/></outputs></tool>'
)


def test_upgrade_bumps_profile_and_runs_migration() -> None:
    from galaxy_tool_xml.profiles import latest_profile

    from galaxy_tool_refactor_registry.resolve import resolve_upgrade_codes

    result = facade.upgrade(_UPGRADABLE, codes=resolve_upgrade_codes())
    assert f'profile="{latest_profile()}"'.encode() in result.formatted
    assert b'format="bam"' in result.formatted  # the 24.1 -> 24.2 migration ran
    assert "24.1" in result.steps_applied
    assert any("upgraded past 24.1" in note for note in result.notes)


def test_upgrade_ignore_fixtypos_still_upgrades() -> None:
    from galaxy_tool_xml.profiles import latest_profile

    from galaxy_tool_refactor_registry.resolve import resolve_upgrade_codes

    codes = resolve_upgrade_codes(ignore=["GTX006"])
    result = facade.upgrade(_UPGRADABLE, codes=codes)
    # The profile upgrade is intrinsic; dropping FixTypos does not disable it.
    assert f'profile="{latest_profile()}"'.encode() in result.formatted


def test_introspection_lists_presets_and_rules() -> None:
    presets_info = facade.list_presets()
    names = {p.name for p in presets_info}
    assert names == {"cosmetic", "iuc", "strict"}
    assert any(p.is_default and p.name == "iuc" for p in presets_info)

    rules = facade.list_rules()
    codes = {r.code for r in rules}
    assert "GTX012" not in codes  # upgrade-only excluded by default
    with_upgrade = {r.code for r in facade.list_rules(include_upgrade=True)}
    assert "GTX012" in with_upgrade
    # Each fixable rule is in at least one preset; advisory rules in strict.
    iuc_rule = next(r for r in rules if r.code == "GTX002")
    assert "iuc" in iuc_rule.presets and iuc_rule.fixable
    adv_rule = next(r for r in rules if r.code == "IUC001")
    assert adv_rule.presets == ("strict",) and not adv_rule.fixable
