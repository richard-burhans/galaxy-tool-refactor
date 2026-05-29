"""Tests for the M3 ``CodemodCommand`` base class and visitor dispatch."""

from __future__ import annotations

from pathlib import Path

from galaxy_tool_xml.binding import load_tool

from galaxy_tool_xml_codemod.codemod import CodemodCommand
from galaxy_tool_xml_codemod.codemods.fix_typos import FixTypos
from galaxy_tool_xml_codemod.cursor import Cursor
from galaxy_tool_xml_codemod.eligibility import corpus_test_profile
from galaxy_tool_xml_codemod.parse import parse_module


def test_visit_tool_is_called_on_root(minimal_tool_path: Path) -> None:
    """A codemod's ``visit_Tool`` method runs on the root ``<tool>`` element."""
    seen: list[str] = []

    class RecordRoot(CodemodCommand):
        def visit_Tool(self, cursor: Cursor) -> None:
            seen.append(cursor.tag)

    module = parse_module(minimal_tool_path)
    RecordRoot().apply(module)
    assert seen == ["tool"]


def test_visit_param_is_called_for_every_param(
    tool_with_params_path: Path,
) -> None:
    """``visit_Param`` runs once per ``<param>`` element regardless of depth."""
    seen: list[str | None] = []

    class RecordParams(CodemodCommand):
        def visit_Param(self, cursor: Cursor) -> None:
            seen.append(cursor.get_attribute("name"))

    module = parse_module(tool_with_params_path)
    RecordParams().apply(module)
    assert seen == ["input1", "input2", "choice"]


def test_mutations_via_cursor_persist(minimal_tool_path: Path) -> None:
    """Mutations performed in ``visit_X`` are visible on the module afterwards."""

    class StampHidden(CodemodCommand):
        def visit_Tool(self, cursor: Cursor) -> None:
            cursor.set_attribute("hidden", "true")

    module = parse_module(minimal_tool_path)
    StampHidden().apply(module)
    assert module.cursor.get_attribute("hidden") == "true"


def test_returning_false_stops_descent(tool_with_params_path: Path) -> None:
    """A ``visit_X`` that returns ``False`` halts traversal into its subtree."""
    seen: list[str] = []

    class SkipInputsSubtree(CodemodCommand):
        def visit_Inputs(self, cursor: Cursor) -> bool:
            seen.append("inputs")
            return False

        def visit_Param(self, cursor: Cursor) -> None:
            seen.append("param")

    module = parse_module(tool_with_params_path)
    SkipInputsSubtree().apply(module)
    assert seen == ["inputs"]


def test_returning_none_descends(tool_with_params_path: Path) -> None:
    """Returning ``None`` (the default) lets traversal descend into children."""
    seen: list[str] = []

    class WatchInputs(CodemodCommand):
        def visit_Inputs(self, cursor: Cursor) -> None:
            seen.append("inputs")

        def visit_Param(self, cursor: Cursor) -> None:
            seen.append("param")

    module = parse_module(tool_with_params_path)
    WatchInputs().apply(module)
    assert seen == ["inputs", "param", "param", "param"]


def test_traversal_handles_snake_case_tags(tool_with_params_path: Path) -> None:
    """Snake-case tags dispatch to PascalCase visitors.

    e.g. ``<change_format>`` would dispatch to ``visit_ChangeFormat``. The
    fixture has no ``<change_format>``, so verify the convention with
    ``<conditional>`` (single word) → ``visit_Conditional``.
    """
    seen: list[str] = []

    class RecordConditional(CodemodCommand):
        def visit_Conditional(self, cursor: Cursor) -> None:
            seen.append(cursor.tag)

    module = parse_module(tool_with_params_path)
    RecordConditional().apply(module)
    assert seen == ["conditional"]


def test_traversal_visits_in_document_order(tool_with_params_path: Path) -> None:
    """The walk is pre-order: parent before children, siblings left-to-right."""
    visited: list[str] = []

    class RecordAll(CodemodCommand):
        def visit_Tool(self, cursor: Cursor) -> None:
            visited.append(cursor.tag)

        def visit_Inputs(self, cursor: Cursor) -> None:
            visited.append(cursor.tag)

        def visit_Outputs(self, cursor: Cursor) -> None:
            visited.append(cursor.tag)

        def visit_Conditional(self, cursor: Cursor) -> None:
            visited.append(cursor.tag)

        def visit_Param(self, cursor: Cursor) -> None:
            visited.append(cursor.tag)

        def visit_Data(self, cursor: Cursor) -> None:
            visited.append(cursor.tag)

        def visit_Command(self, cursor: Cursor) -> None:
            visited.append(cursor.tag)

        def visit_Option(self, cursor: Cursor) -> None:
            visited.append(cursor.tag)

    module = parse_module(tool_with_params_path)
    RecordAll().apply(module)
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
