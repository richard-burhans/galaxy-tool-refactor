"""Tests for ``TrimAttributeWhitespace`` (GTR035).

Trims accidental leading/trailing whitespace from the **behaviour-preserving** subset
of identity-ish attributes — a `<tool>`'s ``name`` (display only) and a
``<requirement>``'s ``version`` (a whitespace value breaks the conda solve, so a
*working* tool never has it; trimming only ever repairs a broken one). A `<tool>`'s
``id`` and ``version`` are deliberately **not** trimmed: Galaxy uses them raw as the
tool's identity / version key, so trimming would change a working tool's identity —
those are left for the advisory check. Reimplements planemo's `ToolNameWhitespace` /
`RequirementVersionWhitespace` as a fixer (planemo only reports).
"""

from __future__ import annotations

from lxml import etree

from galaxy_tool_xml_codemod.codemods.trim_attribute_whitespace import (
    TrimAttributeWhitespace,
)
from galaxy_tool_xml_codemod.parse import parse_module


def test_trims_tool_name_whitespace() -> None:
    module = parse_module(
        b'<tool id="m" name="My Tool " version="1.0"><inputs/></tool>'
    )
    changes = list(TrimAttributeWhitespace().detect(module))
    assert len(changes) == 1 and changes[0].code == "GTR035"
    TrimAttributeWhitespace().apply(module)
    assert module.document.root.get("name") == "My Tool"


def test_trims_requirement_version_whitespace() -> None:
    module = parse_module(
        b'<tool id="m" name="M" version="1.0"><requirements>'
        b'<requirement type="package" version=" 1.0 ">samtools</requirement>'
        b"</requirements><inputs/></tool>"
    )
    TrimAttributeWhitespace().apply(module)
    req = module.document.root.find("requirements/requirement")
    assert req is not None
    assert req.get("version") == "1.0"
    assert req.text == "samtools"  # element text untouched


def test_does_not_trim_tool_id_or_version() -> None:
    # id / version are identity-significant — Galaxy uses them raw as the tool's
    # identity and version key (tool_util/parser/xml.py parse_id/parse_version do not
    # strip), so trimming would change a working tool's identity. Left for the advisory
    # check, NOT auto-fixed (behaviour-preservation discipline).
    module = parse_module(b'<tool id="m " name="M" version="1.0 "><inputs/></tool>')
    assert list(TrimAttributeWhitespace().detect(module)) == []
    before = etree.tostring(module.document.root)
    TrimAttributeWhitespace().apply(module)
    assert etree.tostring(module.document.root) == before


def test_noop_on_clean_attributes() -> None:
    module = parse_module(
        b'<tool id="m" name="M" version="1.0"><requirements>'
        b'<requirement version="1.0">x</requirement>'
        b"</requirements><inputs/></tool>"
    )
    assert list(TrimAttributeWhitespace().detect(module)) == []


def test_is_idempotent() -> None:
    module = parse_module(b'<tool id="m" name=" M " version="1.0"><inputs/></tool>')
    TrimAttributeWhitespace().apply(module)
    once = etree.tostring(module.document.root)
    TrimAttributeWhitespace().apply(module)
    assert etree.tostring(module.document.root) == once
