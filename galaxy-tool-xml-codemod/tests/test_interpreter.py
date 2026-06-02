"""Tests for the ``16_04_fix_interpreter`` eligibility core."""

from __future__ import annotations

from pathlib import Path

from lxml import etree

from galaxy_tool_xml_codemod.codemods._interpreter import (
    first_command_token,
    interpreter_rewrite_target,
)


def _root(xml: str) -> etree._Element:
    return etree.fromstring(xml.encode("utf-8"))


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


def test_target_none_for_non_standard_interpreter() -> None:
    # multi-token / non-script "interpreters" are out of scope
    for interp in ("java -jar", "docker", "Rscript --no-save", "python -W ignore"):
        root = _root(
            f'<tool><command interpreter="{interp}">app.jar x</command></tool>'
        )
        assert interpreter_rewrite_target(root) is None


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
