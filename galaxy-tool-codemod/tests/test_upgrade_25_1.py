"""Tests for the ``Upgrade25_1`` codemod (single-step 25.1 -> 26.0).

26.0 dropped the obsolete top-level ``<trackster_conf>`` element (Trackster
visualization config). ``Upgrade25_1`` removes it, which is the documented
migration — the feature no longer exists, so the only way to validate at 26.0
is to drop it.
"""

from __future__ import annotations

from galaxy_tool_source.binding import newest_valid_profile
from lxml import etree

from galaxy_tool_codemod.codemods.upgrade_25_1 import Upgrade25_1
from galaxy_tool_codemod.parse import parse_module

_STUCK = (
    b'<tool id="m" name="M" version="1.0.0" profile="25.1">'
    b"<command><![CDATA[echo x]]></command><inputs/>"
    b'<outputs><data name="o" format="txt"/></outputs>'
    b"<trackster_conf/></tool>"
)


def test_removes_trackster_conf_and_unsticks() -> None:
    module = parse_module(_STUCK)
    Upgrade25_1().apply(module)
    root = module.document.root
    assert root.find("trackster_conf") is None
    assert newest_valid_profile(module.document) not in (None, "25.1")


def test_noop_when_no_trackster_conf() -> None:
    xml = (
        b'<tool id="m" name="M" version="1.0.0" profile="25.1">'
        b"<command><![CDATA[echo x]]></command><inputs/>"
        b'<outputs><data name="o" format="txt"/></outputs></tool>'
    )
    module = parse_module(xml)
    before = etree.tostring(module.document.root)
    Upgrade25_1().apply(module)
    assert etree.tostring(module.document.root) == before


def test_removes_every_trackster_conf_at_any_depth() -> None:
    """The removal walks the whole tree, so multiple / nested occurrences all go."""
    xml = (
        b'<tool id="m" name="M" version="1.0.0" profile="25.1">'
        b"<command><![CDATA[echo x]]></command><inputs/>"
        b'<outputs><data name="o" format="txt"><trackster_conf/></data>'
        b"<trackster_conf/></outputs><trackster_conf/></tool>"
    )
    module = parse_module(xml)
    Upgrade25_1().apply(module)
    assert not list(module.document.root.iter("trackster_conf"))


def test_is_idempotent() -> None:
    module = parse_module(_STUCK)
    Upgrade25_1().apply(module)
    once = etree.tostring(module.document.root)
    Upgrade25_1().apply(module)
    assert etree.tostring(module.document.root) == once
