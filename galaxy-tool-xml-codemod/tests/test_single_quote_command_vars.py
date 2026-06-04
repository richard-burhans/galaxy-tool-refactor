"""Tests for ``SingleQuoteCommandVars`` (GTR020).

Single-quotes only the provably-single-valued unquoted Cheetah ``$var``\\ s in a
``<command>`` body — the ``{safe, attr_safe, builtin_path}`` classes
(``galaxy_tool_xml.command_vars``) whose value can never contain whitespace for a
tool that currently works. Free-form ``text`` params, deliberate ``multiple=``
splats, label attrs (``.name``), and ``#set``/loop vars are left untouched (the
GTR020.2 advisory check still flags them).
"""

from __future__ import annotations

from lxml import etree

from galaxy_tool_xml_codemod.codemods.single_quote_command_vars import (
    SingleQuoteCommandVars,
)
from galaxy_tool_xml_codemod.parse import parse_module

_HEAD = b'<tool id="m" name="M" version="1.0.0" profile="21.09">'
_INPUTS = (
    b"<inputs>"
    b'<param name="ds" type="data"/>'
    b'<param name="opts" type="text"/>'
    b'<param name="files" type="data" multiple="true"/>'
    b"</inputs>"
)


def _command_text(root: etree._Element) -> str:
    command = root.find("command")
    assert command is not None
    return "".join(command.itertext())


def _module(command: bytes):
    return parse_module(_HEAD + _INPUTS + command + b"</tool>")


def test_quotes_only_the_provable_classes() -> None:
    module = _module(
        b"<command><![CDATA["
        b"python $__tool_directory__/s.py $ds --ext $ds.ext "
        b"--opts $opts --files $files --name $ds.name"
        b"]]></command>"
    )
    changes = list(SingleQuoteCommandVars().detect(module))
    assert len(changes) == 1 and changes[0].code == "GTR020.1"
    SingleQuoteCommandVars().apply(module)
    assert _command_text(module.document.root) == (
        "python '$__tool_directory__'/s.py '$ds' --ext '$ds.ext' "
        "--opts $opts --files $files --name $ds.name"
    )


def test_detect_does_not_mutate() -> None:
    module = _module(b"<command><![CDATA[run $ds]]></command>")
    before = etree.tostring(module.document.root)
    list(SingleQuoteCommandVars().detect(module))
    assert etree.tostring(module.document.root) == before


def test_preserves_cdata_wrapping() -> None:
    module = _module(b"<command><![CDATA[run $ds]]></command>")
    SingleQuoteCommandVars().apply(module)
    command = module.document.root.find("command")
    assert command is not None
    assert b"<![CDATA[" in etree.tostring(command)
    assert _command_text(module.document.root) == "run '$ds'"


def test_preserves_non_cdata_body() -> None:
    module = _module(b"<command>run $ds</command>")
    SingleQuoteCommandVars().apply(module)
    command = module.document.root.find("command")
    assert command is not None
    assert b"<![CDATA[" not in etree.tostring(command)
    assert _command_text(module.document.root) == "run '$ds'"


def test_no_change_when_nothing_provable() -> None:
    module = _module(b"<command><![CDATA[run $opts $files $ds.name]]></command>")
    assert list(SingleQuoteCommandVars().detect(module)) == []
    before = etree.tostring(module.document.root)
    SingleQuoteCommandVars().apply(module)
    assert etree.tostring(module.document.root) == before


def test_skips_mixed_content_command() -> None:
    module = _module(b"<command>echo $ds<foo/></command>")
    assert list(SingleQuoteCommandVars().detect(module)) == []


def test_is_idempotent() -> None:
    module = _module(
        b"<command><![CDATA[python $__tool_directory__/s.py $ds $ds.ext]]></command>"
    )
    SingleQuoteCommandVars().apply(module)
    once = etree.tostring(module.document.root)
    SingleQuoteCommandVars().apply(module)
    assert etree.tostring(module.document.root) == once
