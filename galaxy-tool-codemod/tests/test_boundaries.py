"""Tests for the per-boundary reference renderer (``boundaries.py``).

The rendered block is the generated half of ``docs/profile_boundaries.md`` — the
user-facing "my upgrade stopped, now what" reference the stop note points at.
Derived entirely from ``PROFILE_UPGRADE_CODES`` plus the auto-fix registry, so
it cannot drift from the shipped gate; a freshness test in the registry tier
pins the committed doc to this output.
"""

from __future__ import annotations

from galaxy_tool_codemod.behavior_gate import auto_fixes_by_code
from galaxy_tool_codemod.boundaries import (
    BEGIN_MARKER,
    END_MARKER,
    render_boundary_reference,
)
from galaxy_tool_codemod.profile_semantics import PROFILE_UPGRADE_CODES


def test_markers_name_the_generator() -> None:
    assert "gen_profile_boundaries" in BEGIN_MARKER
    assert "gen_profile_boundaries" in END_MARKER


def test_every_catalogue_code_gets_a_section() -> None:
    rendered = render_boundary_reference()
    for change in PROFILE_UPGRADE_CODES:
        assert f"`{change.code}`" in rendered
        assert change.message.split(".")[0][:40] in rendered  # the verbatim text


def test_every_profile_boundary_gets_a_heading() -> None:
    rendered = render_boundary_reference()
    for profile in {change.profile for change in PROFILE_UPGRADE_CODES}:
        assert f"## Profile {profile}" in rendered


def test_auto_fixed_codes_name_their_codemod() -> None:
    rendered = render_boundary_reference()
    for code, fix in auto_fixes_by_code().items():
        section = rendered.partition(f"`{code}`")[2].partition("###")[0]
        assert fix.meta.code in section  # e.g. GTR016 next to 16_04_fix_interpreter


def test_unfixable_must_fix_codes_describe_the_stop() -> None:
    rendered = render_boundary_reference()
    section = rendered.partition("`24_2_fix_test_case_validation`")[2].partition(
        "###"
    )[0]
    assert "stops" in section
    assert "--allow-behavior-change" in section


def test_consider_codes_describe_the_warning() -> None:
    rendered = render_boundary_reference()
    section = rendered.partition("`20_09_consider_set_e`")[2].partition("###")[0]
    assert "does not stop" in section


def test_release_urls_are_linked() -> None:
    rendered = render_boundary_reference()
    linked = [change for change in PROFILE_UPGRADE_CODES if change.url is not None]
    assert linked
    for change in linked[:3]:
        assert change.url in rendered
