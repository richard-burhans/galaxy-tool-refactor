"""Tests for the command-var quoting-safety classifier (GTR020 / GTR020.2 substrate)."""

from __future__ import annotations

from lxml import etree

from galaxy_tool_source.command_vars import (
    classify_var,
    command_var_info,
    input_param_info,
    io_file_names,
    is_io_file_ref,
    provably_quotable,
)


def test_io_file_names_inputs_and_output_data_only() -> None:
    root = etree.fromstring(
        b"<tool>"
        b'<inputs><param name="reads" type="data"/>'
        b'<param name="many" type="data" multiple="true"/>'
        b'<param name="coll" type="data_collection"/>'
        b'<param name="thr" type="integer"/>'
        b'<param name="mode" type="select"/>'
        b'<conditional name="anno"><param name="ref" type="data"/></conditional>'
        b"</inputs>"
        b'<outputs><data name="out"/>'
        b'<collection name="out_coll" type="list"/></outputs></tool>'
    )
    # single data inputs + output <data>; never multiple/collection/select/number.
    assert io_file_names(root) == {"reads", "ref", "out"}


def test_is_io_file_ref_resolution() -> None:
    io_files = {"reads", "ref", "out"}
    structural = {"anno"}
    assert is_io_file_ref("$reads", io_files, structural)        # bare input file
    assert is_io_file_ref("$out", io_files, structural)          # bare output file
    assert is_io_file_ref("$anno.ref", io_files, structural)     # structural drill to a file
    assert not is_io_file_ref("$reads.ext", io_files, structural)  # metadata, not the file
    assert not is_io_file_ref("$thr", io_files, structural)      # a number, not a file
    assert not is_io_file_ref("$__tool_directory__", io_files, structural)


def test_command_var_info_folds_output_data_files_as_safe() -> None:
    """Output ``<data>`` files join ``kinds`` as ``safe`` — a single-token Galaxy
    path (the IUC rule covers output files); ``<collection>`` outputs are not files."""
    root = etree.fromstring(
        b"<tool>"
        b'<inputs><param name="reads" type="data"/>'
        b'<param name="title" type="text"/></inputs>'
        b"<outputs>"
        b'<data name="out"/>'
        b'<collection name="out_coll" type="list"/>'
        b"</outputs></tool>"
    )
    kinds, structural = command_var_info(root)
    assert kinds["out"] == "safe"  # output <data> file -> provably single-token
    assert "out_coll" not in kinds  # a collection is not a single output file
    assert kinds["reads"] == "safe"  # inputs unchanged
    assert kinds["title"] == "text"
    assert provably_quotable("$out", kinds, structural) is True


def test_command_var_info_input_wins_on_name_collision() -> None:
    """If a name is both an input (unsafe) and an output, the input kind wins."""
    root = etree.fromstring(
        b"<tool>"
        b'<inputs><param name="x" type="text"/></inputs>'
        b'<outputs><data name="x"/></outputs></tool>'
    )
    kinds, _ = command_var_info(root)
    assert kinds["x"] == "text"  # the unsafe input classification is kept


def test_input_param_info_kinds_and_structural() -> None:
    root = etree.fromstring(
        b"<tool><inputs>"
        b'<param name="ds" type="data"/>'
        b'<param name="txt" type="text"/>'
        b'<param name="multi" type="data" multiple="true"/>'
        b'<param name="coll" type="data_collection"/>'
        b'<conditional name="cond"><param name="sub" type="integer"/></conditional>'
        b'<section name="sec">'
        b'<param name="opt" type="select" multiple="true"/></section>'
        b"</inputs></tool>"
    )
    kinds, structural = input_param_info(root)
    assert kinds == {
        "ds": "safe",
        "txt": "text",
        "multi": "multi",
        "coll": "multi",
        "sub": "safe",  # integer, nested in a conditional
        "opt": "multi",  # select multiple=
    }
    assert structural == {"cond", "sec"}


def test_classify_var_buckets() -> None:
    kinds = {"ds": "safe", "txt": "text", "multi": "multi", "sub": "safe"}
    structural = {"cond", "sec"}

    def classify(name: str) -> str:
        return classify_var(name, kinds, structural)

    assert classify("$ds") == "safe"
    assert classify("$txt") == "text"
    assert classify("$multi") == "multi"
    # $param.attr splits by whether the attribute is space-free.
    assert classify("$ds.ext") == "attr_safe"
    assert classify("$ds.file_name") == "attr_safe"
    assert classify("$ds.name") == "attr_unsafe"
    assert classify("$ds.element_identifier") == "attr_unsafe"
    assert classify("$ds.metadata.foo") == "attr_unsafe"  # nested -> not provable
    # $cond.sub resolves to the leaf param's kind.
    assert classify("$cond.sub") == "safe"
    assert classify("${cond.sub}") == "safe"
    assert classify("$cond.unknownleaf") == "structured"
    # Built-ins split path (deployment-fixed) vs label (run-varying).
    assert classify("$__tool_directory__") == "builtin_path"
    assert classify("$on_string") == "builtin_label"
    assert classify("$assembled") == "non_input"


def test_select_is_safe_only_when_all_option_values_are_single_tokens() -> None:
    # A select whose every static option value is a single shell token is provably
    # single-valued -> "safe". The audit's counterexample (a multi-flag dropdown
    # whose option packs several argv words into one value) must NOT be "safe":
    # quoting it would fuse the words into one literal token.
    root = etree.fromstring(
        b"<tool><inputs>"
        b'<param name="single" type="select">'
        b'<option value="-b">b</option><option value="-h">h</option></param>'
        b'<param name="multiflag" type="select">'
        b'<option value="-b -h">bh</option><option value="-b">b</option></param>'
        b'<param name="globbed" type="select">'
        b'<option value="*.bam">all</option></param>'
        b'<param name="dynamic" type="select">'
        b'<options from_dataset="x"/></param>'
        b'<param name="noopts" type="select"/>'
        b"</inputs></tool>"
    )
    kinds, _ = input_param_info(root)
    assert kinds["single"] == "safe"  # every option value is one token
    assert kinds["multiflag"] == "text"  # "-b -h" word-splits -> not provable
    assert kinds["globbed"] == "text"  # a glob expands unquoted -> not provable
    assert kinds["dynamic"] == "text"  # runtime-sourced values -> not provable
    assert kinds["noopts"] == "text"  # nothing static to prove


def test_drill_down_is_safe_only_when_all_nested_values_are_single_tokens() -> None:
    # drill_down nests <option value=> under <options>; a static, all-single-token
    # tree is "safe", a from_file source or a whitespace value is not.
    root = etree.fromstring(
        b"<tool><inputs>"
        b'<param name="dd_ok" type="drill_down"><options>'
        b'<option name="A" value="a"><option name="B" value="b"/></option>'
        b"</options></param>"
        b'<param name="dd_space" type="drill_down"><options>'
        b'<option name="A" value="a b"/></options></param>'
        b'<param name="dd_dyn" type="drill_down"><options from_file="x.txt"/></param>'
        b"</inputs></tool>"
    )
    kinds, _ = input_param_info(root)
    assert kinds["dd_ok"] == "safe"
    assert kinds["dd_space"] == "text"
    assert kinds["dd_dyn"] == "text"


def test_boolean_is_safe_only_when_both_values_are_single_tokens() -> None:
    # A boolean's rendered value is its author-written truevalue/falsevalue, not an
    # intrinsically single token like an integer. Quoting is a no-op ONLY when both
    # are non-empty single shell tokens. The dominant Galaxy idiom
    # truevalue="--flag" falsevalue="" is NOT safe: quoting the empty false case
    # emits a stray '' argument, and a space-prefixed truevalue (" --flag") becomes
    # a literal leading-space token when quoted. Galaxy defaults truevalue/falsevalue
    # to "true"/"false" (both single tokens -> safe).
    root = etree.fromstring(
        b"<tool><inputs>"
        b'<param name="default_bool" type="boolean"/>'
        b'<param name="token_bool" type="boolean" truevalue="yes" falsevalue="no"/>'
        b'<param name="empty_false" type="boolean" truevalue="--flag" falsevalue=""/>'
        b'<param name="space_true" type="boolean" truevalue=" --flag" falsevalue=""/>'
        b'<param name="multi_true" type="boolean" truevalue="-a -b" falsevalue=""/>'
        b"</inputs></tool>"
    )
    kinds, _ = input_param_info(root)
    assert kinds["default_bool"] == "safe"  # defaults true/false -> single tokens
    assert kinds["token_bool"] == "safe"  # yes/no -> single tokens
    assert kinds["empty_false"] == "text"  # "" false -> quoting emits a stray ''
    assert kinds["space_true"] == "text"  # " --flag" -> leading space kept if quoted
    assert kinds["multi_true"] == "text"  # "-a -b" word-splits -> fused if quoted


def test_multiple_select_stays_multi_regardless_of_option_values() -> None:
    # multiple= is a deliberate splat; it outranks any option-value inspection.
    root = etree.fromstring(
        b"<tool><inputs>"
        b'<param name="opt" type="select" multiple="true">'
        b'<option value="-b">b</option></param>'
        b"</inputs></tool>"
    )
    kinds, _ = input_param_info(root)
    assert kinds["opt"] == "multi"


def test_provably_quotable_is_exactly_the_provable_set() -> None:
    kinds = {"ds": "safe", "txt": "text", "multi": "multi"}
    structural: set[str] = set()

    def quotable(name: str) -> bool:
        return provably_quotable(name, kinds, structural)

    # Provable: safe param, space-free attr, path built-in.
    assert quotable("$ds")
    assert quotable("$ds.ext")
    assert quotable("$__tool_directory__")
    # Not provable: free-form text, deliberate splat, label attr/built-in, unknown.
    assert not quotable("$txt")
    assert not quotable("$multi")
    assert not quotable("$ds.name")
    assert not quotable("$on_string")
    assert not quotable("$assembled")
