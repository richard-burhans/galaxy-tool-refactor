"""Tests for the render-equality oracle.

The oracle's claim is narrow and worth restating: ``certified`` means *proven*
behaviour-preserving, by one of two instruments. A text difference alone is not a
refutation (a quoting edit changes bytes on purpose), and an unrenderable side is
``None`` -- not proven -- never a pass.

The two false certifications in ``test_catches_a_changed_boolean_truevalue`` and
``test_catches_a_changed_numeric_default`` are pinned because the first version of this
module produced them: a context built from *before* and shared with *after* cannot see
an edit to ``<inputs>`` at all.
"""

from __future__ import annotations

import copy
import subprocess

import pytest
from lxml import etree

from galaxy_tool_source.render_oracle import (
    WORLDS,
    _boundary_equal,
    build_context,
    context_fingerprint,
    dequote,
    render,
    render_equality_holds,
)

_TOOL = b"""<tool id="t" name="T" version="1.0.0" profile="24.0">
  <command detect_errors="aggressive"><![CDATA[
prog --in $infile --n $count
#if str($flag) == "true"
  --enable
#end if
#if $cutoff
  --cutoff $cutoff
#end if
  --fmt $fmt > $out
]]></command>
  <inputs>
    <param name="infile" type="data" format="txt"/>
    <param name="count" type="integer" value="7"/>
    <param name="cutoff" type="integer" value="0"/>
    <param name="flag" type="boolean" truevalue="--yes" falsevalue="" checked="false"/>
    <param name="fmt" type="select" multiple="true" optional="true"
           display="checkboxes">
      <option value="bed">bed</option><option value="gff">gff</option>
    </param>
  </inputs>
  <outputs><data name="out" format="txt"/></outputs>
</tool>"""


def _root() -> etree._Element:
    return etree.fromstring(_TOOL)


def _command(root: etree._Element) -> etree._Element:
    element = root.find("command")
    assert element is not None
    return element


# --- what it certifies -------------------------------------------------------------


def test_an_unchanged_tool_is_certified() -> None:
    verdict = render_equality_holds(_root(), _root())
    assert verdict.certified
    assert verdict.equal is True
    assert verdict.worlds_compared == len(WORLDS)


def test_dropping_a_display_attribute_is_certified() -> None:
    """GTR106's edit: presentation only, so the rendered command is byte-identical."""
    after = _root()
    param = after.find('inputs/param[@name="fmt"]')
    assert param is not None
    del param.attrib["display"]
    verdict = render_equality_holds(_root(), after)
    assert verdict.certified and verdict.equal is True


def test_a_quoting_edit_is_certified_by_the_boundary_instrument() -> None:
    """GTR020.1 changes the bytes on purpose; what it must preserve is the argv.

    This is why text equality is sufficient but not necessary, and why the oracle
    falls through to ``shell_oracle.boundary_signature`` when the text differs.
    """
    after = _root()
    command = _command(after)
    assert command.text is not None
    command.text = command.text.replace("--in $infile", "--in '$infile'")
    verdict = render_equality_holds(_root(), after)
    assert verdict.equal is False  # the bytes genuinely differ
    assert verdict.boundary_equal is True  # the shell reads it identically
    assert verdict.certified


def test_reindenting_the_command_is_certified() -> None:
    after = _root()
    command = _command(after)
    assert command.text is not None
    command.text = command.text.replace("\n  ", "\n    ")
    verdict = render_equality_holds(_root(), after)
    assert verdict.certified
    assert verdict.equal_normalised is True


# --- what it refuses ---------------------------------------------------------------


def test_catches_a_dropped_flag() -> None:
    after = _root()
    command = _command(after)
    assert command.text is not None
    command.text = command.text.replace("--n $count", "")
    verdict = render_equality_holds(_root(), after)
    assert not verdict.certified
    assert verdict.divergence is not None


def test_catches_a_changed_boolean_truevalue() -> None:
    """⛔ A shared context carries *before*'s ``truevalue``, so the render is identical.

    Pinned because the first version of this oracle certified exactly this edit. The
    context fingerprint is the half that sees it.
    """
    after = _root()
    param = after.find('inputs/param[@name="flag"]')
    assert param is not None
    param.set("truevalue", "--no")
    verdict = render_equality_holds(_root(), after)
    assert not verdict.certified
    assert verdict.reason is not None
    assert "different values" in verdict.reason


def test_catches_a_changed_numeric_default() -> None:
    """⛔ Same blindness, and it only shows in a world that uses the declared value.

    The ``low`` world pins every numeric to 0 for both trees, so this is invisible
    there; it surfaces in ``declared``. That is what the multi-world sweep is for.
    """
    after = _root()
    param = after.find('inputs/param[@name="count"]')
    assert param is not None
    param.set("value", "99")
    verdict = render_equality_holds(_root(), after)
    assert not verdict.certified


def test_catches_a_removed_templated_section() -> None:
    after = _root()
    command = _command(after)
    parent = command.getparent()
    assert parent is not None
    parent.remove(command)
    verdict = render_equality_holds(_root(), after)
    assert not verdict.certified
    assert verdict.reason is not None
    assert "sections differ" in verdict.reason


# --- the Galaxy semantics the context deliberately reproduces ----------------------


def test_a_boolean_reaches_cheetah_as_a_string_in_both_states() -> None:
    """``#if $flag`` is true for BOTH states unless ``falsevalue=""``.

    The trap the whole boolean family of rules exists for. An oracle that modelled a
    boolean as a Python bool would render the wrong branch and certify the wrong edits.
    """
    root = etree.fromstring(
        b'<tool id="t" name="T" version="1.0.0" profile="24.0">'
        b'<command><![CDATA[p\n#if $flag\n--on\n#end if\n]]></command>'
        b'<inputs><param name="flag" type="boolean" truevalue="yes" '
        b'falsevalue="no" checked="false"/></inputs>'
        b'<outputs><data name="o" format="txt"/></outputs></tool>'
    )
    low, high = WORLDS[0], WORLDS[2]
    assert "--on" in (render(root, low) or {}).get("command", "")
    assert "--on" in (render(root, high) or {}).get("command", "")


def test_an_empty_falsevalue_is_the_one_that_switches_off() -> None:
    root = etree.fromstring(
        b'<tool id="t" name="T" version="1.0.0" profile="24.0">'
        b'<command><![CDATA[p\n#if $flag\n--on\n#end if\n]]></command>'
        b'<inputs><param name="flag" type="boolean" truevalue="yes" '
        b'falsevalue="" checked="false"/></inputs>'
        b'<outputs><data name="o" format="txt"/></outputs></tool>'
    )
    assert "--on" not in (render(root, WORLDS[0]) or {}).get("command", "")
    assert "--on" in (render(root, WORLDS[2]) or {}).get("command", "")


def test_a_numeric_is_a_real_number_so_zero_is_falsy() -> None:
    root = etree.fromstring(
        b'<tool id="t" name="T" version="1.0.0" profile="24.0">'
        b'<command><![CDATA[p\n#if $n\n--n $n\n#end if\n]]></command>'
        b'<inputs><param name="n" type="integer" value="5"/></inputs>'
        b'<outputs><data name="o" format="txt"/></outputs></tool>'
    )
    assert "--n" not in (render(root, WORLDS[0]) or {}).get("command", "")  # 0
    assert "--n 5" in (render(root, WORLDS[1]) or {}).get("command", "")  # declared


def test_an_unknown_name_resolves_symbolically() -> None:
    """Galaxy injects specials (``$__tool_directory__``); a render must survive."""
    root = etree.fromstring(
        b'<tool id="t" name="T" version="1.0.0" profile="24.0">'
        b"<command><![CDATA[p '$__tool_directory__/x.py' $on_string]]></command>"
        b"<inputs/><outputs><data name=\"o\" format=\"txt\"/></outputs></tool>"
    )
    rendered = render(root, WORLDS[0])
    assert rendered is not None
    assert "__tool_directory__" in rendered["command"]


def test_a_world_selects_a_when_by_value_not_position() -> None:
    """A codemod that reorders ``<when>`` must not shift which branch a world takes."""
    tool = (
        b'<tool id="t" name="T" version="1.0.0" profile="24.0">'
        b'<command><![CDATA[p $mode.sel]]></command><inputs>'
        b'<conditional name="mode"><param name="sel" type="select">'
        b'<option value="a">a</option><option value="b">b</option></param>'
        b"%s</conditional></inputs>"
        b'<outputs><data name="o" format="txt"/></outputs></tool>'
    )
    forward = etree.fromstring(
        tool % b'<when value="a"/><when value="b"/>'
    )
    reversed_ = etree.fromstring(
        tool % b'<when value="b"/><when value="a"/>'
    )
    for world in WORLDS:
        assert context_fingerprint(build_context(forward, world)) == (
            context_fingerprint(build_context(reversed_, world))
        )


def test_an_unrenderable_tool_is_unknown_not_a_pass() -> None:
    """Cheetah cannot compile this; the verdict must be ``None``, never ``True``."""
    broken = etree.fromstring(
        b'<tool id="t" name="T" version="1.0.0" profile="24.0">'
        b"<command><![CDATA[p #if $x\nunterminated]]></command>"
        b"<inputs/><outputs><data name=\"o\" format=\"txt\"/></outputs></tool>"
    )
    verdict = render_equality_holds(broken, copy.deepcopy(broken))
    assert verdict.equal is None
    assert verdict.certified is False
    assert verdict.reason is not None


# --- quote removal, differential-tested against real bash --------------------------


@pytest.mark.parametrize(
    "word",
    [
        "plain",
        "'quoted'",
        '"dquoted"',
        "''",
        '""',
        "a'b'c",
        "a''b",
        "'a'b'c'",
        "a\\ b",
        "\\$x",
        '"a\\$x"',
        '"a\\\\b"',
        "'a\"b'",
        '"a\'b"',
        "/path/to/x",
        "--flag='v'",
        '--flag="v"',
        "a\\'b",
        '"\\n"',
        "'it'\\''s'",
        "-e",
    ],
)
def test_dequote_matches_real_bash(word: str) -> None:
    """``dequote`` must agree with the shell, not with my reading of POSIX.

    The boundary instrument compares argv words after quote removal, so an error here
    would make a quoting codemod look like it changed the command (or hide that it
    did).
    """
    real = subprocess.run(
        ["bash", "-c", f"printf '%s' {word}"],
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
    )
    if real.returncode != 0:  # pragma: no cover - bash rejects the fixture itself
        pytest.skip(f"bash rejects {word!r}")
    assert dequote(word) == real.stdout


@pytest.mark.parametrize("word", ["x$y", '"x$y"'])
def test_dequote_leaves_a_shell_expansion_alone(word: str) -> None:
    """A deliberate deviation from bash: the two renderings carry the same expansion.

    bash expands an unset ``$y`` to nothing. Doing that here would need the job's
    environment, and it would compare two sides that both hold ``$y`` -- so the
    expansion is left verbatim and cancels out.
    """
    assert "$y" in dequote(word)


def test_dequote_does_not_decode_ansi_c_quoting() -> None:
    """A known limitation, pinned: ``$'a\\tb'`` is not decoded to a real tab.

    Both sides get the same treatment, so identical input still compares identical.
    The cost is precision when a codemod edits *inside* ``$'...'``, where the verdict
    lands on not-proven -- the conservative side.
    """
    assert dequote("$'a\\tb'") != "a\tb"


def test_boundary_equality_survives_added_quotes() -> None:
    """The case that exposed the missing quote removal, from ``bgruening/diff``.

    A Cheetah var sitting between two single-quoted segments inside a sed script. Real
    bash hands sed the identical argv word either way; raw bashlex words differ by the
    added quote pair, and without ``dequote`` the oracle called GTR020.1 a bug.
    """
    before = "sed -e '/@@d@@/{r'f'' -e ';d}' t.html"
    after = "sed -e '/@@d@@/{r''f''' -e ';d}' t.html"
    assert _boundary_equal(before, after) is True


def test_boundary_equality_still_catches_a_real_argv_change() -> None:
    assert _boundary_equal("prog --in x", "prog --in x --extra") is False


# --- collection inputs: the `#for ... element_identifier` idiom ---------------------


_COLLECTION_TOOL = b"""<tool id="c" name="C" version="1.0.0" profile="24.0">
  <command><![CDATA[
prog
#for $x in $inputs
  --in '$x' --name '$x.element_identifier' --ext '$x.ext'
#end for
]]></command>
  <inputs><param name="inputs" type="data" format="txt" multiple="true"/></inputs>
  <outputs><data name="o" format="txt"/></outputs>
</tool>"""


def test_a_multiple_input_is_iterable_with_dataset_attributes() -> None:
    """⛔ Modelling a ``multiple="true"`` input as a string broke 14 of 69 real tools.

    ``#for $x in $inputs`` over a ``str`` iterates single CHARACTERS, which have no
    attributes and never reach ``_Namespace.__missing__`` -- the lookup is an
    attribute access, not a name lookup -- so the whole render failed with
    ``NotFound: element_identifier`` and the tool could not be certified at all. That
    one cause accounted for **every** blind spot the oracle had on our own wrappers.
    """
    root = etree.fromstring(_COLLECTION_TOOL)
    rendered = render(root, WORLDS[2])  # high edge: two elements
    assert rendered is not None, "a #for over a collection must render"
    command = rendered["command"]
    assert "element_identifier" in command
    assert command.count("--name") == 2, "the high world must walk two elements"


def test_the_low_world_skips_the_loop_body_entirely() -> None:
    """Zero elements, so a `#for` body contributes nothing in that world."""
    rendered = render(etree.fromstring(_COLLECTION_TOOL), WORLDS[0])
    assert rendered is not None
    assert "--name" not in rendered["command"]


def test_a_data_collection_param_is_iterable_too() -> None:
    root = etree.fromstring(
        b'<tool id="c" name="C" version="1.0.0" profile="24.0">'
        b"<command><![CDATA[p\n#for $e in $coll\n"
        b"--n $e.element_identifier\n#end for\n]]></command>"
        b'<inputs><param name="coll" type="data_collection" collection_type="list" '
        b'format="txt"/></inputs>'
        b'<outputs><data name="o" format="txt"/></outputs></tool>'
    )
    rendered = render(root, WORLDS[2])
    assert rendered is not None and rendered["command"].count("--n") == 2


def test_a_single_dataset_param_stays_a_scalar() -> None:
    """Only multiple/collection inputs become lists; a plain data param must not,
    or `--in '$input'` would render a Python list repr into the command."""
    root = etree.fromstring(
        b'<tool id="c" name="C" version="1.0.0" profile="24.0">'
        b"<command><![CDATA[p --in '$input' "
        b"--id '$input.element_identifier']]></command>"
        b'<inputs><param name="input" type="data" format="txt"/></inputs>'
        b'<outputs><data name="o" format="txt"/></outputs></tool>'
    )
    rendered = render(root, WORLDS[1])
    assert rendered is not None
    assert "[" not in rendered["command"], "a single dataset must not render as a list"
    assert "input.element_identifier" in rendered["command"]
