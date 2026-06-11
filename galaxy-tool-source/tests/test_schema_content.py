"""Tests for the schema-derived text-bearing element set."""

from __future__ import annotations

from galaxy_tool_source.schema_content import text_bearing_tags


def test_known_payload_elements_are_text_bearing() -> None:
    tags = text_bearing_tags()
    # The hand-maintained guard lists (fmt GTR004 denylist / GTR001 payload set)
    # must be a subset of the derivation — these are the proven-payload tags.
    assert {"command", "configfile", "token", "help"} <= tags


def test_schema_surfaces_text_bearing_elements_the_hand_lists_missed() -> None:
    tags = text_bearing_tags()
    # The derivation's point: option labels, eval'd filter text, description,
    # version_command are all text content by schema.
    assert {"option", "filter", "description", "version_command"} <= tags


def test_structural_elements_are_not_text_bearing() -> None:
    tags = text_bearing_tags()
    assert not {"outputs", "tool", "conditional", "repeat", "tests"} & tags


def test_name_collision_and_legacy_tags_are_honestly_included() -> None:
    # The derivation is name-keyed and conservative: <inputs> IS text-bearing
    # (simpleContent under <configfiles> — ConfigInputs), and <macros> is
    # xs:anyType in the legacy schemas. The CONTEXT handling (configfiles-only
    # for inputs; the cleared-macros exception) lives in the fmt consumer
    # (galaxy_tool_fmt.payload), not here — this module reports the schema
    # truth.
    tags = text_bearing_tags()
    assert {"inputs", "macros"} <= tags


def test_result_is_cached_and_frozen() -> None:
    first = text_bearing_tags()
    assert first is text_bearing_tags()  # @cache
    assert isinstance(first, frozenset)
