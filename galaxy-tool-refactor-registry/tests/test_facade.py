"""Tests for the facade entry points: run / upgrade / detect + I/O + ordering."""

from __future__ import annotations

from pathlib import Path

from galaxy_tool_codemod.canonical import canonical_codemods
from galaxy_tool_codemod.module import Module
from galaxy_tool_fmt.format import format_tool_document
from galaxy_tool_fmt.serializer import to_bytes
from galaxy_tool_source.binding import load_tool

from galaxy_tool_refactor_registry import facade
from galaxy_tool_refactor_registry.registry import advisory_codes
from galaxy_tool_refactor_registry.resolve import resolve_codes


def _today_format(source: bytes) -> bytes:
    """Reproduce the direct canonical + cosmetic pipeline for comparison.

    Re-derives from the *live* ``canonical_codemods()`` set, so this pins that the
    facade reproduces the direct pipeline — not a frozen historical byte string
    (GTR020 joining the set shifted both sides together; codemod §30).
    """
    document = load_tool(source)
    module = Module(document)
    for codemod_cls in canonical_codemods():
        codemod_cls().apply(module)
    return format_tool_document(document)


def test_default_ruleset_is_byte_identical_to_today_format(sample_bytes: bytes) -> None:
    """The regression guard: default run == the direct canonical pipeline."""
    out = facade.run(sample_bytes, codes=resolve_codes()).formatted
    assert out == _today_format(sample_bytes)


def test_cosmetic_ruleset_skips_structural_reorder(sample_bytes: bytes) -> None:
    """cosmetic does not reorder <param> attributes; default does."""
    cosmetic_codes = resolve_codes(rulesets=["cosmetic"])
    cosmetic = facade.run(sample_bytes, codes=cosmetic_codes).formatted
    default = facade.run(sample_bytes, codes=resolve_codes()).formatted
    assert cosmetic != default
    # The param keeps its source attribute order under cosmetic-only.
    param = cosmetic.partition(b"<param")[2]
    assert param.index(b"value=") < param.index(b"type=") < param.index(b"name=")


def test_strict_reports_advisory_but_same_bytes_as_default(sample_bytes: bytes) -> None:
    """Advisory rules report (notes) but never change the formatted bytes."""
    default = facade.run(sample_bytes, codes=resolve_codes()).formatted
    strict = facade.run(sample_bytes, codes=resolve_codes(rulesets=["strict"]))
    assert strict.formatted == default
    assert strict.advisory  # several checks fire on this skeletal tool
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
    result = facade.detect(sample_bytes, codes=resolve_codes(rulesets=["strict"]))
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
    facade.detect(document, codes=resolve_codes(rulesets=["strict"]))
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
    from galaxy_tool_source.profiles import latest_profile

    from galaxy_tool_refactor_registry.resolve import resolve_upgrade_codes

    result = facade.upgrade(_UPGRADABLE, codes=resolve_upgrade_codes())
    assert f'profile="{latest_profile()}"'.encode() in result.formatted
    assert b'format="bam"' in result.formatted  # the 24.1 -> 24.2 migration ran
    assert "24.1" in result.steps_applied
    assert any("upgraded past 24.1" in note for note in result.notes)


def test_upgrade_ignore_fixtypos_still_upgrades() -> None:
    from galaxy_tool_source.profiles import latest_profile

    from galaxy_tool_refactor_registry.resolve import resolve_upgrade_codes

    codes = resolve_upgrade_codes(ignore=["GTR006"])
    result = facade.upgrade(_UPGRADABLE, codes=codes)
    # The profile upgrade is intrinsic; dropping FixTypos does not disable it.
    assert f'profile="{latest_profile()}"'.encode() in result.formatted


def test_upgrade_warns_on_semantic_boundaries() -> None:
    """A 24.1 tool that ships tests trips Galaxy's 24.2 must-fix code on bump.

    The default gate stops before 24.2 now, so the crossed-boundary warning is
    exercised through the explicit opt-out, where the bump actually happens.
    """
    from galaxy_tool_refactor_registry.resolve import resolve_upgrade_codes

    with_tests = (
        b'<tool id="m" name="M" version="1.0.0" profile="24.1">'
        b"<command><![CDATA[echo x]]></command>"
        b'<inputs><param name="i" type="data" format="BAM"/></inputs>'
        b'<outputs><data name="o"/></outputs>'
        b'<tests><test><param name="i" value="x.bam"/><output name="o"/></test>'
        b"</tests></tool>"
    )
    result = facade.upgrade(
        with_tests, codes=resolve_upgrade_codes(), allow_behavior_change=True
    )
    semantic = [n for n in result.notes if "profile-behaviour" in n]
    assert len(semantic) == 1
    note = semantic[0]
    assert "24.1→" in note
    assert "1 of 1" in note  # the one crossed 24.2 code applies (has tests)
    assert "24.2" in note  # the crossed release
    assert "must-fix" in note  # 24_2_fix_test_case_validation is must_fix
    assert "docs/profile_boundaries.md" in note


def test_upgrade_silent_when_no_crossed_code_applies() -> None:
    """_UPGRADABLE crosses 24.2 but ships no <test>, so 24_2 does not apply."""
    from galaxy_tool_refactor_registry.resolve import resolve_upgrade_codes

    result = facade.upgrade(_UPGRADABLE, codes=resolve_upgrade_codes())
    assert not [n for n in result.notes if "profile-behaviour" in n]


def test_upgrade_no_profile_warns_from_1601_baseline() -> None:
    """A tool with no profile= runs as 16.01, so the bump to latest crosses many."""
    from galaxy_tool_refactor_registry.resolve import resolve_upgrade_codes

    no_profile = (
        b'<tool id="m" name="M" version="1.0.0">'
        # A chained command (not a lone statement) so the 20.09 set_e note applies
        # after the §28 detector tightening.
        b"<command><![CDATA[echo a && echo b]]></command><inputs/>"
        b'<outputs><data name="o"/></outputs></tool>'
    )
    result = facade.upgrade(no_profile, codes=resolve_upgrade_codes())
    semantic = [n for n in result.notes if "profile-behaviour" in n]
    assert len(semantic) == 1
    # baseline is Galaxy's 16.01 default; crossed releases span 16.04..24.2.
    assert "16.01→" in semantic[0]
    assert "16.04" in semantic[0] and "20.09" in semantic[0]


def test_upgrade_applies_runtime_gated_from_work_dir_fix() -> None:
    """Crossing UP through 21.09 strips a whitespace from_work_dir (runtime-gated)."""
    from galaxy_tool_refactor_registry.resolve import resolve_upgrade_codes

    # Declares 20.09 (< 21.09), so the bump to latest CROSSES the 21.09 boundary.
    tool = (
        b'<tool id="m" name="M" version="1.0.0" profile="20.09">'
        b"<command><![CDATA[echo x]]></command><inputs/>"
        b'<outputs><data name="o" from_work_dir=" out.txt "/></outputs></tool>'
    )
    result = facade.upgrade(tool, codes=resolve_upgrade_codes())
    assert b'from_work_dir="out.txt"' in result.formatted
    assert b'from_work_dir=" out.txt "' not in result.formatted


def test_crossing_gate_leaves_already_past_tool_untouched() -> None:
    """A tool already declaring >=21.09 keeps its whitespace from_work_dir.

    Galaxy already quotes from_work_dir at that profile, so the literal whitespace is
    the tool's current behaviour — a behaviour-preserving upgrade must not rewrite it.
    """
    from galaxy_tool_refactor_registry.resolve import resolve_upgrade_codes

    tool = (
        b'<tool id="m" name="M" version="1.0.0" profile="24.0">'
        b"<command><![CDATA[echo x]]></command><inputs/>"
        b'<outputs><data name="o" from_work_dir=" out.txt "/></outputs></tool>'
    )
    result = facade.upgrade(tool, codes=resolve_upgrade_codes())
    assert b'from_work_dir=" out.txt "' in result.formatted


def test_upgrade_already_latest_has_no_semantic_warning() -> None:
    """A tool already declaring the latest profile isn't bumped, so no warning."""
    from galaxy_tool_source.profiles import latest_profile

    from galaxy_tool_refactor_registry.resolve import resolve_upgrade_codes

    at_latest = (
        f'<tool id="m" name="M" version="1.0.0" profile="{latest_profile()}">'
        "<command><![CDATA[echo x]]></command><inputs/>"
        '<outputs><data name="o"/></outputs></tool>'
    ).encode()
    result = facade.upgrade(at_latest, codes=resolve_upgrade_codes())
    assert not [n for n in result.notes if "runtime-behaviour" in n]


def _pass_notes(result: object) -> list[str]:
    return [n for n in result.notes if "behavior-preserving" in n]  # type: ignore[attr-defined]


def test_upgrade_behavior_preserving_verdict_true_with_clean_pass_note() -> None:
    """_UPGRADABLE bumps 24.1->latest crossing 24.2, but ships no <test>, so no
    crossed code applies: the upgrade is behavior-preserving and says so."""
    from galaxy_tool_refactor_registry.resolve import resolve_upgrade_codes

    result = facade.upgrade(_UPGRADABLE, codes=resolve_upgrade_codes())
    assert result.behavior_preserving is True
    pass_notes = _pass_notes(result)
    assert len(pass_notes) == 1
    assert "24.1→" in pass_notes[0]
    # The positive note is distinct from the negative semantic warning.
    assert not [n for n in result.notes if "profile-behaviour" in n]


def test_upgrade_behavior_preserving_false_when_a_crossed_code_applies() -> None:
    """Opting past the gate crosses 24.2 with tests -> not behavior-preserving."""
    from galaxy_tool_refactor_registry.resolve import resolve_upgrade_codes

    with_tests = (
        b'<tool id="m" name="M" version="1.0.0" profile="24.1">'
        b"<command><![CDATA[echo x]]></command>"
        b'<inputs><param name="i" type="data" format="BAM"/></inputs>'
        b'<outputs><data name="o"/></outputs>'
        b'<tests><test><param name="i" value="x.bam"/><output name="o"/></test>'
        b"</tests></tool>"
    )
    result = facade.upgrade(
        with_tests, codes=resolve_upgrade_codes(), allow_behavior_change=True
    )
    assert result.behavior_preserving is False
    assert _pass_notes(result) == []


def test_upgrade_behavior_preserving_none_for_macro_token_profile() -> None:
    """A macro-token profile= is unplaceable, so the verdict is undetermined."""
    from galaxy_tool_refactor_registry.resolve import resolve_upgrade_codes

    macro_profile = (
        b'<tool id="m" name="M" version="1.0.0" profile="@PROFILE@">'
        b"<command><![CDATA[echo x]]></command><inputs/>"
        b'<outputs><data name="o"/></outputs></tool>'
    )
    result = facade.upgrade(macro_profile, codes=resolve_upgrade_codes())
    assert result.behavior_preserving is None
    assert _pass_notes(result) == []


def test_upgrade_already_latest_is_preserving_but_emits_no_pass_note() -> None:
    """A no-op upgrade (already latest) is vacuously preserving; no note is added."""
    from galaxy_tool_source.profiles import latest_profile

    from galaxy_tool_refactor_registry.resolve import resolve_upgrade_codes

    at_latest = (
        f'<tool id="m" name="M" version="1.0.0" profile="{latest_profile()}">'
        "<command><![CDATA[echo x]]></command><inputs/>"
        '<outputs><data name="o"/></outputs></tool>'
    ).encode()
    result = facade.upgrade(at_latest, codes=resolve_upgrade_codes())
    assert result.behavior_preserving is True
    assert _pass_notes(result) == []  # nothing advanced -> no story to tell


# --- the behavior-preserving default (the gate) -----------------------------------

_WITH_TESTS = (
    b'<tool id="m" name="M" version="1.0.0" profile="24.1">'
    b"<command><![CDATA[echo x]]></command>"
    b'<inputs><param name="i" type="data" format="BAM"/></inputs>'
    b'<outputs><data name="o"/></outputs>'
    b'<tests><test><param name="i" value="x.bam"/><output name="o"/></test>'
    b"</tests></tool>"
)


def test_upgrade_default_stops_before_an_unfixable_must_fix_boundary() -> None:
    """A 24.1 tool that ships tests stays at 24.1: 24.2's test-case validation
    applies and has no auto-fix, so the default walk does not cross it."""
    from galaxy_tool_refactor_registry.resolve import resolve_upgrade_codes

    result = facade.upgrade(_WITH_TESTS, codes=resolve_upgrade_codes())
    assert b'profile="24.1"' in result.formatted
    assert result.stopped_at == "24.1"
    assert result.blocking_codes == ("24_2_fix_test_case_validation",)
    stop_notes = [n for n in result.notes if "stopped at 24.1" in n]
    assert len(stop_notes) == 1
    assert "24_2_fix_test_case_validation" in stop_notes[0]
    assert "allow-behavior-change" in stop_notes[0]
    # Nothing was crossed, so there is no crossed-boundary warning to review.
    assert not [n for n in result.notes if "profile-behaviour" in n]


def test_upgrade_default_walks_up_to_the_boundary_from_below() -> None:
    """A no-profile tool with tests advances to 24.1 (not latest): everything
    below the 24.2 blocker is still taken."""
    from galaxy_tool_refactor_registry.resolve import resolve_upgrade_codes

    no_profile_with_tests = (
        b'<tool id="m" name="M" version="1.0.0">'
        b"<command><![CDATA[echo x]]></command><inputs/>"
        b'<outputs><data name="o"/></outputs>'
        b"<tests><test/></tests></tool>"
    )
    result = facade.upgrade(no_profile_with_tests, codes=resolve_upgrade_codes())
    assert b'profile="24.1"' in result.formatted
    assert result.stopped_at == "24.1"
    assert result.blocking_codes == ("24_2_fix_test_case_validation",)
    # The bump 16.01 -> 24.1 still crosses applicable consider-level codes; they
    # are warned about (and the verdict stays honest), but they do not stop the
    # walk under the default policy.
    assert [n for n in result.notes if "profile-behaviour" in n]
    assert result.behavior_preserving is False


def test_upgrade_allow_behavior_change_restores_the_walk_to_latest() -> None:
    from galaxy_tool_source.profiles import latest_profile

    from galaxy_tool_refactor_registry.resolve import resolve_upgrade_codes

    result = facade.upgrade(
        _WITH_TESTS, codes=resolve_upgrade_codes(), allow_behavior_change=True
    )
    assert f'profile="{latest_profile()}"'.encode() in result.formatted
    assert result.stopped_at is None
    # The work list is still reported so the user knows what to review.
    assert result.blocking_codes == ("24_2_fix_test_case_validation",)
    assert result.behavior_preserving is False
    assert [n for n in result.notes if "profile-behaviour" in n]


def test_upgrade_target_profile_caps_the_walk() -> None:
    from galaxy_tool_refactor_registry.resolve import resolve_upgrade_codes

    clean = (
        b'<tool id="m" name="M" version="1.0.0">'
        b"<command><![CDATA[echo x]]></command><inputs/>"
        b'<outputs><data name="o"/></outputs></tool>'
    )
    result = facade.upgrade(
        clean, codes=resolve_upgrade_codes(), target_profile="20.09"
    )
    assert b'profile="20.09"' in result.formatted
    assert result.stopped_at == "20.09"
    assert result.blocking_codes == ()


def test_upgrade_unknown_target_profile_raises() -> None:
    import pytest

    from galaxy_tool_refactor_registry.errors import UnknownProfile
    from galaxy_tool_refactor_registry.resolve import resolve_upgrade_codes

    with pytest.raises(UnknownProfile):
        facade.upgrade(
            _UPGRADABLE, codes=resolve_upgrade_codes(), target_profile="99.99"
        )


def test_upgrade_credits_an_auto_fixed_must_fix_code() -> None:
    """Crossing 21.09 with a fixable from_work_dir is auto-fixed AND credited:
    the verdict is behavior-preserving and no crossed-boundary warning remains."""
    from galaxy_tool_source.profiles import latest_profile

    from galaxy_tool_refactor_registry.resolve import resolve_upgrade_codes

    tool = (
        b'<tool id="m" name="M" version="1.0.0" profile="20.09">'
        b"<command><![CDATA[echo x]]></command><inputs/>"
        b'<outputs><data name="o" from_work_dir=" out.txt "/></outputs></tool>'
    )
    result = facade.upgrade(tool, codes=resolve_upgrade_codes())
    assert f'profile="{latest_profile()}"'.encode() in result.formatted
    assert result.auto_fixed_codes == ("21_09_fix_from_work_dir_whitespace",)
    assert result.blocking_codes == ()
    assert result.behavior_preserving is True
    assert not [n for n in result.notes if "profile-behaviour" in n]
    assert [n for n in result.notes if "fixed automatically" in n]


def test_upgrade_unfixable_16_04_blocker_leaves_profile_unchanged() -> None:
    """A bucket-B interpreter (leading Cheetah) cannot be auto-fixed and 16.04
    has no vendored predecessor, so the declaration must not move at all."""
    from galaxy_tool_refactor_registry.resolve import resolve_upgrade_codes

    bucket_b = (
        b'<tool id="m" name="M" version="1.0.0">'
        b'<command interpreter="python"><![CDATA[$script $input]]></command>'
        b'<inputs/><outputs><data name="o"/></outputs></tool>'
    )
    result = facade.upgrade(bucket_b, codes=resolve_upgrade_codes())
    assert b"profile=" not in result.formatted
    assert result.stopped_at == "16.01"
    assert "16_04_fix_interpreter" in result.blocking_codes
    assert [n for n in result.notes if "unchanged" in n]


def test_upgrade_macro_token_profile_fails_closed() -> None:
    """An unresolvable @PROFILE@ baseline cannot place boundaries: no advance."""
    from galaxy_tool_refactor_registry.resolve import resolve_upgrade_codes

    macro_profile = (
        b'<tool id="m" name="M" version="1.0.0" profile="@PROFILE@">'
        b"<command><![CDATA[echo x]]></command><inputs/>"
        b'<outputs><data name="o"/></outputs></tool>'
    )
    result = facade.upgrade(macro_profile, codes=resolve_upgrade_codes())
    assert b'profile="@PROFILE@"' in result.formatted
    assert result.behavior_preserving is None
    assert result.steps_applied == ()
    assert [n for n in result.notes if "macro token" in n]


def test_upgrade_resolvable_inline_token_baseline_gates_normally() -> None:
    """A @PROFILE@ whose inline token resolves to 24.1 is placeable: the gate
    runs against the resolved baseline instead of failing closed."""
    from galaxy_tool_refactor_registry.resolve import resolve_upgrade_codes

    tokenised = (
        b'<tool id="m" name="M" version="1.0.0" profile="@PROFILE@">'
        b'<macros><token name="@PROFILE@">24.1</token></macros>'
        b"<command><![CDATA[echo x]]></command><inputs/>"
        b'<outputs><data name="o"/></outputs>'
        b"<tests><test/></tests></tool>"
    )
    result = facade.upgrade(tokenised, codes=resolve_upgrade_codes())
    assert result.stopped_at == "24.1"
    assert result.blocking_codes == ("24_2_fix_test_case_validation",)
    assert b'profile="@PROFILE@"' in result.formatted  # the reference survives


def test_introspection_lists_rulesets_and_rules() -> None:
    rulesets_info = facade.list_rulesets()
    names = {r.name for r in rulesets_info}
    assert names == {"cosmetic", "default", "iuc", "strict"}
    assert any(r.is_default and r.name == "default" for r in rulesets_info)

    rules = facade.list_rules()
    codes = {r.code for r in rules}
    assert "GTR012" not in codes  # upgrade-pipeline: excluded by default
    assert "GTR092" not in codes  # opt-in-command-only: excluded by default
    with_upgrade = {r.code for r in facade.list_rules(include_upgrade=True)}
    assert "GTR012" in with_upgrade
    assert "GTR092" in with_upgrade
    # Each fixable rule is in at least one ruleset; advisory rules in strict only.
    default_rule = next(r for r in rules if r.code == "GTR002")
    assert "default" in default_rule.rulesets and default_rule.fixable
    adv_rule = next(r for r in rules if r.code == "GTR021")
    assert adv_rule.rulesets == ("strict",) and not adv_rule.fixable


_REFS_TOOL = (
    b'<tool id="m" name="M" version="1.0.0" profile="21.09">'
    b"<command><![CDATA[tool $input --opt $opts $adv.x]]></command>"
    b'<outputs><data name="o" label="$input.name on $on_string"/></outputs>'
    b"</tool>"
)


def test_find_references_matches_root_and_segment() -> None:
    result = facade.find_references(_REFS_TOOL, name="input")
    # $input in <command> and $input.name in the output label both match.
    sections = sorted(o.section for o in result.occurrences)
    assert sections == ["command", "output_data_label:o"]
    assert all(o.reference.startswith("$input") for o in result.occurrences)


def test_find_references_segment_of_qualified_access() -> None:
    # $adv.x matches a query for the leaf segment "x".
    result = facade.find_references(_REFS_TOOL, name="x")
    assert [o.reference for o in result.occurrences] == ["$adv.x"]


def test_find_references_no_matches_is_empty() -> None:
    assert facade.find_references(_REFS_TOOL, name="absent").occurrences == ()


def test_rename_param_rewrites_all_sites() -> None:
    result = facade.rename_param(_REFS_TOOL, old="input", new="sample")
    assert result.changed
    assert result.renamed >= 2  # $input in command + $input.name in label
    assert result.formatted is not None
    text = result.formatted.decode("utf-8")
    assert "$sample" in text and "$input" not in text
    assert "<![CDATA[" in text  # the command's CDATA wrapper is preserved
    # find-references over the result confirms the invariant.
    assert facade.find_references(result.formatted, name="input").occurrences == ()
    assert facade.find_references(result.formatted, name="sample").occurrences


def test_rename_param_not_found_bails() -> None:
    result = facade.rename_param(_REFS_TOOL, old="absent", new="x")
    assert not result.changed
    assert result.reason == "not-found"
    assert result.formatted is None


def test_rename_param_does_not_mutate_source_on_bail() -> None:
    document = load_tool(_REFS_TOOL)
    before = to_bytes(document.tree)
    # A shadowing #set makes this bail; the source document must be untouched.
    shadow_tool = (
        b'<tool id="m" name="M" version="1.0.0" profile="21.09">'
        b"<command><![CDATA[#set $input = 1\ntool $input]]></command></tool>"
    )
    result = facade.rename_param(load_tool(shadow_tool), old="input", new="sample")
    assert not result.changed
    assert result.reason == "shadowed"
    assert to_bytes(document.tree) == before


def test_rename_param_writes_when_path_given(tmp_path: Path) -> None:
    target = tmp_path / "tool.xml"
    result = facade.rename_param(
        _REFS_TOOL, old="input", new="sample", write_path=target
    )
    assert result.changed
    assert target.read_bytes() == result.formatted


def test_convert_help_converts_a_gated_tool(tmp_path: Path) -> None:
    tool = (
        b"<tool id='x' name='X' version='1.0' profile='24.2'>"
        b"<command><![CDATA[echo hi]]></command>"
        b"<help>Title\n=====\n\nSome **bold** text.\n</help></tool>"
    )
    out = tmp_path / "converted.xml"
    result = facade.convert_help(tool, write_path=out)
    assert result.converted and result.skip_reason is None
    assert b'format="markdown"' in result.formatted
    assert b"# Title" in result.formatted
    assert out.read_bytes() == result.formatted


def test_convert_help_reports_the_profile_gate(tmp_path: Path) -> None:
    tool = (
        b"<tool id='x' name='X' version='1.0'>"
        b"<command><![CDATA[echo hi]]></command>"
        b"<help>Title\n=====\n\nSome **bold** text.\n</help></tool>"
    )
    out = tmp_path / "converted.xml"
    result = facade.convert_help(tool, write_path=out)
    assert not result.converted
    assert result.skip_reason is not None and "upgrade" in result.skip_reason
    assert not out.exists()  # nothing written when not converted


_TOKENIZABLE = (
    b'<tool id="m" name="M" version="1.20+galaxy0" profile="24.0">'
    b"<command><![CDATA[echo x]]></command>"
    b'<requirements><requirement type="package" version="1.20">samtools'
    b"</requirement></requirements>"
    b'<inputs><param name="i" type="text"/></inputs>'
    b'<outputs><data name="o"/></outputs></tool>'
)


def test_tokenize_version_applies_and_serialises() -> None:
    result = facade.tokenize_version(_TOKENIZABLE)
    assert result.tokenized is True and result.skip_reason is None
    assert b'version="@TOOL_VERSION@+galaxy@VERSION_SUFFIX@"' in result.formatted
    assert b'<token name="@TOOL_VERSION@">1.20</token>' in result.formatted
    assert b'<requirement type="package" version="@TOOL_VERSION@">' in result.formatted


def test_tokenize_version_reports_skip_reason() -> None:
    plain = _TOKENIZABLE.replace(b'version="1.20+galaxy0"', b'version="1.20"')
    result = facade.tokenize_version(plain)
    assert result.tokenized is False
    assert result.skip_reason is not None and "+galaxy" in result.skip_reason
    assert b'version="1.20"' in result.formatted  # unchanged tool echoed


def test_tokenize_version_macros_file_emits_import_and_new_file(tmp_path: Path) -> None:
    tool = tmp_path / "tool.xml"
    tool.write_bytes(_TOKENIZABLE)
    result = facade.tokenize_version(tool, macros_file="macros.xml")
    assert result.tokenized is True and result.skip_reason is None
    assert b"<import>macros.xml</import>" in result.formatted
    assert b'<token name="@TOOL_VERSION@">' not in result.formatted  # not inline
    assert result.new_macros is not None
    assert result.new_macros.path == "macros.xml"
    assert b'<token name="@TOOL_VERSION@">1.20</token>' in result.new_macros.content
    assert b'<token name="@VERSION_SUFFIX@">0</token>' in result.new_macros.content


def test_tokenize_version_macros_file_writes_both(tmp_path: Path) -> None:
    tool = tmp_path / "tool.xml"
    tool.write_bytes(_TOKENIZABLE)
    result = facade.tokenize_version(tool, write_path=tool, macros_file="macros.xml")
    assert result.tokenized is True
    macros = tmp_path / "macros.xml"
    assert macros.exists()
    assert b'<token name="@TOOL_VERSION@">1.20</token>' in macros.read_bytes()
    assert b"<import>macros.xml</import>" in tool.read_bytes()


def test_tokenize_version_macros_file_merges_into_existing(tmp_path: Path) -> None:
    # An existing macros file with no version tokens: the tokens are merged in (not
    # refused), and the result records it was not newly created.
    tool = tmp_path / "tool.xml"
    tool.write_bytes(_TOKENIZABLE)
    (tmp_path / "macros.xml").write_text(
        '<macros><token name="@CITE@">ref</token></macros>', encoding="utf-8"
    )
    result = facade.tokenize_version(tool, macros_file="macros.xml")
    assert result.tokenized is True
    assert result.new_macros is not None and result.new_macros.created is False
    assert b'<token name="@CITE@">ref</token>' in result.new_macros.content
    assert b'<token name="@TOOL_VERSION@">1.20</token>' in result.new_macros.content
    assert b"<import>macros.xml</import>" in result.formatted


def test_tokenize_version_macros_file_declines_token_conflict(tmp_path: Path) -> None:
    # An existing file already defines @TOOL_VERSION@ at a different value: decline.
    tool = tmp_path / "tool.xml"
    tool.write_bytes(_TOKENIZABLE)
    (tmp_path / "macros.xml").write_text(
        '<macros><token name="@TOOL_VERSION@">9.9</token>'
        '<token name="@VERSION_SUFFIX@">9</token></macros>',
        encoding="utf-8",
    )
    result = facade.tokenize_version(tool, macros_file="macros.xml")
    assert result.tokenized is False
    assert result.skip_reason is not None and "9.9" in result.skip_reason


def test_tokenize_version_macros_file_needs_a_path() -> None:
    result = facade.tokenize_version(_TOKENIZABLE, macros_file="macros.xml")
    assert result.tokenized is False
    assert result.skip_reason is not None and "needs a tool path" in result.skip_reason


def test_tokenize_version_macros_file_rejects_unsafe_name(tmp_path: Path) -> None:
    tool = tmp_path / "tool.xml"
    tool.write_bytes(_TOKENIZABLE)
    result = facade.tokenize_version(tool, macros_file="../evil.xml")
    assert result.tokenized is False
    assert result.skip_reason is not None and "plain filename" in result.skip_reason


_BARE_VERSION = (
    b'<tool id="m" name="M" version="1.20" profile="24.0">'
    b"<command><![CDATA[echo x]]></command>"
    b'<requirements><requirement type="package" version="1.20">samtools'
    b"</requirement></requirements>"
    b'<inputs><param name="i" type="text"/></inputs>'
    b'<outputs><data name="o"/></outputs></tool>'
)


def test_adopt_version_suffix_adds_galaxy0_and_tokenizes() -> None:
    result = facade.adopt_version_suffix(_BARE_VERSION)
    assert result.tokenized is True and result.skip_reason is None
    assert b'version="@TOOL_VERSION@+galaxy@VERSION_SUFFIX@"' in result.formatted
    assert b'<token name="@TOOL_VERSION@">1.20</token>' in result.formatted
    assert b'<token name="@VERSION_SUFFIX@">0</token>' in result.formatted
    assert b'<requirement type="package" version="@TOOL_VERSION@">' in result.formatted


def test_adopt_version_suffix_skips_already_suffixed() -> None:
    result = facade.adopt_version_suffix(_TOKENIZABLE)  # 1.20+galaxy0
    assert result.tokenized is False
    assert result.skip_reason is not None


def test_adopt_version_suffix_skips_without_matching_requirement() -> None:
    plain = _BARE_VERSION.replace(b'version="1.20">samtools', b'version="9.9">samtools')
    result = facade.adopt_version_suffix(plain)
    assert result.tokenized is False
    assert result.skip_reason is not None and "requirement" in result.skip_reason


def test_adopt_version_suffix_writes_when_path_given(tmp_path: Path) -> None:
    tool = tmp_path / "tool.xml"
    tool.write_bytes(_BARE_VERSION)
    result = facade.adopt_version_suffix(tool, write_path=tool)
    assert result.tokenized is True
    assert b'version="@TOOL_VERSION@+galaxy@VERSION_SUFFIX@"' in tool.read_bytes()


def test_tokenize_version_shared_consensus_writes_group(tmp_path: Path) -> None:
    a = tmp_path / "a.xml"
    b = tmp_path / "b.xml"
    a.write_bytes(_TOKENIZABLE.replace(b'id="m"', b'id="a"'))
    b.write_bytes(_TOKENIZABLE.replace(b'id="m"', b'id="b"'))
    plan = facade.tokenize_version_shared(
        tmp_path / "macros.xml", target_tools=[a, b], write=True
    )
    assert plan.skip_reason is None
    assert {e.path.name for e in plan.tool_edits} == {"a.xml", "b.xml"}
    assert (tmp_path / "macros.xml").exists()
    for tool in (a, b):
        assert b"<import>macros.xml</import>" in tool.read_bytes()
        assert b'version="@TOOL_VERSION@+galaxy@VERSION_SUFFIX@"' in tool.read_bytes()
