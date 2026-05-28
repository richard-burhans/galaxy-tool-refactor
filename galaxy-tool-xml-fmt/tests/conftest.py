"""Shared pytest fixtures."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest
from galaxy_tool_xml.document import ToolDocument
from lxml import etree


@pytest.fixture
def make_doc() -> Callable[[bytes], ToolDocument]:
    """Build a ``ToolDocument`` from raw XML bytes with CDATA preserved.

    Hand-rolling this in every test file produced the same five-line
    helper eight times. The fixture returns a callable rather than a
    pre-built document because most tests build several documents per
    test from different payloads.
    """

    def _build(payload: bytes) -> ToolDocument:
        parser = etree.XMLParser(strip_cdata=False)
        root = etree.fromstring(payload, parser=parser)
        return ToolDocument(etree.ElementTree(root))

    return _build
