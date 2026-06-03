"""Tests for the command-var quoting-safety classifier (GTX020 / IUC011 substrate)."""

from __future__ import annotations

from lxml import etree

from galaxy_tool_xml.command_vars import (
    classify_var,
    input_param_info,
    provably_quotable,
)


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
