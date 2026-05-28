"""Framework tests: all_rules(), apply_edits dispatch, format pipeline."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import ClassVar

import pytest
from galaxy_tool_xml.document import ToolDocument
from lxml import etree

from galaxy_tool_xml_fmt.edits import Edit, NoOp, apply_edits
from galaxy_tool_xml_fmt.format import all_rules, format_tool_document
from galaxy_tool_xml_fmt.rule_blank_line import BlankLineBetweenSections
from galaxy_tool_xml_fmt.rule_empty_element import EmptyElementShorthand
from galaxy_tool_xml_fmt.rule_indent import CanonicalIndent
from galaxy_tool_xml_fmt.rule_param_attr_order import ParamAttributeOrder
from galaxy_tool_xml_fmt.rule_tool_attr_order import ToolAttributeOrder
from galaxy_tool_xml_fmt.rules import Rule, RuleMeta

_TINY_TOOL = b"""<?xml version='1.0' encoding='UTF-8'?>
<tool id="t" name="T" version="0.1.0">
  <command><![CDATA[echo hi]]></command>
</tool>
"""

_EXPECTED_RULES: frozenset[type[Rule]] = frozenset({
    BlankLineBetweenSections,
    EmptyElementShorthand,
    CanonicalIndent,
    ParamAttributeOrder,
    ToolAttributeOrder,
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
    import galaxy_tool_xml_fmt.format as fmt_module

    monkeypatch.setattr(fmt_module, "all_rules", lambda: ())
    parser = etree.XMLParser(strip_cdata=False)
    doc = make_doc(_TINY_TOOL)
    output = format_tool_document(doc)
    reparsed = etree.fromstring(output, parser=parser)
    assert etree.tostring(reparsed) == etree.tostring(doc.tree.getroot())
