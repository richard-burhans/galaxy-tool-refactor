"""Tests for the ``16_04_fix_interpreter`` eligibility core."""

from __future__ import annotations

from pathlib import Path

from lxml import etree

from galaxy_tool_codemod.codemods._interpreter import (
    first_command_token,
    first_command_token_span,
    interpreter_rewrite,
    interpreter_rewrite_target,
)


def _root(xml: str) -> etree._Element:
    return etree.fromstring(xml.encode("utf-8"))


def test_first_command_token_span_anchors_past_leading_comment() -> None:
    # The script name appears inside a leading ## comment AND as the real first
    # token. The span offset must point at the REAL invocation line so a rewrite
    # restricted to body[offset:] never touches the comment (the redup.xml bug).
    body = "## should fix redup.pl\n  redup.pl --in $x\n"
    span = first_command_token_span(body)
    assert span is not None
    token, offset = span
    assert token == "redup.pl"
    assert body[:offset] == "## should fix redup.pl\n"  # comment is before the anchor
    assert body[offset:].startswith("  redup.pl")


def test_first_command_token_span_none_on_leading_directive() -> None:
    assert first_command_token_span("#if $c\nx.py\n#end if") is None


def test_interpreter_rewrite_returns_full_plan() -> None:
    root = _root(
        '<tool><command interpreter="python">myscript.py $input</command></tool>'
    )
    plan = interpreter_rewrite(root)
    assert plan == ("python", "myscript.py", 0)


def test_interpreter_rewrite_none_for_bucket_b_and_empty() -> None:
    bucket_b = _root(
        '<tool><command interpreter="python">#if $c\nx.py\n#end if</command></tool>'
    )
    empty = _root('<tool><command interpreter="">x.py</command></tool>')
    assert interpreter_rewrite(bucket_b) is None
    # Legacy gated on `if interpreter:` — an empty attribute was ignored.
    assert interpreter_rewrite(empty) is None


def test_first_command_token_skips_blanks_and_comments() -> None:
    assert first_command_token("\n  ## a comment\nmyscript.py $in\n") == "myscript.py"


def test_first_command_token_none_on_leading_directive() -> None:
    assert first_command_token("#if $cond\nmyscript.py\n#end if") is None


def test_target_bucket_a_simple() -> None:
    root = _root(
        '<tool><command interpreter="python">myscript.py $input</command></tool>'
    )
    assert interpreter_rewrite_target(root) == "myscript.py"


def test_target_handles_cdata_and_perl() -> None:
    root = _root(
        '<tool><command interpreter="perl">'
        "<![CDATA[\nrun.pl --in $x\n]]></command></tool>"
    )
    assert interpreter_rewrite_target(root) == "run.pl"


def test_target_none_for_leading_cheetah() -> None:
    root = _root(
        '<tool><command interpreter="python">#if $c\nx.py\n#end if</command></tool>'
    )
    assert interpreter_rewrite_target(root) is None


def test_target_none_for_var_first_token() -> None:
    root = _root('<tool><command interpreter="python">$wrapper x.py</command></tool>')
    assert interpreter_rewrite_target(root) is None


def test_target_resolves_for_any_nonempty_interpreter() -> None:
    # Galaxy interpolates the interpreter value verbatim in every composition
    # form (prepend 16.04..20.01; token-splice 20.09..dev:787), so flag-bearing /
    # non-script values are in scope — the literal first token is the only gate.
    for interp in ("java -jar", "docker", "Rscript --no-save", "python -W ignore"):
        root = _root(
            f'<tool><command interpreter="{interp}">app.jar x</command></tool>'
        )
        assert interpreter_rewrite_target(root) == "app.jar"


def test_target_none_when_first_token_not_a_filename() -> None:
    root = _root('<tool><command interpreter="bash">cd /tmp</command></tool>')
    assert interpreter_rewrite_target(root) is None


def test_target_none_without_command_or_interpreter() -> None:
    assert interpreter_rewrite_target(_root("<tool><inputs/></tool>")) is None
    assert (
        interpreter_rewrite_target(_root("<tool><command>x.py $i</command></tool>"))
        is None
    )


def test_target_file_exists_guard(tmp_path: Path) -> None:
    root = _root(
        '<tool><command interpreter="python">myscript.py $input</command></tool>'
    )
    # script absent -> not bucket A under the existence guard
    assert interpreter_rewrite_target(root, tool_dir=tmp_path) is None
    (tmp_path / "myscript.py").write_text("print(1)\n", encoding="utf-8")
    assert interpreter_rewrite_target(root, tool_dir=tmp_path) == "myscript.py"
