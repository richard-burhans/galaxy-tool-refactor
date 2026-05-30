"""Shared fixtures + sample tool sources for the registry tests."""

from __future__ import annotations

import pytest

# A valid tool with out-of-order <param> attributes and a flat layout, so the
# fixable rules (param reorder + cosmetic whitespace) all fire, and which lacks
# tests / requirements / help so several advisory IUC checks fire too.
_SAMPLE = (
    b'<tool id="t" name="T" version="0.1" profile="24.1">'
    b"<command><![CDATA[echo x]]></command>"
    b'<inputs><param value="v" type="text" name="a"/></inputs>'
    b'<outputs><data name="o"/></outputs></tool>'
)


@pytest.fixture
def sample_bytes() -> bytes:
    """Raw XML bytes for a non-canonical, advisory-incomplete valid tool."""
    return _SAMPLE
