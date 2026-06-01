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


def test_upgrade_warns_on_semantic_boundaries() -> None:
    """A 24.1 tool bumped to latest crosses Galaxy's 24.2 upgrade code (must-fix)."""
    from galaxy_tool_refactor_registry.resolve import resolve_upgrade_codes

    result = facade.upgrade(_UPGRADABLE, codes=resolve_upgrade_codes())
    semantic = [n for n in result.notes if "profile-behaviour" in n]
    assert len(semantic) == 1
    note = semantic[0]
    assert "24.1→" in note
    assert "24.2" in note  # the crossed release
    assert "must-fix" in note  # 24_2_fix_test_case_validation is must_fix
    assert "docs/profile_upgrades.md" in note


def test_upgrade_no_profile_warns_from_1601_baseline() -> None:
    """A tool with no profile= runs as 16.01, so the bump to latest crosses many."""
    from galaxy_tool_refactor_registry.resolve import resolve_upgrade_codes

    no_profile = (
        b'<tool id="m" name="M" version="1.0.0">'
        b"<command><![CDATA[echo x]]></command><inputs/>"
        b'<outputs><data name="o"/></outputs></tool>'
    )
    result = facade.upgrade(no_profile, codes=resolve_upgrade_codes())
    semantic = [n for n in result.notes if "profile-behaviour" in n]
    assert len(semantic) == 1
    # baseline is Galaxy's 16.01 default; crossed releases span 16.04..24.2.
    assert "16.01→" in semantic[0]
    assert "16.04" in semantic[0] and "20.09" in semantic[0]


def test_upgrade_applies_runtime_gated_from_work_dir_fix() -> None:
    """Reaching >=21.09 strips a whitespace from_work_dir (a runtime-gated fix)."""
    from galaxy_tool_refactor_registry.resolve import resolve_upgrade_codes

    tool = (
        b'<tool id="m" name="M" version="1.0.0" profile="24.0">'
        b"<command><![CDATA[echo x]]></command><inputs/>"
        b'<outputs><data name="o" from_work_dir=" out.txt "/></outputs></tool>'
    )
    result = facade.upgrade(tool, codes=resolve_upgrade_codes())
    assert b'from_work_dir="out.txt"' in result.formatted
    assert b'from_work_dir=" out.txt "' not in result.formatted


def test_upgrade_already_latest_has_no_semantic_warning() -> None:
    """A tool already declaring the latest profile isn't bumped, so no warning."""
    from galaxy_tool_xml.profiles import latest_profile

    from galaxy_tool_refactor_registry.resolve import resolve_upgrade_codes

    at_latest = (
        f'<tool id="m" name="M" version="1.0.0" profile="{latest_profile()}">'
        "<command><![CDATA[echo x]]></command><inputs/>"
        '<outputs><data name="o"/></outputs></tool>'
    ).encode()
    result = facade.upgrade(at_latest, codes=resolve_upgrade_codes())
    assert not [n for n in result.notes if "runtime-behaviour" in n]


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
