"""Tests for near-miss typo suggestions."""

from pathlib import Path

from galaxy_tool_source.corrections import suggest_corrections


def test_typos_detected_for_all_kinds(data_dir: Path) -> None:
    corrections = suggest_corrections(data_dir / "tool_with_typos.xml")
    kinds = {correction.kind for correction in corrections}
    assert kinds == {"attribute", "element", "enum_value"}


def test_typo_suggestions_point_at_correct_spelling(data_dir: Path) -> None:
    corrections = suggest_corrections(data_dir / "tool_with_typos.xml")
    suggested = {correction.suggested for correction in corrections}
    assert {"optional", "description", "data_source"} <= suggested


def test_clean_tool_yields_no_corrections(data_dir: Path) -> None:
    assert suggest_corrections(data_dir / "minimal_tool.xml") == []


def test_genuinely_unknown_name_yields_no_correction() -> None:
    xml = b'<tool id="t" name="T" version="1.0.0" profile="26.0"><zzzzzzzzzz/></tool>'
    corrections = suggest_corrections(xml)
    assert all(correction.kind != "element" for correction in corrections)


def test_macro_constructs_not_flagged(data_dir: Path) -> None:
    corrections = suggest_corrections(data_dir / "tool_with_macros.xml")
    assert corrections == []


def test_correction_str_is_a_did_you_mean_line(data_dir: Path) -> None:
    corrections = suggest_corrections(data_dir / "tool_with_typos.xml")
    assert all("did you mean" in str(correction) for correction in corrections)


def test_corrections_use_the_declared_profile() -> None:
    """A near-miss of a 26.0-only element is flagged only under a 26.0 profile."""
    child = b"<entry_pointx/>"
    head = b'<tool id="t" name="T" version="1.0.0" profile='
    recent = head + b'"26.0">' + child + b"</tool>"
    old = head + b'"16.10">' + child + b"</tool>"
    assert "entry_points" in {c.suggested for c in suggest_corrections(recent)}
    assert "entry_points" not in {c.suggested for c in suggest_corrections(old)}


def test_profile_override_uses_overridden_vocabulary() -> None:
    """An explicit ``profile`` overrides the tool's declared profile vocabulary."""
    child = b"<entry_pointx/>"
    head = b'<tool id="t" name="T" version="1.0.0" profile="16.10">'
    tool = head + child + b"</tool>"
    # Under the tool's own (16.10) profile, ``entry_points`` is not vocabulary.
    assert "entry_points" not in {c.suggested for c in suggest_corrections(tool)}
    # Overriding to 26.0 brings ``entry_points`` into scope so the near-miss flags.
    assert "entry_points" in {
        c.suggested for c in suggest_corrections(tool, profile="26.0")
    }


def test_profile_none_matches_declared_profile() -> None:
    """``profile=None`` preserves today's behaviour: use the tool's own profile."""
    child = b"<entry_pointx/>"
    tool = b'<tool id="t" name="T" version="1.0.0" profile="26.0">' + child + b"</tool>"
    assert suggest_corrections(tool) == suggest_corrections(tool, profile=None)
    assert "entry_points" in {
        c.suggested for c in suggest_corrections(tool, profile=None)
    }
