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


def test_facade_resolves_and_places_opaque_top_level_expand() -> None:
    """The facade resolves an opaque inline-macro ``<expand>`` to the IUC tag it
    expands to and actively places it (the GTR013 resolution layer, §53), going
    beyond the bare pinning pipeline. Here ``<expand macro="bt">`` resolves to
    ``<xrefs>`` and so sorts after ``<macros>``, where the bare pipeline pins it
    before ``<macros>``."""
    source = (
        b'<tool id="t" name="T" version="0.1" profile="24.1">'
        b"<description>d</description>"
        b'<expand macro="bt"/>'
        b'<macros><xml name="bt"><xrefs>'
        b'<xref type="bio.tools">x</xref></xrefs></xml></macros>'
        b"<command><![CDATA[echo x]]></command>"
        b"<inputs/><outputs/></tool>"
    )
    out = facade.run(source, codes=resolve_codes()).formatted
    # Resolved + placed: <macros> now precedes the <expand> call.
    assert out.index(b"<macros") < out.index(b'<expand macro="bt"')
    # The facade does MORE than the bare pinning pipeline (which leaves it first).
    assert out != _today_format(source)
    assert _today_format(source).index(b'<expand macro="bt"') < _today_format(
        source
    ).index(b"<macros")


# A macros.xml imported by the tools below: one macro that expands to a single
# IUC element (<xrefs>) and one that expands to two (<requirements> + <citations>).
_IMPORTED_MACROS = (
    b"<macros>"
    b'<xml name="xref_block"><xrefs>'
    b'<xref type="bio.tools">x</xref></xrefs></xml>'
    b'<xml name="reqs_and_cites">'
    b'<requirements><requirement type="package">samtools</requirement></requirements>'
    b'<citations><citation type="doi">10.0/x</citation></citations></xml>'
    b"</macros>"
)


def test_facade_resolves_imported_macro_expand_into_iuc_slot(tmp_path: Path) -> None:
    """GTR013 §53 resolution layer, end-to-end via an IMPORTED macros.xml (not an
    inline block). ``<expand macro="xref_block">`` resolves through the imported
    file to a single ``<xrefs>`` (IUC rank 4), so it is actively placed after
    ``<macros>`` and before ``<command>`` — exercising ``top_level_expand_tags``'
    import resolution against the tool's source path (the real-world / vg-suite
    path the bare inline test does not cover)."""
    (tmp_path / "macros.xml").write_bytes(_IMPORTED_MACROS)
    tool = tmp_path / "tool.xml"
    tool.write_bytes(
        b'<tool id="t" name="T" version="0.1" profile="24.1">'
        b"<description>d</description>"
        b'<expand macro="xref_block"/>'
        b"<macros><import>macros.xml</import></macros>"
        b"<command><![CDATA[echo x]]></command>"
        b"<inputs/><outputs/></tool>"
    )
    out = facade.run(tool, codes=resolve_codes()).formatted
    assert out.index(b"<macros") < out.index(b'<expand macro="xref_block"')
    assert out.index(b'<expand macro="xref_block"') < out.index(b"<command")


def test_facade_pins_unresolvable_imported_expand_not_floated_to_end(
    tmp_path: Path,
) -> None:
    """GTR013 §53 pinning, end-to-end via an imported macros.xml: an ``<expand>``
    that resolves to MORE than one top-level element (``reqs_and_cites`` →
    ``<requirements>`` + ``<citations>``) cannot be placed, so it is pinned at its
    author position rather than floated past every known element to the end (the
    vg-suite bug). Here it sits between ``<command>`` and ``<inputs>`` and stays
    there after the full ``format``."""
    (tmp_path / "macros.xml").write_bytes(_IMPORTED_MACROS)
    tool = tmp_path / "tool.xml"
    tool.write_bytes(
        b'<tool id="t" name="T" version="0.1" profile="24.1">'
        b"<description>d</description>"
        b"<macros><import>macros.xml</import></macros>"
        b"<command><![CDATA[echo x]]></command>"
        b'<expand macro="reqs_and_cites"/>'
        b"<inputs/><outputs/><help>h</help></tool>"
    )
    out = facade.run(tool, codes=resolve_codes()).formatted
    expand_at = out.index(b'<expand macro="reqs_and_cites"')
    # Pinned between <command> and <inputs>; crucially, NOT after the last element.
    assert out.index(b"<command") < expand_at < out.index(b"<inputs")
    assert expand_at < out.index(b"<help")


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


def test_upgrade_modernize_bumps_profile_and_runs_migration() -> None:
    from galaxy_tool_refactor_registry import deployment
    from galaxy_tool_refactor_registry.resolve import resolve_upgrade_codes

    result = facade.upgrade(
        _UPGRADABLE, codes=resolve_upgrade_codes(), modernize=True
    )
    # The walk lands on the deployment ceiling, not the (pre-release) latest.
    assert f'profile="{deployment.DEPLOYMENT_CEILING}"'.encode() in result.formatted
    assert b'format="bam"' in result.formatted  # the 24.1 -> 24.2 migration ran
    assert "24.1" in result.steps_applied
    assert any("upgraded past 24.1" in note for note in result.notes)


def test_upgrade_modernize_ignore_fixtypos_still_upgrades() -> None:
    from galaxy_tool_refactor_registry import deployment
    from galaxy_tool_refactor_registry.resolve import resolve_upgrade_codes

    codes = resolve_upgrade_codes(ignore=["GTR006"])
    result = facade.upgrade(_UPGRADABLE, codes=codes, modernize=True)
    # The profile upgrade is intrinsic; dropping FixTypos does not disable it.
    assert f'profile="{deployment.DEPLOYMENT_CEILING}"'.encode() in result.formatted


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
        with_tests,
        codes=resolve_upgrade_codes(),
        modernize=True,
        allow_behavior_change=True,
    )
    semantic = [n for n in result.notes if "profile-behaviour" in n]
    assert len(semantic) == 1
    note = semantic[0]
    assert "24.1→" in note
    assert "1 of 1" in note  # the one crossed 24.2 code applies (has tests)
    assert "24.2" in note  # the crossed release
    assert "must-fix" in note  # 24_2_fix_test_case_validation is must_fix
    assert "docs/profile_boundaries.md" in note


def test_upgrade_modernize_silent_when_no_crossed_code_applies() -> None:
    """_UPGRADABLE crosses 24.2 but ships no <test>, so 24_2 does not apply."""
    from galaxy_tool_refactor_registry.resolve import resolve_upgrade_codes

    result = facade.upgrade(
        _UPGRADABLE, codes=resolve_upgrade_codes(), modernize=True
    )
    assert not [n for n in result.notes if "profile-behaviour" in n]


def test_upgrade_modernize_no_profile_warns_from_1601_baseline() -> None:
    """A tool with no profile= runs as 16.01, so the bump to latest crosses many."""
    from galaxy_tool_refactor_registry.resolve import resolve_upgrade_codes

    no_profile = (
        b'<tool id="m" name="M" version="1.0.0">'
        # A chained command (not a lone statement) so the 20.09 set_e note applies
        # after the §28 detector tightening.
        b"<command><![CDATA[echo a && echo b]]></command><inputs/>"
        b'<outputs><data name="o"/></outputs></tool>'
    )
    result = facade.upgrade(no_profile, codes=resolve_upgrade_codes(), modernize=True)
    semantic = [n for n in result.notes if "profile-behaviour" in n]
    assert len(semantic) == 1
    # baseline is Galaxy's 16.01 default; crossed releases span 16.04..24.2.
    assert "16.01→" in semantic[0]
    assert "16.04" in semantic[0] and "20.09" in semantic[0]


def test_upgrade_modernize_applies_runtime_gated_from_work_dir_fix() -> None:
    """Crossing UP through 21.09 strips a whitespace from_work_dir (runtime-gated)."""
    from galaxy_tool_refactor_registry.resolve import resolve_upgrade_codes

    # Declares 20.09 (< 21.09), so the modernize walk to latest CROSSES 21.09.
    tool = (
        b'<tool id="m" name="M" version="1.0.0" profile="20.09">'
        b"<command><![CDATA[echo x]]></command><inputs/>"
        b'<outputs><data name="o" from_work_dir=" out.txt "/></outputs></tool>'
    )
    result = facade.upgrade(tool, codes=resolve_upgrade_codes(), modernize=True)
    assert b'from_work_dir="out.txt"' in result.formatted
    assert b'from_work_dir=" out.txt "' not in result.formatted


def test_upgrade_default_kept_tool_gets_no_runtime_gated_fix() -> None:
    """A tool kept at its declared profile crosses nothing, so no gated fix runs.

    The same 20.09 tool validates where it sits, so the minimal default keeps
    it there; the 21.09 from_work_dir strip must NOT apply (Galaxy still runs
    the tool under the old quoting behaviour at 20.09).
    """
    from galaxy_tool_refactor_registry.resolve import resolve_upgrade_codes

    tool = (
        b'<tool id="m" name="M" version="1.0.0" profile="20.09">'
        b"<command><![CDATA[echo x]]></command><inputs/>"
        b'<outputs><data name="o" from_work_dir=" out.txt "/></outputs></tool>'
    )
    result = facade.upgrade(tool, codes=resolve_upgrade_codes())
    assert b'profile="20.09"' in result.formatted
    assert b'from_work_dir=" out.txt "' in result.formatted
    assert result.auto_fixed_codes == ()


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


def test_upgrade_modernize_behavior_preserving_true_with_clean_pass_note() -> None:
    """_UPGRADABLE bumps 24.1->latest crossing 24.2, but ships no <test>, so no
    crossed code applies: the upgrade is behavior-preserving and says so."""
    from galaxy_tool_refactor_registry.resolve import resolve_upgrade_codes

    result = facade.upgrade(
        _UPGRADABLE, codes=resolve_upgrade_codes(), modernize=True
    )
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
        with_tests,
        codes=resolve_upgrade_codes(),
        modernize=True,
        allow_behavior_change=True,
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


# --- the minimal-bump default ------------------------------------------------------

_WITH_TESTS = (
    b'<tool id="m" name="M" version="1.0.0" profile="24.1">'
    b"<command><![CDATA[echo x]]></command>"
    b'<inputs><param name="i" type="data" format="BAM"/></inputs>'
    b'<outputs><data name="o"/></outputs>'
    b'<tests><test><param name="i" value="x.bam"/><output name="o"/></test>'
    b"</tests></tool>"
)

# Invalid at its declared 20.09 (<required_files> entered the schema at 21.09),
# valid as-is at 21.09+: the bump-direct minimal case.
_NEEDS_BUMP = (
    b'<tool id="r" name="R" version="1.0.0" profile="20.09">'
    b'<required_files><include path="x.py"/></required_files>'
    b"<command><![CDATA[echo x]]></command>"
    b"<inputs/><outputs/></tool>"
)


def test_upgrade_default_keeps_a_valid_declared_profile() -> None:
    """The minimal default: a tool that validates at its declared profile is
    left there, even when newer profiles would be reachable."""
    from galaxy_tool_refactor_registry.resolve import resolve_upgrade_codes

    result = facade.upgrade(_WITH_TESTS, codes=resolve_upgrade_codes())
    assert b'profile="24.1"' in result.formatted
    assert result.baseline_profile == "24.1"
    assert result.reached_profile == "24.1"
    assert result.stopped_at is None  # a walk-mode concept; no walk ran
    assert result.steps_applied == ()
    # The modernize review list is still reported for introspection.
    assert result.blocking_codes == ("24_2_fix_test_case_validation",)
    assert result.behavior_preserving is True  # nothing crossed
    kept_notes = [n for n in result.notes if "kept" in n]
    assert len(kept_notes) == 1
    assert "24.1" in kept_notes[0]
    assert "--modernize" in kept_notes[0]


def test_upgrade_default_leaves_an_undeclared_tool_undeclared() -> None:
    """A no-profile tool valid under Galaxy's 16.01 legacy default stays
    undeclared: declaring a profile is best practice, not strictly needed."""
    from galaxy_tool_refactor_registry.resolve import resolve_upgrade_codes

    no_profile = (
        b'<tool id="m" name="M" version="1.0.0">'
        b"<command><![CDATA[echo x]]></command><inputs/>"
        b'<outputs><data name="o"/></outputs></tool>'
    )
    result = facade.upgrade(no_profile, codes=resolve_upgrade_codes())
    assert b"profile=" not in result.formatted
    assert result.baseline_profile == "16.01"
    assert result.reached_profile == "16.01"
    assert result.stopped_at is None
    undeclared_notes = [n for n in result.notes if "undeclared" in n]
    assert len(undeclared_notes) == 1
    assert "--modernize" in undeclared_notes[0]


def test_upgrade_default_bumps_to_the_minimum_valid_profile() -> None:
    """Invalid at the declared profile: bump to the MINIMUM valid one, no further."""
    from galaxy_tool_source.profiles import latest_profile

    from galaxy_tool_refactor_registry.resolve import resolve_upgrade_codes

    result = facade.upgrade(_NEEDS_BUMP, codes=resolve_upgrade_codes())
    assert b'profile="21.09"' in result.formatted
    assert f'profile="{latest_profile()}"'.encode() not in result.formatted
    assert result.baseline_profile == "20.09"
    assert result.reached_profile == "21.09"
    bump_notes = [n for n in result.notes if "minimum" in n]
    assert len(bump_notes) == 1
    assert "20.09" in bump_notes[0] and "21.09" in bump_notes[0]


def test_upgrade_default_minimal_bump_applies_crossed_runtime_fixes() -> None:
    """A needed bump crosses 21.09, so the from_work_dir gated fix applies."""
    from galaxy_tool_refactor_registry.resolve import resolve_upgrade_codes

    tool = (
        b'<tool id="r" name="R" version="1.0.0" profile="20.09">'
        b'<required_files><include path="x.py"/></required_files>'
        b"<command><![CDATA[echo x]]></command><inputs/>"
        b'<outputs><data name="o" from_work_dir=" out.txt "/></outputs></tool>'
    )
    result = facade.upgrade(tool, codes=resolve_upgrade_codes())
    assert b'profile="21.09"' in result.formatted
    assert b'from_work_dir="out.txt"' in result.formatted
    assert result.auto_fixed_codes == ("21_09_fix_from_work_dir_whitespace",)


def test_upgrade_default_unreachable_leaves_profile_unchanged() -> None:
    """Nothing at or above the baseline validates: profile= must not move."""
    from galaxy_tool_source.profiles import latest_profile

    from galaxy_tool_refactor_registry.resolve import resolve_upgrade_codes

    latest = latest_profile()
    # A comma-list data format validates at no profile at or above the latest.
    stuck = (
        f'<tool id="m" name="M" version="1.0.0" profile="{latest}">'
        "<command><![CDATA[echo x]]></command><inputs/>"
        '<outputs><data name="o" format="fasta,fastq"/></outputs></tool>'
    ).encode()
    result = facade.upgrade(stuck, codes=resolve_upgrade_codes())
    assert f'profile="{latest}"'.encode() in result.formatted
    assert result.baseline_profile == latest
    assert result.reached_profile == latest
    assert result.steps_applied == ()
    unreachable_notes = [n for n in result.notes if "left unchanged" in n]
    assert len(unreachable_notes) == 1
    assert latest in unreachable_notes[0]


def test_upgrade_allow_behavior_change_alone_is_a_typed_error() -> None:
    """allow_behavior_change has no gate to lift outside a walk mode: typed error,
    never a silent imply."""
    import pytest

    from galaxy_tool_refactor_registry.errors import UpgradeFlagError
    from galaxy_tool_refactor_registry.resolve import resolve_upgrade_codes

    with pytest.raises(UpgradeFlagError):
        facade.upgrade(
            _UPGRADABLE, codes=resolve_upgrade_codes(), allow_behavior_change=True
        )


def test_upgrade_target_profile_composes_with_allow_behavior_change() -> None:
    """target_profile alone counts as a walk mode, so the flag pair is valid."""
    from galaxy_tool_refactor_registry.resolve import resolve_upgrade_codes

    result = facade.upgrade(
        _WITH_TESTS,
        codes=resolve_upgrade_codes(),
        allow_behavior_change=True,
        target_profile="24.2",
    )
    assert b'profile="24.2"' in result.formatted


# --- the modernize walk (the behavior gate) ----------------------------------------


def test_upgrade_modernize_stops_before_an_unfixable_must_fix_boundary() -> None:
    """A 24.1 tool that ships tests stays at 24.1: 24.2's test-case validation
    applies and has no auto-fix, so the gated modernize walk does not cross it."""
    from galaxy_tool_refactor_registry.resolve import resolve_upgrade_codes

    result = facade.upgrade(_WITH_TESTS, codes=resolve_upgrade_codes(), modernize=True)
    assert b'profile="24.1"' in result.formatted
    assert result.stopped_at == "24.1"
    assert result.blocking_codes == ("24_2_fix_test_case_validation",)
    stop_notes = [n for n in result.notes if "stopped at 24.1" in n]
    assert len(stop_notes) == 1
    assert "24_2_fix_test_case_validation" in stop_notes[0]
    assert "allow-behavior-change" in stop_notes[0]
    # Nothing was crossed, so there is no crossed-boundary warning to review.
    assert not [n for n in result.notes if "profile-behaviour" in n]


def test_upgrade_modernize_walks_up_to_the_boundary_from_below() -> None:
    """A no-profile tool with tests advances to 24.1 (not latest): everything
    below the 24.2 blocker is still taken."""
    from galaxy_tool_refactor_registry.resolve import resolve_upgrade_codes

    no_profile_with_tests = (
        b'<tool id="m" name="M" version="1.0.0">'
        b"<command><![CDATA[echo x]]></command><inputs/>"
        b'<outputs><data name="o"/></outputs>'
        b'<tests><test><param name="nosuch" value="1"/></test></tests></tool>'
    )
    result = facade.upgrade(
        no_profile_with_tests, codes=resolve_upgrade_codes(), modernize=True
    )
    assert b'profile="24.1"' in result.formatted
    assert result.stopped_at == "24.1"
    assert result.blocking_codes == ("24_2_fix_test_case_validation",)
    # The bump 16.01 -> 24.1 still crosses applicable consider-level codes; they
    # are warned about (and the verdict stays honest), but they do not stop the
    # walk under the gate's default policy.
    assert [n for n in result.notes if "profile-behaviour" in n]
    assert result.behavior_preserving is False


def test_upgrade_allow_behavior_change_walks_past_the_gate() -> None:
    """The flag lifts the behaviour gate; the deployment ceiling still caps."""
    from galaxy_tool_refactor_registry import deployment
    from galaxy_tool_refactor_registry.resolve import resolve_upgrade_codes

    result = facade.upgrade(
        _WITH_TESTS,
        codes=resolve_upgrade_codes(),
        modernize=True,
        allow_behavior_change=True,
    )
    ceiling = deployment.DEPLOYMENT_CEILING
    assert f'profile="{ceiling}"'.encode() in result.formatted
    assert result.stopped_at == ceiling
    # The work list is still reported so the user knows what to review.
    assert result.blocking_codes == ("24_2_fix_test_case_validation",)
    assert result.behavior_preserving is False
    assert [n for n in result.notes if "profile-behaviour" in n]


def test_upgrade_target_profile_caps_the_walk() -> None:
    """target_profile alone implies the walk mode and caps it."""
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


def test_upgrade_modernize_credits_an_auto_fixed_must_fix_code() -> None:
    """Crossing 21.09 with a fixable from_work_dir is auto-fixed AND credited:
    the verdict is behavior-preserving and no crossed-boundary warning remains."""
    from galaxy_tool_refactor_registry import deployment
    from galaxy_tool_refactor_registry.resolve import resolve_upgrade_codes

    tool = (
        b'<tool id="m" name="M" version="1.0.0" profile="20.09">'
        b"<command><![CDATA[echo x]]></command><inputs/>"
        b'<outputs><data name="o" from_work_dir=" out.txt "/></outputs></tool>'
    )
    result = facade.upgrade(tool, codes=resolve_upgrade_codes(), modernize=True)
    assert f'profile="{deployment.DEPLOYMENT_CEILING}"'.encode() in result.formatted
    assert result.auto_fixed_codes == ("21_09_fix_from_work_dir_whitespace",)
    assert result.blocking_codes == ()
    assert result.behavior_preserving is True
    assert not [n for n in result.notes if "profile-behaviour" in n]
    assert [n for n in result.notes if "fixed automatically" in n]


def test_upgrade_modernize_unfixable_16_04_blocker_keeps_profile_unmoved() -> None:
    """A bucket-B interpreter (leading Cheetah) cannot be auto-fixed and 16.04
    has no vendored predecessor, so the declaration must not move at all."""
    from galaxy_tool_refactor_registry.resolve import resolve_upgrade_codes

    bucket_b = (
        b'<tool id="m" name="M" version="1.0.0">'
        b'<command interpreter="python"><![CDATA[$script $input]]></command>'
        b'<inputs/><outputs><data name="o"/></outputs></tool>'
    )
    result = facade.upgrade(bucket_b, codes=resolve_upgrade_codes(), modernize=True)
    assert b"profile=" not in result.formatted
    assert result.stopped_at == "16.01"
    assert "16_04_fix_interpreter" in result.blocking_codes
    assert [n for n in result.notes if "unchanged" in n]


def test_upgrade_macro_token_profile_fails_closed() -> None:
    """An unresolvable @PROFILE@ baseline cannot place boundaries: no advance,
    in the default and the modernize walk alike."""
    from galaxy_tool_refactor_registry.resolve import resolve_upgrade_codes

    macro_profile = (
        b'<tool id="m" name="M" version="1.0.0" profile="@PROFILE@">'
        b"<command><![CDATA[echo x]]></command><inputs/>"
        b'<outputs><data name="o"/></outputs></tool>'
    )
    for modernize in (False, True):
        result = facade.upgrade(
            macro_profile, codes=resolve_upgrade_codes(), modernize=modernize
        )
        assert b'profile="@PROFILE@"' in result.formatted
        assert result.behavior_preserving is None
        assert result.steps_applied == ()
        assert [n for n in result.notes if "macro token" in n]


def test_upgrade_modernize_resolvable_inline_token_gates_normally() -> None:
    """A @PROFILE@ whose inline token resolves to 24.1 is placeable: the gate
    runs against the resolved baseline instead of failing closed."""
    from galaxy_tool_refactor_registry.resolve import resolve_upgrade_codes

    tokenised = (
        b'<tool id="m" name="M" version="1.0.0" profile="@PROFILE@">'
        b'<macros><token name="@PROFILE@">24.1</token></macros>'
        b"<command><![CDATA[echo x]]></command><inputs/>"
        b'<outputs><data name="o"/></outputs>'
        b'<tests><test><param name="nosuch" value="1"/></test></tests></tool>'
    )
    result = facade.upgrade(tokenised, codes=resolve_upgrade_codes(), modernize=True)
    assert result.stopped_at == "24.1"
    assert result.blocking_codes == ("24_2_fix_test_case_validation",)
    assert b'profile="@PROFILE@"' in result.formatted  # the reference survives


def test_upgrade_default_keeps_a_valid_inline_token_value() -> None:
    """The minimal default keeps a resolvable inline token's value untouched
    when the tool validates at it."""
    from galaxy_tool_refactor_registry.resolve import resolve_upgrade_codes

    tokenised = (
        b'<tool id="m" name="M" version="1.0.0" profile="@PROFILE@">'
        b'<macros><token name="@PROFILE@">24.1</token></macros>'
        b"<command><![CDATA[echo x]]></command><inputs/>"
        b'<outputs><data name="o"/></outputs></tool>'
    )
    result = facade.upgrade(tokenised, codes=resolve_upgrade_codes())
    assert b">24.1</token>" in result.formatted
    assert result.baseline_profile == "24.1"
    assert result.reached_profile == "24.1"


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


_CLEAN_LEGACY = (
    b'<tool id="m" name="M" version="1.0.0">'
    b"<command><![CDATA[echo x]]></command><inputs/>"
    b'<outputs><data name="o"/></outputs></tool>'
)


def test_upgrade_modernize_is_capped_at_the_deployment_ceiling() -> None:
    """A plain modernize walk lands on the deployment ceiling, not latest."""
    from galaxy_tool_refactor_registry import deployment
    from galaxy_tool_refactor_registry.resolve import resolve_upgrade_codes

    result = facade.upgrade(
        _CLEAN_LEGACY, codes=resolve_upgrade_codes(), modernize=True
    )
    ceiling = deployment.DEPLOYMENT_CEILING
    assert f'profile="{ceiling}"'.encode() in result.formatted
    assert result.stopped_at == ceiling
    assert [n for n in result.notes if "deployment ceiling" in n]


def test_upgrade_target_profile_may_exceed_the_deployment_ceiling() -> None:
    """An explicit target expresses intent: it wins over the deployment cap."""
    from galaxy_tool_source.profiles import latest_profile

    from galaxy_tool_refactor_registry.resolve import resolve_upgrade_codes

    result = facade.upgrade(
        _CLEAN_LEGACY,
        codes=resolve_upgrade_codes(),
        target_profile=latest_profile(),
    )
    assert f'profile="{latest_profile()}"'.encode() in result.formatted
    # The ceiling is still mentioned so the choice is informed, never silent.
    assert [n for n in result.notes if "deployment ceiling" in n]


def test_upgrade_allow_behavior_change_is_still_deployment_capped() -> None:
    """allow_behavior_change lifts the behaviour gate, not the deployment cap."""
    from galaxy_tool_refactor_registry import deployment
    from galaxy_tool_refactor_registry.resolve import resolve_upgrade_codes

    result = facade.upgrade(
        _CLEAN_LEGACY,
        codes=resolve_upgrade_codes(),
        modernize=True,
        allow_behavior_change=True,
    )
    ceiling = deployment.DEPLOYMENT_CEILING
    assert f'profile="{ceiling}"'.encode() in result.formatted
    assert result.stopped_at == ceiling


def test_upgrade_modernize_keeps_a_baseline_above_the_ceiling() -> None:
    """A tool already declared past the ceiling is never lowered to it."""
    from galaxy_tool_source.profiles import latest_profile

    from galaxy_tool_refactor_registry.resolve import resolve_upgrade_codes

    latest = latest_profile()
    tool = _CLEAN_LEGACY.replace(
        b'version="1.0.0"', f'version="1.0.0" profile="{latest}"'.encode()
    )
    result = facade.upgrade(tool, codes=resolve_upgrade_codes(), modernize=True)
    assert f'profile="{latest}"'.encode() in result.formatted
    assert result.reached_profile == latest


def test_upgrade_modernize_warns_when_the_snapshot_is_stale(
    monkeypatch: object,
) -> None:
    """An old server-poll snapshot earns a re-poll suggestion in the notes."""
    from datetime import date

    from galaxy_tool_refactor_registry import deployment
    from galaxy_tool_refactor_registry.resolve import resolve_upgrade_codes

    monkeypatch.setattr(  # type: ignore[attr-defined]
        deployment, "DEPLOYMENT_SNAPSHOT_DATE", date(2000, 1, 1)
    )
    result = facade.upgrade(
        _CLEAN_LEGACY, codes=resolve_upgrade_codes(), modernize=True
    )
    assert [n for n in result.notes if "poll_galaxy_servers" in n]


def test_upgrade_default_ignores_the_deployment_ceiling() -> None:
    """The minimal default has no walk to cap: no deployment note appears."""
    from galaxy_tool_refactor_registry.resolve import resolve_upgrade_codes

    result = facade.upgrade(_CLEAN_LEGACY, codes=resolve_upgrade_codes())
    assert not [n for n in result.notes if "deployment ceiling" in n]
    assert result.stopped_at is None


# --- reconcile_lint_skip --------------------------------------------------------

_NO_CITATIONS = (
    b'<tool id="t" name="T" version="1.0">'
    b"<command><![CDATA[echo x]]></command><inputs/>"
    b"<outputs><data name='o'/></outputs>"
    b"</tool>"
)
_CLEAN_WITH_CITES = (
    b'<tool id="t" name="T" version="1.0">'
    b"<command><![CDATA[echo x]]></command><inputs/>"
    b"<outputs><data name='o'/></outputs>"
    b"<citations><citation type='doi'>10.1/x</citation></citations>"
    b"</tool>"
)


def _doc(source: bytes):
    from galaxy_tool_source.binding import load_tool

    return load_tool(source)


def _skip(*names: str):
    from galaxy_tool_refactor_registry.lint_skip import parse_lint_skip

    return parse_lint_skip("\n".join(names) + "\n")


_REDUNDANT_NAME = (
    b'<tool id="t" name="T" version="1.0">'
    b"<command><![CDATA[echo x]]></command>"
    b'<inputs><param argument="--foo" name="foo" type="text"/></inputs>'
    b'<outputs><data name="o"/></outputs></tool>'
)


def test_reconcile_lint_skip_removes_a_fixed_line() -> None:
    """InputsNameRedundantArgument: GTR037 drops the redundant name, clearing it."""
    doc = _doc(_REDUNDANT_NAME)
    result = facade.reconcile_lint_skip([doc], _skip("InputsNameRedundantArgument"))
    assert [r.name for r in result.removed] == ["InputsNameRedundantArgument"]
    assert result.removed[0].fixed is True
    assert result.file_emptied is True
    assert result.documents[0] is not None  # the tool XML was fixed
    assert b'name="foo"' not in result.documents[0]  # redundant name dropped
    assert b"<?xml" not in result.documents[0]


def test_reconcile_lint_skip_removes_a_stale_line_without_touching_the_tool() -> None:
    """CitationsNoValid on a tool that already has citations: stale, removed, no fix."""
    doc = _doc(_CLEAN_WITH_CITES)
    result = facade.reconcile_lint_skip([doc], _skip("CitationsNoValid"))
    assert [r.name for r in result.removed] == ["CitationsNoValid"]
    assert result.removed[0].fixed is False  # already clean
    assert result.documents[0] is None  # tool left untouched
    assert result.file_emptied is True


def test_reconcile_lint_skip_keeps_a_still_firing_line_silently() -> None:
    """CitationsNoValid on a tool with no citations still fires -> keep, no report."""
    doc = _doc(_NO_CITATIONS)  # no <citations>
    result = facade.reconcile_lint_skip([doc], _skip("CitationsNoValid"))
    assert result.removed == ()
    assert result.kept_lines == ("CitationsNoValid",)
    assert result.file_emptied is False
    assert result.documents[0] is None  # nothing earned a fix


def test_reconcile_lint_skip_keeps_incompletely_covered_lines() -> None:
    """OutputsFormatInput (GTR015 only, incidental) is never removed, even if clean."""
    doc = _doc(_CLEAN_WITH_CITES)
    result = facade.reconcile_lint_skip([doc], _skip("OutputsFormatInput"))
    assert result.removed == ()
    assert result.kept_lines == ("OutputsFormatInput",)


def test_reconcile_lint_skip_preserves_comments_and_unremoved_names() -> None:
    """A removed line drops out; comments and kept names stay verbatim."""
    doc = _doc(_CLEAN_WITH_CITES)  # citations present -> CitationsNoValid stale
    lines = _skip("# author note", "CitationsNoValid", "TestsCaseValidation")
    result = facade.reconcile_lint_skip([doc], lines)
    assert [r.name for r in result.removed] == ["CitationsNoValid"]
    # The comment and the uncovered TestsCaseValidation line are preserved.
    assert result.kept_lines == ("# author note", "TestsCaseValidation")
    assert result.file_emptied is False


def test_reconcile_lint_skip_requires_all_dir_tools_clear() -> None:
    """A line is removed only if clear on every tool the .lint_skip governs."""
    has_cites = _doc(_CLEAN_WITH_CITES)
    no_cites = _doc(_NO_CITATIONS)  # no citations -> CitationsNoValid still fires here
    result = facade.reconcile_lint_skip(
        [has_cites, no_cites], _skip("CitationsNoValid")
    )
    assert result.removed == ()  # one tool still trips it -> keep for the dir


_RAGGED = b"""<tool id="t" name="T" version="1.0" profile="24.0">
  <description>desc</description>
        <command><![CDATA[echo x]]></command>
  <inputs>
    <param name="a" type="text"/>
  </inputs>
  <outputs>
        <data name="out" format="txt"/>
  </outputs>
</tool>
"""


def test_is_canonical_and_fired_codes_agree_with_run() -> None:
    from galaxy_tool_refactor_registry.gate_eligibility import gate_codes

    codes = gate_codes()
    # The ragged-indentation tool is non-canonical (GTR001 fires).
    assert not facade.is_canonical(_RAGGED, codes=codes)
    fired = facade.fired_codes(_RAGGED, codes=codes)
    assert "GTR001" in fired
    # After format over the same codes, nothing fires — canonical, and the two
    # primitives agree (fired empty <=> is_canonical True).
    canonical = facade.run(_RAGGED, codes=codes).formatted
    assert facade.fired_codes(canonical, codes=codes) == set()
    assert facade.is_canonical(canonical, codes=codes)


def test_minimal_note_token_profile_defers_not_kept() -> None:
    # Issue #262: a token profile (@PROFILE@) must NOT be narrated as "kept /
    # validates at its declared profile" — the token carries the real decision.
    from galaxy_tool_refactor_registry.facade import _minimal_outcome_note

    note = _minimal_outcome_note(
        declared="@PROFILE@", baseline="21.05", reached="21.05", unreachable=None
    )
    assert note is not None
    assert "macro token" in note and "@PROFILE@" in note
    assert "validates at its declared profile" not in note


def test_minimal_note_numeric_profile_still_says_kept() -> None:
    # A real (non-token) profile is unchanged: it still reports the kept message.
    from galaxy_tool_refactor_registry.facade import _minimal_outcome_note

    note = _minimal_outcome_note(
        declared="24.0", baseline="24.0", reached="24.0", unreachable=None
    )
    assert note is not None and "24.0 kept" in note
    assert "validates at its declared profile" in note


# --- the opt-in consider-blocking gate (block_consider, D28) ------------------------


def test_upgrade_block_consider_alone_is_a_typed_error() -> None:
    """block_consider tightens the walk's gate, so it needs a walk mode too."""
    import pytest

    from galaxy_tool_refactor_registry.errors import UpgradeFlagError
    from galaxy_tool_refactor_registry.resolve import resolve_upgrade_codes

    with pytest.raises(UpgradeFlagError):
        facade.upgrade(_UPGRADABLE, codes=resolve_upgrade_codes(), block_consider=True)


def test_upgrade_block_consider_conflicts_with_allow_behavior_change() -> None:
    """Tightening and lifting the gate at once has no coherent meaning."""
    import pytest

    from galaxy_tool_refactor_registry.errors import UpgradeFlagConflict
    from galaxy_tool_refactor_registry.resolve import resolve_upgrade_codes

    with pytest.raises(UpgradeFlagConflict):
        facade.upgrade(
            _UPGRADABLE,
            codes=resolve_upgrade_codes(),
            modernize=True,
            allow_behavior_change=True,
            block_consider=True,
        )


_NO_PROFILE_SIMPLE = (
    b'<tool id="m" name="M" version="1.0.0">'
    b"<command><![CDATA[echo a && echo b]]></command><inputs/>"
    b'<outputs><data name="o"/></outputs></tool>'
)


def test_upgrade_modernize_block_consider_stops_at_a_consider_boundary() -> None:
    """Galaxy's 16_04 implicit-extra-file-collection consider code applies to every
    tool, so the strict gate freezes a 16.01-baseline walk below the oldest vendored
    profile: profile= stays undeclared and the stop note names the code + the
    flag-specific opt-out."""
    from galaxy_tool_refactor_registry.resolve import resolve_upgrade_codes

    result = facade.upgrade(
        _NO_PROFILE_SIMPLE,
        codes=resolve_upgrade_codes(),
        modernize=True,
        block_consider=True,
    )
    assert "16_04_consider_implicit_extra_file_collection" in result.blocking_codes
    assert b"profile=" not in result.formatted  # the walk did not run
    stop_notes = [n for n in result.notes if "left profile= unchanged" in n]
    assert len(stop_notes) == 1
    assert "16_04_consider_implicit_extra_file_collection" in stop_notes[0]
    assert "--block-consider" in stop_notes[0]
    assert "--allow-behavior-change" in stop_notes[0]


def test_upgrade_modernize_default_still_walks_past_consider_codes() -> None:
    """The control: without block_consider the same tool walks (consider codes
    warn, never stop) and no consider code appears in the blocking set."""
    from galaxy_tool_refactor_registry.resolve import resolve_upgrade_codes

    result = facade.upgrade(
        _NO_PROFILE_SIMPLE, codes=resolve_upgrade_codes(), modernize=True
    )
    assert (
        "16_04_consider_implicit_extra_file_collection" not in result.blocking_codes
    )
    assert b'profile="' in result.formatted  # the walk declared a profile
