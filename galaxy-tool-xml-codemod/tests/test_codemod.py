"""Tests for the ``CodemodCommand`` base class and detect-dispatch harness."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from galaxy_tool_source.binding import load_tool

from galaxy_tool_xml_codemod.change import Change
from galaxy_tool_xml_codemod.codemod import CodemodCommand
from galaxy_tool_xml_codemod.codemods.fix_typos import FixTypos
from galaxy_tool_xml_codemod.cursor import Cursor
from galaxy_tool_xml_codemod.eligibility import corpus_test_profile
from galaxy_tool_xml_codemod.parse import parse_module


def test_detect_tool_is_called_on_root(minimal_tool_path: Path) -> None:
    """A codemod's ``detect_Tool`` method runs on the root ``<tool>`` element."""
    seen: list[str] = []

    class RecordRoot(CodemodCommand):
        def detect_Tool(self, cursor: Cursor) -> Iterable[Change]:
            seen.append(cursor.tag)
            return ()

    module = parse_module(minimal_tool_path)
    list(RecordRoot().detect(module))
    assert seen == ["tool"]


def test_detect_param_is_called_for_every_param(
    tool_with_params_path: Path,
) -> None:
    """``detect_Param`` runs once per ``<param>`` element regardless of depth."""
    seen: list[str | None] = []

    class RecordParams(CodemodCommand):
        def detect_Param(self, cursor: Cursor) -> Iterable[Change]:
            seen.append(cursor.get_attribute("name"))
            return ()

    module = parse_module(tool_with_params_path)
    list(RecordParams().detect(module))
    assert seen == ["input1", "input2", "choice"]


def test_detect_is_non_mutating(minimal_tool_path: Path) -> None:
    """``detect`` never mutates — the change's thunk only fires under ``apply``."""

    class StampHidden(CodemodCommand):
        def detect_Tool(self, cursor: Cursor) -> Iterable[Change]:
            yield Change(
                code="GTR000",
                sourceline=cursor.sourceline,
                xpath=cursor.xpath,
                message="would stamp hidden",
                mutate=lambda: cursor.set_attribute("hidden", "true"),
            )

    module = parse_module(minimal_tool_path)
    list(StampHidden().detect(module))
    assert module.cursor.get_attribute("hidden") is None


def test_apply_runs_detected_change_thunks(minimal_tool_path: Path) -> None:
    """``apply`` materialises ``detect`` and fires each change's thunk."""

    class StampHidden(CodemodCommand):
        def detect_Tool(self, cursor: Cursor) -> Iterable[Change]:
            yield Change(
                code="GTR000",
                sourceline=cursor.sourceline,
                xpath=cursor.xpath,
                message="would stamp hidden",
                mutate=lambda: cursor.set_attribute("hidden", "true"),
            )

    module = parse_module(minimal_tool_path)
    StampHidden().apply(module)
    assert module.cursor.get_attribute("hidden") == "true"


def test_detect_descends_into_children(tool_with_params_path: Path) -> None:
    """The walk descends into a matched element's subtree."""
    seen: list[str] = []

    class WatchInputs(CodemodCommand):
        def detect_Inputs(self, cursor: Cursor) -> Iterable[Change]:
            seen.append("inputs")
            return ()

        def detect_Param(self, cursor: Cursor) -> Iterable[Change]:
            seen.append("param")
            return ()

    module = parse_module(tool_with_params_path)
    list(WatchInputs().detect(module))
    assert seen == ["inputs", "param", "param", "param"]


def test_traversal_handles_snake_case_tags(tool_with_params_path: Path) -> None:
    """Snake-case tags dispatch to PascalCase detectors.

    e.g. ``<change_format>`` would dispatch to ``detect_ChangeFormat``. The
    fixture has no ``<change_format>``, so verify the convention with
    ``<conditional>`` (single word) → ``detect_Conditional``.
    """
    seen: list[str] = []

    class RecordConditional(CodemodCommand):
        def detect_Conditional(self, cursor: Cursor) -> Iterable[Change]:
            seen.append(cursor.tag)
            return ()

    module = parse_module(tool_with_params_path)
    list(RecordConditional().detect(module))
    assert seen == ["conditional"]


def test_traversal_visits_in_document_order(tool_with_params_path: Path) -> None:
    """The walk is pre-order: parent before children, siblings left-to-right."""
    visited: list[str] = []

    class RecordAll(CodemodCommand):
        def _record(self, cursor: Cursor) -> Iterable[Change]:
            visited.append(cursor.tag)
            return ()

        detect_Tool = _record
        detect_Inputs = _record
        detect_Outputs = _record
        detect_Conditional = _record
        detect_Param = _record
        detect_Data = _record
        detect_Command = _record
        detect_Option = _record

    module = parse_module(tool_with_params_path)
    list(RecordAll().detect(module))
    assert visited == [
        "tool",
        "command",
        "inputs",
        "param",
        "param",
        "conditional",
        "param",
        "option",
        "option",
        "outputs",
        "data",
    ]


# ---------------------------------------------------------------------------
# Corpus-sweep eligibility hooks
# ---------------------------------------------------------------------------

_INVALID = (
    b'<tool id="m" name="M" version="1.0.0" profile="24.0">'
    b"<command><![CDATA[echo x]]></command>"
    b'<inputs><param name="x" typ="text"/></inputs><outputs/></tool>'
)


def test_default_corpus_eligible_mirrors_corpus_test_profile(
    minimal_tool_path: Path,
) -> None:
    """The base hook is eligible exactly when the sweep policy picks a profile."""
    document = load_tool(minimal_tool_path)
    assert CodemodCommand.corpus_eligible(document) is (
        corpus_test_profile(document) is not None
    )


def test_default_corpus_validation_profile_mirrors_policy(
    minimal_tool_path: Path,
) -> None:
    """The base validation profile defaults to the sweep policy's choice."""
    document = load_tool(minimal_tool_path)
    assert (
        CodemodCommand.corpus_validation_profile(document)
        == corpus_test_profile(document)
    )


def test_fix_typos_eligible_only_for_globally_invalid_tools(
    minimal_tool_path: Path,
) -> None:
    """``FixTypos`` inverts eligibility: in scope iff nothing validates."""
    assert FixTypos.corpus_eligible(load_tool(_INVALID)) is True
    assert FixTypos.corpus_eligible(load_tool(minimal_tool_path)) is False


def test_base_upgrade_steps_applied_is_empty() -> None:
    """A non-orchestrator codemod reports no upgrade steps."""
    assert FixTypos().upgrade_steps_applied() == ()


def test_fix_typos_validation_profile_tracks_repair() -> None:
    """Validation profile is ``None`` pre-repair, the stopped-at version after."""
    module = parse_module(_INVALID)
    assert FixTypos.corpus_validation_profile(module.document) is None
    FixTypos().apply(module)
    assert FixTypos.corpus_validation_profile(module.document) is not None
