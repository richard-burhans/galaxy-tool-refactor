"""Tests for the ``FixInterpreter`` (GTR016) runtime-gated codemod.

Rewrites a deprecated ``<command interpreter="I">script.py …</command>`` to
``<command>I '$__tool_directory__/script.py' …</command>`` (dropping the
attribute), reproducing what Galaxy did at runtime before profile 16.04 — verbatim
``interpreter + " " + command`` concatenation, so **any** non-empty interpreter
value rewrites (flags, ``java -jar``, compound prefixes), provided the command's
first token is a literal script (bucket A). Bucket B (leading Cheetah) and an
empty ``interpreter=""`` (legacy ignored it) are left for the §23 warning.
"""

from __future__ import annotations

from lxml import etree

from galaxy_tool_xml_codemod.codemods.fix_interpreter import FixInterpreter
from galaxy_tool_xml_codemod.parse import parse_module

_HEAD = b'<tool id="m" name="M" version="1.0.0" profile="15.10">'


def _command_text(root: etree._Element) -> str:
    command = root.find("command")
    assert command is not None
    return "".join(command.itertext())


def test_bucket_a_rewrites_and_drops_attribute() -> None:
    module = parse_module(
        _HEAD + b'<command interpreter="python">myscript.py $input</command></tool>'
    )
    changes = list(FixInterpreter().detect(module))
    assert len(changes) == 1 and changes[0].code == "GTR016"
    FixInterpreter().apply(module)
    command = module.document.root.find("command")
    assert command is not None
    assert command.get("interpreter") is None  # attribute dropped
    assert _command_text(command.getroottree().getroot()) == (
        "python '$__tool_directory__/myscript.py' $input"
    )
    # The rewritten body is emitted as CDATA so shell operators stay literal.
    assert b"<![CDATA[" in etree.tostring(command)


def test_skips_mixed_content_command() -> None:
    # A mixed-content <command> (a comment / <expand> child) can't be rewritten by
    # overwriting only .text: set_text leaves the children and their tails, so the
    # tail absorbed into the new body would run twice — and clearing the children would
    # drop an <expand>'s macro content. So FixInterpreter skips it, matching the other
    # command-rewriting codemods. Behaviour-preservation GTR016
    # (docs/behavior_preservation.md).
    module = parse_module(
        _HEAD + b'<command interpreter="python">'
        b"script.py <!-- note --> --x</command></tool>"
    )
    before = etree.tostring(module.document.root)
    assert list(FixInterpreter().detect(module)) == []
    FixInterpreter().apply(module)
    assert etree.tostring(module.document.root) == before


def test_cdata_and_shell_operators_preserved() -> None:
    module = parse_module(
        _HEAD + b'<command interpreter="bash">'
        b"<![CDATA[run.sh $a && echo done]]></command></tool>"
    )
    FixInterpreter().apply(module)
    serialized = etree.tostring(module.document.root.find("command"))
    assert b"bash '$__tool_directory__/run.sh' $a && echo done" in serialized
    assert b"&amp;&amp;" not in serialized  # && stayed literal inside CDATA


def test_script_name_in_leading_comment_is_not_mistargeted() -> None:
    # The positional-splice guard: the script name appears in a leading ## comment
    # AND as the real invocation. The comment must be byte-identical; only the real
    # first invocation is rewritten (the redup.xml regression).
    module = parse_module(
        _HEAD + b'<command interpreter="perl">'
        b"<![CDATA[## should fix redup.pl\nredup.pl --in $x\n]]></command></tool>"
    )
    FixInterpreter().apply(module)
    body = _command_text(module.document.root)
    assert "## should fix redup.pl\n" in body  # comment untouched
    assert "perl '$__tool_directory__/redup.pl' --in $x" in body  # real one rewritten
    assert "## should fix perl" not in body  # comment was NOT mangled


def test_first_occurrence_only() -> None:
    module = parse_module(
        _HEAD + b'<command interpreter="python">x.py --copy x.py</command></tool>'
    )
    FixInterpreter().apply(module)
    assert _command_text(module.document.root) == (
        "python '$__tool_directory__/x.py' --copy x.py"
    )


def test_bucket_b_leading_cheetah_is_no_op() -> None:
    xml = (
        _HEAD + b'<command interpreter="python">#if $c\nx.py\n#end if</command></tool>'
    )
    module = parse_module(xml)
    assert not list(FixInterpreter().detect(module))
    before = etree.tostring(module.document.root)
    FixInterpreter().apply(module)
    assert etree.tostring(module.document.root) == before


def test_multitoken_interpreter_rewrites_verbatim() -> None:
    # Galaxy interpolates the interpreter value verbatim in every composition
    # form (prepend 16.04..20.01; token-splice + shlex.quote 20.09..dev), so
    # `java -jar` ran exactly as written — the rewrite reproduces it.
    module = parse_module(
        _HEAD + b'<command interpreter="java -jar">app.jar x</command></tool>'
    )
    changes = list(FixInterpreter().detect(module))
    assert len(changes) == 1
    FixInterpreter().apply(module)
    assert _command_text(module.document.root) == (
        "java -jar '$__tool_directory__/app.jar' x"
    )
    command = module.document.root.find("command")
    assert command is not None and command.get("interpreter") is None


def test_flags_interpreter_rewrites_verbatim() -> None:
    module = parse_module(
        _HEAD
        + b'<command interpreter="Rscript --no-save">run.R $input</command></tool>'
    )
    FixInterpreter().apply(module)
    assert _command_text(module.document.root) == (
        "Rscript --no-save '$__tool_directory__/run.R' $input"
    )


def test_compound_interpreter_prefix_rewrites_verbatim() -> None:
    # Even a shell-compound interpreter value worked by concatenation:
    # `export X=1; java -jar /abs/app.jar x`.
    module = parse_module(
        _HEAD + b'<command interpreter="export X=1; java -jar">'
        b"app.jar x</command></tool>"
    )
    FixInterpreter().apply(module)
    assert _command_text(module.document.root) == (
        "export X=1; java -jar '$__tool_directory__/app.jar' x"
    )


def test_empty_interpreter_is_no_op() -> None:
    # Legacy gated on `if interpreter:` — an empty attribute was ignored, so the
    # body was already run as-is; the rewrite shape doesn't apply.
    module = parse_module(
        _HEAD + b'<command interpreter="">script.py $i</command></tool>'
    )
    assert not list(FixInterpreter().detect(module))


def test_multitoken_interpreter_leading_cheetah_still_no_op() -> None:
    # The widening does not touch the literal-first-token requirement: a former
    # bucket-C tool whose command leads with Cheetah stays unprovable (bucket B).
    module = parse_module(
        _HEAD + b'<command interpreter="java -jar">'
        b"#if $c\napp.jar\n#end if</command></tool>"
    )
    assert not list(FixInterpreter().detect(module))


def test_is_idempotent() -> None:
    module = parse_module(
        _HEAD + b'<command interpreter="python">myscript.py $i</command></tool>'
    )
    FixInterpreter().apply(module)
    once = etree.tostring(module.document.root)
    FixInterpreter().apply(module)
    assert etree.tostring(module.document.root) == once


def test_introduced_at_1604() -> None:
    assert FixInterpreter.introduced_profile == "16.04"
    assert FixInterpreter.meta.code == "GTR016"
