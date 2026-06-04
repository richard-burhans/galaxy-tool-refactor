"""Tests for ``SingleQuoteCommandVars`` (GTR020).

Single-quotes only the provably-single-valued unquoted Cheetah ``$var``\\ s in a
``<command>`` body — the ``{safe, attr_safe, builtin_path}`` classes
(``galaxy_tool_xml.command_vars``) whose value can never contain whitespace for a
tool that currently works. Free-form ``text`` params, deliberate ``multiple=``
splats, label attrs (``.name``), and ``#set``/loop vars are left untouched (the
GTR020.2 advisory check still flags them).
"""

from __future__ import annotations

import pytest
from galaxy_tool_xml.shell_oracle import shell_oracle_available
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
    b'<param name="fd" type="integer"/>'
    b"</inputs>"
)

requires_oracle = pytest.mark.skipif(
    not shell_oracle_available(), reason="needs the shell-oracle extra (bashlex)"
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


@requires_oracle
def test_does_not_quote_assignment_rhs_residual() -> None:
    # $opts is a free-form text param. An assignment RHS is a no-split context for a
    # shell *expansion*, but Galaxy renders the Cheetah value as literal text and a
    # literal `THREADS=foo bar` splits — so quoting is NOT behaviour-preserving. The
    # oracle does not widen here; a non-provable text param is left untouched.
    module = _module(b"<command><![CDATA[THREADS=$opts\nrun $opts]]></command>")
    assert list(SingleQuoteCommandVars().detect(module)) == []
    before = etree.tostring(module.document.root)
    SingleQuoteCommandVars().apply(module)
    assert etree.tostring(module.document.root) == before


@requires_oracle
def test_does_not_false_veto_glued_safe_var() -> None:
    # a space-free data param glued to a literal suffix stays fixable (the discarded
    # "standalone word" predicate would have wrongly vetoed this).
    module = _module(b"<command><![CDATA[run ${ds}.bam]]></command>")
    SingleQuoteCommandVars().apply(module)
    assert _command_text(module.document.root) == "run '${ds}'.bam"


@requires_oracle
def test_narrows_fd_dup_target() -> None:
    # $fd is an integer (value-domain "safe"), but in a >&-dup position quoting would
    # flip a descriptor dup into a file redirect, so the oracle narrows it away.
    module = _module(b"<command><![CDATA[run 2>&$fd]]></command>")
    assert list(SingleQuoteCommandVars().detect(module)) == []


def test_certifier_seam_overrides_default() -> None:
    # An injected certifier replaces the default policy (the Phase-2 seam). A
    # quote-everything certifier quotes a residual text param the default leaves alone.
    class _QuoteEverything:
        def should_quote(self, body, /, *, occurrence, kinds, structural) -> bool:
            return True

    module = _module(b"<command><![CDATA[run $opts]]></command>")
    SingleQuoteCommandVars(certifier=_QuoteEverything()).apply(module)
    assert _command_text(module.document.root) == "run '$opts'"
    # default leaves the splitting-position text param untouched
    plain = _module(b"<command><![CDATA[run $opts]]></command>")
    SingleQuoteCommandVars().apply(plain)
    assert _command_text(plain.document.root) == "run $opts"
