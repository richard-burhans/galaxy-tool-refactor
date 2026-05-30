"""Tests for coarse detection on the validation-driven codemods."""

from __future__ import annotations

from pathlib import Path

from galaxy_tool_xml_codemod.change import apply_changes
from galaxy_tool_xml_codemod.codemods.fix_typos import FixTypos
from galaxy_tool_xml_codemod.codemods.update_profile import UpdateProfile
from galaxy_tool_xml_codemod.parse import parse_module

# A tool with a single attribute typo (``typ=`` for ``type=``) that validates at
# no profile until repaired — ``FixTypos``'s population.
_TYPO = (
    b'<tool id="m" name="M" version="1.0.0" profile="24.0">'
    b"<command><![CDATA[echo x]]></command>"
    b'<inputs><param name="x" typ="text"/></inputs><outputs/></tool>'
)


def test_coarse_detect_yields_one_root_change_when_apply_would_change() -> None:
    """``FixTypos.detect`` reports a single change at the root for a repairable tool."""
    module = parse_module(_TYPO)
    changes = list(FixTypos().detect(module))
    assert len(changes) == 1
    assert changes[0].code == "GTX006"
    assert changes[0].xpath == "/tool"
    # Coarse detect is non-mutating: the typo survives until apply runs.
    assert next(module.document.root.iter("param")).get("typ") == "text"


def test_coarse_detect_yields_nothing_when_apply_is_a_noop(
    minimal_tool_path: Path,
) -> None:
    """An already-valid tool gives ``FixTypos`` nothing to repair."""
    module = parse_module(minimal_tool_path)
    assert list(FixTypos().detect(module)) == []


def test_coarse_detect_change_thunk_performs_the_real_fix() -> None:
    """Applying the detected change repairs the typo on the real module."""
    module = parse_module(_TYPO)
    apply_changes(list(FixTypos().detect(module)))
    param = next(module.document.root.iter("param"))
    assert param.get("typ") is None
    assert param.get("type") == "text"


def test_update_profile_coarse_detect_reports_a_missing_profile() -> None:
    """``UpdateProfile.detect`` flags a tool whose ``profile=`` would be set."""
    no_profile = (
        b'<tool id="m" name="M" version="1.0.0">'
        b"<command><![CDATA[echo x]]></command>"
        b'<inputs><param name="x" type="text"/></inputs><outputs/></tool>'
    )
    module = parse_module(no_profile)
    changes = list(UpdateProfile().detect(module))
    assert len(changes) == 1
    assert changes[0].code == "GTX007"
    # Non-mutating until applied.
    assert module.document.root.get("profile") is None
