"""Tests for the tier-1 Cheetah parameter-rename primitive (``cheetah_rename``).

The first Cheetah *mutator* — the mutating sibling of ``find-references``. Rename is
**atomic**: every live ``$old`` reference (in ``<command>`` / ``<configfile>`` via the
faithful lexer, in attribute-Cheetah, in cross-ref attributes) plus the definition is
rewritten, or the whole rename bails and nothing changes. Skipped when CT3 is absent
(the rewrite of ``<command>`` bodies needs the faithful lexer).
"""

from __future__ import annotations

import pytest

pytest.importorskip("Cheetah")

from lxml import etree  # noqa: E402

from galaxy_tool_xml.cheetah_refs import tool_cheetah_references  # noqa: E402
from galaxy_tool_xml.cheetah_rename import (  # noqa: E402
    RenameOutcome,
    rename_param,
)


def _root(xml: str) -> etree._Element:
    return etree.fromstring(xml.encode("utf-8"))


def _no_live_old(root: etree._Element, old: str) -> bool:
    """No live ``$old`` reference survives (the find-references invariant)."""
    return not any(old in ref.segments for ref in tool_cheetah_references(root))


# --- success cases --------------------------------------------------------------


def test_simple_command_reference() -> None:
    root = _root("<tool><inputs><param name='old'/></inputs>"
                 "<command>tool $old -o out.txt</command></tool>")
    outcome = rename_param(root, old="old", new="new")
    assert not outcome.bailed
    assert root.find("command").text == "tool $new -o out.txt"
    assert root.find("inputs/param").get("name") == "new"
    assert _no_live_old(root, "old")


def test_braced_and_dotted_references() -> None:
    root = _root(
        "<tool><inputs><conditional name='cond'>"
        "<param name='old'/></conditional></inputs>"
        "<command>run ${old_other} $cond.old ${cond.old}.ext</command></tool>"
    )
    outcome = rename_param(root, old="old", new="renamed")
    assert not outcome.bailed
    # Only the matching segment is rewritten; $old_other is a different name.
    assert (
        root.find("command").text
        == "run ${old_other} $cond.renamed ${cond.renamed}.ext"
    )
    assert root.find("inputs/conditional/param").get("name") == "renamed"


def test_directive_head_reference() -> None:
    root = _root("<tool><command>#if $old\ntool '$old'\n#end if\n</command></tool>")
    outcome = rename_param(root, old="old", new="new")
    assert not outcome.bailed
    assert root.find("command").text == "#if $new\ntool '$new'\n#end if\n"


def test_raw_and_comment_are_not_rewritten() -> None:
    # $old inside #raw / a ## comment is not a live reference; it stays, and its
    # presence does NOT cause a bail (the residual oracle is faithful, not regex).
    root = _root(
        "<tool><command>## mentions $old\n#raw\n$old stays\n#end raw\n"
        "run $old</command></tool>"
    )
    outcome = rename_param(root, old="old", new="new")
    assert not outcome.bailed
    body = root.find("command").text
    assert "## mentions $old" in body  # comment untouched
    assert "$old stays" in body  # raw untouched
    assert "run $new" in body  # live reference rewritten


def test_configfile_reference() -> None:
    root = _root(
        "<tool><inputs><param name='old'/></inputs><configfiles>"
        "<configfile name='script'>x = '$old'</configfile></configfiles>"
        "<command>run</command></tool>"
    )
    outcome = rename_param(root, old="old", new="new")
    assert not outcome.bailed
    assert root.find(".//configfile").text == "x = '$new'"


def test_cross_ref_attribute() -> None:
    root = _root(
        "<tool><inputs><param name='old' type='data'/>"
        "<param name='col' type='data_column' data_ref='old'/></inputs>"
        "<command>run $old</command></tool>"
    )
    outcome = rename_param(root, old="old", new="new")
    assert not outcome.bailed
    assert root.find("inputs/param[@name='col']").get("data_ref") == "new"


def test_attribute_cheetah_label() -> None:
    root = _root(
        "<tool><inputs><param name='old'/></inputs>"
        "<command>run $old</command>"
        "<outputs><data name='o' label='out for ${old}.ext'/></outputs></tool>"
    )
    outcome = rename_param(root, old="old", new="new")
    assert not outcome.bailed
    assert root.find("outputs/data").get("label") == "out for ${new}.ext"


def test_renamed_count_reflects_sites() -> None:
    root = _root("<tool><inputs><param name='old'/></inputs>"
                 "<command>$old $old</command></tool>")
    outcome = rename_param(root, old="old", new="new")
    # two command refs + one definition
    assert outcome.renamed == 3


# --- bail cases -----------------------------------------------------------------


def test_shadowed_by_local_binding_bails() -> None:
    root = _root("<tool><command>#set $old = 1\nrun $old</command></tool>")
    before = etree.tostring(root)
    outcome = rename_param(root, old="old", new="new")
    assert outcome.bailed
    assert outcome.reason == "shadowed"
    assert etree.tostring(root) == before  # unchanged


def test_mixed_content_command_bails() -> None:
    root = _root("<tool><command>run $old <token>x</token></command></tool>")
    before = etree.tostring(root)
    outcome = rename_param(root, old="old", new="new")
    assert outcome.bailed
    assert outcome.reason == "mixed-content"
    assert etree.tostring(root) == before


def test_lexer_bail_command_bails() -> None:
    # An unterminated #if cannot be lexed faithfully -> bail rather than guess.
    root = _root("<tool><command>#if $old\nrun $old\n</command></tool>")
    before = etree.tostring(root)
    outcome = rename_param(root, old="old", new="new")
    assert outcome.bailed
    assert outcome.reason == "lexer-bail"
    assert etree.tostring(root) == before


def test_not_found_bails() -> None:
    root = _root("<tool><inputs><param name='other'/></inputs>"
                 "<command>run $other</command></tool>")
    outcome = rename_param(root, old="absent", new="new")
    assert outcome.bailed
    assert outcome.reason == "not-found"


def test_invalid_new_name_bails() -> None:
    root = _root("<tool><command>run $old</command></tool>")
    outcome = rename_param(root, old="old", new="not an identifier")
    assert outcome.bailed
    assert outcome.reason == "invalid-name"


def test_no_op_same_name_bails() -> None:
    root = _root("<tool><command>run $old</command></tool>")
    outcome = rename_param(root, old="old", new="old")
    assert outcome.bailed


def test_change_format_input_is_renamed() -> None:
    # `<when input="old">` is a modelled by-name cross-reference — it is rewritten.
    root = _root(
        "<tool><inputs><param name='old'/></inputs><command>run $old</command>"
        "<outputs><data name='o'><change_format>"
        "<when input='old' value='x' format='txt'/>"
        "</change_format></data></outputs></tool>"
    )
    outcome = rename_param(root, old="old", new="new")
    assert not outcome.bailed
    assert root.find(".//change_format/when").get("input") == "new"


def test_tests_param_reference_is_renamed() -> None:
    # A <test><param name="old"> references the input by name and follows the rename.
    root = _root(
        "<tool><inputs><param name='old'/></inputs><command>run $old</command>"
        "<tests><test><param name='old' value='1'/>"
        "<output name='out' file='o.txt'/></test></tests></tool>"
    )
    outcome = rename_param(root, old="old", new="new")
    assert not outcome.bailed
    assert root.find(".//tests//param").get("name") == "new"


def test_coincidental_literal_value_does_not_bail() -> None:
    # A param default value or a select option value that merely equals the name is a
    # coincidence, not a reference — the rename still applies.
    root = _root(
        "<tool><inputs><param name='fmt' type='select' value='fmt'>"
        "<option value='fmt'>F</option></param></inputs>"
        "<command>run $fmt</command></tool>"
    )
    outcome = rename_param(root, old="fmt", new="kind")
    assert not outcome.bailed
    assert root.find("inputs/param").get("name") == "kind"
    assert root.find("inputs/param").get("value") == "fmt"  # literal value untouched


def test_unmodeled_non_literal_attribute_bails() -> None:
    # A non-literal attribute whose value still equals old after rewriting is a possible
    # by-name reference this version does not model — the net bails to avoid a dangler.
    root = _root(
        "<tool><inputs><param name='old'/></inputs>"
        "<command>run $old</command>"
        "<outputs><data name='o' some_future_ref='old'/></outputs></tool>"
    )
    outcome = rename_param(root, old="old", new="new")
    assert outcome.bailed
    assert outcome.reason == "cross-ref-residual"


def test_output_data_name_rename() -> None:
    root = _root(
        "<tool><command>cp in '$out'</command>"
        "<outputs><data name='out' format='txt'/></outputs></tool>"
    )
    outcome = rename_param(root, old="out", new="result")
    assert not outcome.bailed
    assert root.find("outputs/data").get("name") == "result"
    assert root.find("command").text == "cp in '$result'"


def test_find_references_invariant() -> None:
    # The defining property: after a successful rename, find-references finds no `old`
    # and the new name where old used to be.
    root = _root(
        "<tool><inputs><conditional name='c'><param name='old'/></conditional></inputs>"
        "<command>run $old $c.old\n#if $old\necho '$old'\n#end if</command>"
        "<outputs><data name='o' label='$old.x'/></outputs></tool>"
    )
    outcome = rename_param(root, old="old", new="new")
    assert not outcome.bailed
    segments = {seg for ref in tool_cheetah_references(root) for seg in ref.segments}
    assert "old" not in segments
    assert "new" in segments


def test_environment_variable_reference() -> None:
    root = _root(
        "<tool><command>run</command><environment_variables>"
        "<environment_variable name='E'>$old/path</environment_variable>"
        "</environment_variables></tool>"
    )
    outcome = rename_param(root, old="old", new="new")
    assert not outcome.bailed
    assert root.find(".//environment_variable").text == "$new/path"


def test_filter_bare_reference_bails() -> None:
    root = _root(
        "<tool><command>run $old</command>"
        "<outputs><data name='o'><filter>old == 'x'</filter></data></outputs></tool>"
    )
    outcome = rename_param(root, old="old", new="new")
    assert outcome.bailed
    assert outcome.reason == "filter-bare-ref"


def test_outcome_is_dataclass() -> None:
    assert RenameOutcome(renamed=0, bailed=True, reason="x").reason == "x"
