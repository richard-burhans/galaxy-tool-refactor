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
    RenameEdit,
    RenameOutcome,
    RenamePlan,
    _raw_offset_map,
    rename_param,
    rename_param_plan,
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


# --- offset-returning rename (rename_param_plan) --------------------------------


def _apply(source: str, plan: RenamePlan) -> str:
    """Apply a plan's edits to *source*, highest offset first (LSP-client order)."""
    out = source
    for edit in sorted(plan.edits, key=lambda e: e.start, reverse=True):
        out = f"{out[: edit.start]}{edit.replacement}{out[edit.end :]}"
    return out


# Representative success sources, each renaming ``old`` -> ``new`` cleanly.
_PLAN_SUCCESS = [
    "<tool><inputs><param name='old'/></inputs>"
    "<command>tool $old -o out.txt</command></tool>",
    "<tool><inputs><conditional name='cond'><param name='old'/></conditional></inputs>"
    "<command>run ${old_other} $cond.old ${cond.old}.ext</command></tool>",
    "<tool><command><![CDATA[#if $old\ntool '$old'\n#end if\n]]></command></tool>",
    "<tool><inputs><param name='old'/></inputs><configfiles>"
    "<configfile name='script'>x = '$old'</configfile></configfiles>"
    "<command>run</command></tool>",
    "<tool><inputs><param name='old' type='data'/>"
    "<param name='col' type='data_column' data_ref='old'/></inputs>"
    "<command>run $old</command></tool>",
    "<tool><inputs><param name='old'/></inputs><command>run $old</command>"
    "<outputs><data name='o' label='out for ${old}.ext'/></outputs></tool>",
    "<tool><command>cp in '$out'</command>"
    "<outputs><data name='out' format='txt'/></outputs></tool>",
    "<tool><inputs><param name='old'/></inputs><command>run $old</command>"
    "<tests><test><param name='old' value='1'/>"
    "<output name='out' file='o.txt'/></test></tests></tool>",
    "<tool><command>run</command><environment_variables>"
    "<environment_variable name='E'>$old/path</environment_variable>"
    "</environment_variables></tool>",
    "<tool><inputs><param name='old'/></inputs>"
    "<command>echo a &amp;&amp; run $old &lt; in.txt</command></tool>",
    # Newline/whitespace before the CDATA opener (very common formatting).
    "<tool><inputs><param name='old'/></inputs>"
    "<command>\n    <![CDATA[run $old -o out]]>\n</command></tool>",
]


@pytest.mark.parametrize("source", _PLAN_SUCCESS)
def test_plan_matches_tree_rename(source: str) -> None:
    old, new = ("out", "result") if "name='out'" in source else ("old", "new")
    plan = rename_param_plan(source, old=old, new=new)
    assert not plan.bailed
    # Every edit replaces exactly the `old` segment (segment-precise, not whole-ref).
    assert all(source[edit.start : edit.end] == old for edit in plan.edits)
    # Applying the plan and re-parsing is identical to the tree-mutating rendering.
    applied_root = etree.fromstring(_apply(source, plan).encode("utf-8"))
    tree_root = etree.fromstring(source.encode("utf-8"))
    outcome = rename_param(tree_root, old=old, new=new)
    assert plan.renamed == outcome.renamed
    assert etree.tostring(applied_root) == etree.tostring(tree_root)
    assert _no_live_old(applied_root, old)


def test_plan_edits_are_disjoint_and_ordered() -> None:
    source = ("<tool><inputs><param name='old'/></inputs>"
              "<command>$old $old $old</command></tool>")
    plan = rename_param_plan(source, old="old", new="new")
    assert not plan.bailed
    starts = [edit.start for edit in plan.edits]
    assert starts == sorted(starts)
    for previous, current in zip(plan.edits, plan.edits[1:], strict=False):
        assert current.start >= previous.end


def test_plan_minimal_diff_leaves_other_bytes_untouched() -> None:
    source = ("<tool><inputs><param name='old'/></inputs>"
              "<command>tool $old -o out.txt</command></tool>")
    plan = rename_param_plan(source, old="old", new="renamed_param")
    applied = _apply(source, plan)
    # Only the renamed tokens differ; removing every edit's replacement restores source.
    assert applied.count("renamed_param") == len(plan.edits)
    assert applied.replace("renamed_param", "old") == source


@pytest.mark.parametrize(
    ("source", "old", "new", "reason"),
    [
        ("<tool><command>#set $old = 1\nrun $old</command></tool>",
         "old", "new", "shadowed"),
        ("<tool><command>run $old <token>x</token></command></tool>",
         "old", "new", "mixed-content"),
        ("<tool><command>#if $old\nrun $old\n</command></tool>",
         "old", "new", "lexer-bail"),
        ("<tool><inputs><param name='other'/></inputs>"
         "<command>run $other</command></tool>", "absent", "new", "not-found"),
        ("<tool><command>run $old</command></tool>",
         "old", "not an identifier", "invalid-name"),
        ("<tool><command>run $old</command></tool>", "old", "old", "no-op"),
        ("<tool><inputs><param name='old'/></inputs><command>run $old</command>"
         "<outputs><data name='o' some_future_ref='old'/></outputs></tool>",
         "old", "new", "cross-ref-residual"),
        ("<tool><command>run $old</command>"
         "<outputs><data name='o'><filter>old == 'x'</filter></data></outputs></tool>",
         "old", "new", "filter-bare-ref"),
    ],
)
def test_plan_bail_parity(source: str, old: str, new: str, reason: str) -> None:
    plan = rename_param_plan(source, old=old, new=new)
    outcome = rename_param(etree.fromstring(source.encode("utf-8")), old=old, new=new)
    assert plan.bailed
    assert plan.edits == ()
    assert plan.reason == reason == outcome.reason


def test_plan_parse_error_bails() -> None:
    # Input the lenient recover parser cannot salvage into a tree at all. (A merely
    # unclosed tag is recovered, and its edits stay sound via the slice self-check.)
    plan = rename_param_plan("%%% not xml at all %%%", old="old", new="new")
    assert plan.bailed
    assert plan.reason == "parse-error"


def test_plan_entities_are_relocated() -> None:
    # A non-CDATA body with &amp; entities: the decoded-text span is relocated to the
    # raw source via the entity-aware map, so the rename applies (no entity bail).
    source = "<tool><command>echo a &amp;&amp; run $old &lt; in</command></tool>"
    plan = rename_param_plan(source, old="old", new="new")
    assert not plan.bailed
    assert all(source[edit.start : edit.end] == "old" for edit in plan.edits)
    assert _apply(source, plan) == (
        "<tool><command>echo a &amp;&amp; run $new &lt; in</command></tool>"
    )
    # And the applied source re-parses to the same tree the mutator produces.
    applied_root = etree.fromstring(_apply(source, plan).encode("utf-8"))
    tree_root = etree.fromstring(source.encode("utf-8"))
    rename_param(tree_root, old="old", new="new")
    assert etree.tostring(applied_root) == etree.tostring(tree_root)


def test_plan_handles_whitespace_before_cdata() -> None:
    # Whitespace before a CDATA section interleaves raw `<![CDATA[` into `.text`; the
    # walker consumes the leading whitespace + the section markers and still relocates.
    source = "<tool><command>  <![CDATA[run $old here]]></command></tool>"
    plan = rename_param_plan(source, old="old", new="new")
    assert not plan.bailed
    assert _apply(source, plan) == (
        "<tool><command>  <![CDATA[run $new here]]></command></tool>"
    )


def test_plan_encoding_bail_on_non_utf8_bytes() -> None:
    # The bytes convenience only supports UTF-8 (the LSP path passes a decoded str).
    source = "<tool><command>café $old</command></tool>".encode("latin-1")
    plan = rename_param_plan(source, old="old", new="new")
    assert plan.bailed
    assert plan.reason == "encoding"


def test_raw_offset_map_helper() -> None:
    # Plain text: each decoded char maps to itself (offset by base).
    assert _raw_offset_map("X" + "ab", 1, "ab") == [1, 2]
    # An entity decodes to one char; later offsets account for the wider raw span.
    mapping = _raw_offset_map("<c>a&amp;b</c>", 3, "a&b")
    assert mapping == [3, 4, 9]  # 'a'@3, '&amp;'@4, 'b'@9
    # A CDATA section's content is verbatim; markers are skipped.
    mapping = _raw_offset_map("<c><![CDATA[ab]]></c>", 3, "ab")
    assert mapping == [12, 13]
    # An undecodable named entity is the (rare) genuine entity-content bail.
    assert _raw_offset_map("<c>&nbsp;</c>", 3, "\xa0") == "entity-content"


def test_plan_attribute_value_with_entities() -> None:
    # An attribute value with an entity (&amp;): the same walker relocates the $old span
    # past the entity, so the attr-Cheetah rename applies (no flat-check bail).
    source = (
        "<tool><inputs><param name='old'/></inputs><command>run $old</command>"
        "<outputs><data name='o' label='a &amp; b ${old}.txt'/></outputs></tool>"
    )
    plan = rename_param_plan(source, old="old", new="renamed")
    assert not plan.bailed
    assert all(source[edit.start : edit.end] == "old" for edit in plan.edits)
    root = etree.fromstring(_apply(source, plan).encode("utf-8"))
    assert root.find("outputs/data").get("label") == "a & b ${renamed}.txt"
    assert root.find("inputs/param").get("name") == "renamed"


def test_plan_cdata_offsets_are_correct() -> None:
    source = "<tool><command><![CDATA[run $old here]]></command></tool>"
    plan = rename_param_plan(source, old="old", new="new")
    assert not plan.bailed
    (edit,) = plan.edits
    assert source[edit.start : edit.end] == "old"
    assert _apply(source, plan) == (
        "<tool><command><![CDATA[run $new here]]></command></tool>"
    )


def test_plan_attribute_value_span_not_tag() -> None:
    # data_ref="old" resolves to the value span (the inner "old"), not the tag/name.
    source = ("<tool><inputs><param name='old' type='data'/>"
              "<param name='col' type='data_column' data_ref='old'/></inputs>"
              "<command>run $old</command></tool>")
    plan = rename_param_plan(source, old="old", new="aligned")
    assert not plan.bailed
    assert all(source[edit.start : edit.end] == "old" for edit in plan.edits)
    root = etree.fromstring(_apply(source, plan).encode("utf-8"))
    assert root.find("inputs/param[@name='col']").get("data_ref") == "aligned"
    assert root.find("inputs/param[@name='aligned']") is not None


def test_plan_multiline_start_tag() -> None:
    # lxml's sourceline for a multi-line start tag is the line of its closing `>`, not
    # the opening `<`; the locator must still anchor it (regression: it used to grab the
    # next same-tag element, renaming the wrong param).
    source = (
        "<tool><inputs>\n"
        "  <param name='old'\n"
        "         type='data'\n"
        "         format='fasta'/>\n"
        "  <param name='other' type='data'/>\n"
        "</inputs><command>run $old $other</command></tool>"
    )
    plan = rename_param_plan(source, old="old", new="renamed")
    assert not plan.bailed
    assert all(source[edit.start : edit.end] == "old" for edit in plan.edits)
    root = etree.fromstring(_apply(source, plan).encode("utf-8"))
    assert root.find("inputs/param[@name='renamed']") is not None
    assert root.find("inputs/param[@name='other']") is not None  # untouched
    assert root.find("command").text == "run $renamed $other"


def test_plan_dotted_segment_only() -> None:
    source = (
        "<tool><inputs><conditional name='cond'><param name='old'/></conditional>"
        "</inputs><command>$cond.old ${cond.old}.ext ${old_other}</command></tool>"
    )
    plan = rename_param_plan(source, old="old", new="x")
    assert not plan.bailed
    assert all(source[edit.start : edit.end] == "old" for edit in plan.edits)
    assert _apply(source, plan) == (
        "<tool><inputs><conditional name='cond'><param name='x'/></conditional>"
        "</inputs><command>$cond.x ${cond.x}.ext ${old_other}</command></tool>"
    )


def test_plan_is_dataclass() -> None:
    plan = RenamePlan(
        edits=(RenameEdit(1, 4, "new"),), renamed=1, bailed=False, reason=None
    )
    assert plan.edits[0].replacement == "new"
    assert plan.renamed == 1
