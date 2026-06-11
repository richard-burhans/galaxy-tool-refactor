"""Framework tests: all_rules(), apply_edits dispatch, format pipeline."""

from __future__ import annotations

from collections.abc import Callable

import pytest
from galaxy_tool_source.document import ToolDocument
from lxml import etree

from galaxy_tool_fmt.edits import NoOp, apply_edits
from galaxy_tool_fmt.format import all_rules, format_tool_document
from galaxy_tool_fmt.rule_blank_line import BlankLineBetweenSections
from galaxy_tool_fmt.rule_empty_element import EmptyElementShorthand
from galaxy_tool_fmt.rule_indent import CanonicalIndent
from galaxy_tool_fmt.rules import Rule

_TINY_TOOL = b"""<?xml version='1.0' encoding='UTF-8'?>
<tool id="t" name="T" version="0.1.0">
  <command><![CDATA[echo hi]]></command>
</tool>
"""

_EXPECTED_RULES: frozenset[type[Rule]] = frozenset({
    BlankLineBetweenSections,
    EmptyElementShorthand,
    CanonicalIndent,
})


def test_all_rules_returns_expected_rule_classes() -> None:
    result = all_rules()
    assert isinstance(result, tuple)
    assert frozenset(result) == _EXPECTED_RULES


def test_all_rules_is_sorted_by_order() -> None:
    result = all_rules()
    orders = [cls.meta.order for cls in result]
    assert orders == sorted(orders)


def test_apply_edits_dispatches_noop_without_changing_tree(
    make_doc: Callable[[bytes], ToolDocument],
) -> None:
    doc = make_doc(_TINY_TOOL)
    before = etree.tostring(doc.tree)
    apply_edits([NoOp()])
    after = etree.tostring(doc.tree)
    assert before == after


def test_format_tool_document_is_identity_with_empty_rules(
    monkeypatch: pytest.MonkeyPatch,
    make_doc: Callable[[bytes], ToolDocument],
) -> None:
    """No cosmetic rules → format_tool_document is identity (modulo serialisation)."""
    import galaxy_tool_fmt.format as fmt_module

    monkeypatch.setattr(fmt_module, "all_rules", lambda: ())
    parser = etree.XMLParser(strip_cdata=False)
    doc = make_doc(_TINY_TOOL)
    output = format_tool_document(doc)
    reparsed = etree.fromstring(output, parser=parser)
    assert etree.tostring(reparsed) == etree.tostring(doc.tree.getroot())


def test_format_tool_document_does_not_import_codemod_package(
    make_doc: Callable[[bytes], ToolDocument],
) -> None:
    """The fmt library function must not import galaxy-tool-codemod.

    Tier separation: fmt's library is cosmetic-only; codemod is an
    optional dependency consumed only by fmt's CLI. A user with just
    ``xml + fmt`` installed must be able to call ``format_tool_document``
    without ImportError.
    """
    import importlib
    import sys

    # Force re-import of fmt's format module from a clean state, then
    # verify codemod is not loaded as a side effect.
    for module_name in list(sys.modules):
        if module_name.startswith("galaxy_tool_codemod"):
            del sys.modules[module_name]
    import galaxy_tool_fmt.format as fmt_module

    importlib.reload(fmt_module)
    fmt_module.format_tool_document(make_doc(_TINY_TOOL))
    assert not any(
        name.startswith("galaxy_tool_codemod") for name in sys.modules
    )


_STRUCTURED_TOOL = b"""<?xml version='1.0' encoding='UTF-8'?>
<tool id="t" name="T" version="0.1.0" profile="21.09">
    <description>desc</description>
    <requirements>
        <requirement type="package" version="1.0">alpha</requirement>
        <requirement type="package" version="2.0">beta</requirement>
    </requirements>
    <command detect_errors="exit_code"><![CDATA[echo hi]]></command>
    <inputs>
        <param name="a" type="select" label="A">
            <option value="x">X</option>
            <option value="y" selected="true">Y</option>
        </param>
    </inputs>
    <outputs>
        <data name="out" format="txt"></data>
    </outputs>
    <help>help text</help>
</tool>
"""


def test_format_preserves_structure_and_attributes(
    make_doc: Callable[[bytes], ToolDocument],
) -> None:
    """Property: cosmetic formatting is structure-preserving.

    The ``Edit`` union can only set ``.text`` / ``.tail`` (whitespace trivia) or
    clear a whitespace-only ``.text`` — it cannot rename a tag, reorder children,
    or touch attributes. So formatting must leave the document-ordered element
    sequence, every element's tag, and its attributes (names, values, *order*)
    identical; only inter-element whitespace and empty-element shorthand may
    change. This pins that contract so a future cosmetic rule that edits structure
    fails loudly rather than silently exceeding fmt's remit (audit N3).
    """
    formatted = format_tool_document(make_doc(_STRUCTURED_TOOL))

    parser = etree.XMLParser(strip_cdata=False)
    before = list(etree.fromstring(_STRUCTURED_TOOL, parser=parser).iter())
    after = list(etree.fromstring(formatted, parser=parser).iter())

    assert len(after) == len(before)
    for original, result in zip(before, after, strict=True):
        assert result.tag == original.tag
        assert list(result.attrib.items()) == list(original.attrib.items())
        assert (result.text or "").strip() == (original.text or "").strip()
