"""Tests for ``test_case_check`` — the provably-clean 24.2 test-case checker.

The checker is the toolchain's own implementation of the decision Galaxy's
strict test-case validator makes at profile 24.2, used to tighten the
``24_2_fix_test_case_validation`` detector. It is **one-directional**: it may
return ``True`` (provably clean, the gate lets the tool past 24.2) only when
every test input is provably valid under rules justified from Galaxy's model
code; anything it cannot model returns ``False`` (stays blocked). The corpus
parity oracle (``scripts.measure test-case-validation-truth``) must show zero
unsound suppressions; ``test_parity_against_real_validator`` here pins the
same agreement on the synthetic fixtures in CI.
"""

from __future__ import annotations

from lxml import etree

from galaxy_tool_codemod.test_case_check import all_test_cases_provably_clean


def _root(body: str) -> etree._Element:
    xml = f'<tool id="t" name="T" version="1.0">{body}</tool>'
    return etree.fromstring(xml.encode())


_OUT = (
    '<outputs><data name="o" format="txt"/></outputs>'
)
_CHECK = '<assert_contents><has_text text="x"/></assert_contents>'


def _tool(inputs: str, tests: str) -> etree._Element:
    return _root(
        f"<command>echo</command><inputs>{inputs}</inputs>{_OUT}"
        f"<tests>{tests}</tests>"
    )


# --- trivially clean and trivially unknown ----------------------------------------


def test_no_tests_is_clean() -> None:
    root = _root(f"<command>echo</command><inputs/>{_OUT}")
    assert all_test_cases_provably_clean(root)


def test_unknown_param_name_is_not_clean() -> None:
    root = _tool(
        '<param name="i" type="integer" value="1"/>',
        f'<test><param name="nosuch" value="2"/>'
        f'<output name="o">{_CHECK}</output></test>',
    )
    assert not all_test_cases_provably_clean(root)


# --- per-type value rules ----------------------------------------------------------


def test_integer_literal_is_clean_and_junk_is_not() -> None:
    inputs = '<param name="i" type="integer" value="1"/>'
    good = _tool(inputs, '<test><param name="i" value="-2"/></test>')
    bad = _tool(inputs, '<test><param name="i" value="abc"/></test>')
    sneaky = _tool(inputs, '<test><param name="i" value="1_0"/></test>')
    assert all_test_cases_provably_clean(good)
    assert not all_test_cases_provably_clean(bad)
    # int("1_0") == 10 in Python, but our grammar is a strict subset: not provable.
    assert not all_test_cases_provably_clean(sneaky)


def test_integer_bounds_are_enforced() -> None:
    inputs = '<param name="i" type="integer" value="5" min="1" max="10"/>'
    assert all_test_cases_provably_clean(
        _tool(inputs, '<test><param name="i" value="10"/></test>')
    )
    assert not all_test_cases_provably_clean(
        _tool(inputs, '<test><param name="i" value="11"/></test>')
    )


def test_float_literal_and_bounds() -> None:
    inputs = '<param name="f" type="float" value="0.5" min="0" max="1"/>'
    assert all_test_cases_provably_clean(
        _tool(inputs, '<test><param name="f" value="0.75"/></test>')
    )
    assert not all_test_cases_provably_clean(
        _tool(inputs, '<test><param name="f" value="1.5"/></test>')
    )
    assert not all_test_cases_provably_clean(
        _tool(inputs, '<test><param name="f" value="nan"/></test>')
    )


def test_boolean_asbool_vocabulary() -> None:
    inputs = '<param name="b" type="boolean" truevalue="--x" falsevalue=""/>'
    for value in ("true", "False", "YES", "0"):
        assert all_test_cases_provably_clean(
            _tool(inputs, f'<test><param name="b" value="{value}"/></test>')
        ), value
    # The truevalue itself is the classic mistake: asbool rejects it.
    assert not all_test_cases_provably_clean(
        _tool(inputs, '<test><param name="b" value="--x"/></test>')
    )


def test_text_value_is_clean_unless_validated() -> None:
    plain = _tool(
        '<param name="t" type="text" value=""/>',
        '<test><param name="t" value="anything at all"/></test>',
    )
    assert all_test_cases_provably_clean(plain)
    validated = _tool(
        '<param name="t" type="text" value="">'
        '<validator type="regex">x+</validator></param>',
        '<test><param name="t" value="xxx"/></test>',
    )
    # A <validator> may reject (regex/length/expression run at validation
    # time); never provable statically, so not clean.
    assert not all_test_cases_provably_clean(validated)


def test_static_select_value_membership() -> None:
    inputs = (
        '<param name="s" type="select">'
        '<option value="a">Label A</option><option value="b" selected="true">B</option>'
        "</param>"
    )
    assert all_test_cases_provably_clean(
        _tool(inputs, '<test><param name="s" value="a"/></test>')
    )
    # The label instead of the value: the 24.2 strict Literal rejects it.
    assert not all_test_cases_provably_clean(
        _tool(inputs, '<test><param name="s" value="Label A"/></test>')
    )


def test_multiple_select_splits_on_commas() -> None:
    inputs = (
        '<param name="s" type="select" multiple="true">'
        '<option value="a">A</option><option value="b">B</option>'
        "</param>"
    )
    assert all_test_cases_provably_clean(
        _tool(inputs, '<test><param name="s" value="a,b"/></test>')
    )
    assert not all_test_cases_provably_clean(
        _tool(inputs, '<test><param name="s" value="a,zzz"/></test>')
    )


def test_dynamic_select_accepts_any_provided_value() -> None:
    inputs = (
        '<param name="s" type="select">'
        '<options from_data_table="builds"><column name="value" index="0"/></options>'
        "</param>"
    )
    # Dynamic options validate as a plain string at 24.2 (no option table).
    assert all_test_cases_provably_clean(
        _tool(inputs, '<test><param name="s" value="whatever"/></test>')
    )
    # Omitted dynamic select: the no-options validator can reject None — not provable.
    assert not all_test_cases_provably_clean(_tool(inputs, "<test/>"))


def test_data_param_with_value_is_clean_and_required_must_be_present() -> None:
    inputs = '<param name="d" type="data" format="txt"/>'
    assert all_test_cases_provably_clean(
        _tool(inputs, '<test><param name="d" value="in.txt"/></test>')
    )
    # Required (non-optional) data param omitted from the test: required field.
    assert not all_test_cases_provably_clean(_tool(inputs, "<test/>"))
    optional = '<param name="d" type="data" format="txt" optional="true"/>'
    assert all_test_cases_provably_clean(_tool(optional, "<test/>"))


def test_data_column_must_be_an_integer_index() -> None:
    inputs = (
        '<param name="d" type="data" format="tabular"/>'
        '<param name="c" type="data_column" data_ref="d" value="1"/>'
    )
    assert all_test_cases_provably_clean(
        _tool(
            inputs,
            '<test><param name="d" value="x.tsv"/><param name="c" value="2"/></test>',
        )
    )
    assert not all_test_cases_provably_clean(
        _tool(
            inputs,
            '<test><param name="d" value="x.tsv"/>'
            '<param name="c" value="c2: name"/></test>',
        )
    )


def test_color_must_be_lowercase_hex() -> None:
    # Galaxy's ensure_color_valid accepts only "#" + six lowercase hex digits;
    # an uppercase value is "Invalid color", so it is not provably clean.
    inputs = '<param name="col" type="color" value="#000000"/>'
    assert all_test_cases_provably_clean(
        _tool(inputs, '<test><param name="col" value="#548dd4"/></test>')
    )
    assert not all_test_cases_provably_clean(
        _tool(inputs, '<test><param name="col" value="#FF0000"/></test>')
    )


def test_required_integer_must_appear_in_the_test() -> None:
    # Non-optional integer with NO default: the test-case field is required.
    inputs = '<param name="i" type="integer"/>'
    assert not all_test_cases_provably_clean(_tool(inputs, "<test/>"))
    with_default = '<param name="i" type="integer" value="3"/>'
    assert all_test_cases_provably_clean(_tool(with_default, "<test/>"))


# --- grouping constructs -----------------------------------------------------------


def test_conditional_when_selection_and_nested_params() -> None:
    inputs = (
        '<conditional name="c"><param name="mode" type="select">'
        '<option value="x">X</option><option value="y">Y</option></param>'
        '<when value="x"><param name="ix" type="integer" value="1"/></when>'
        '<when value="y"><param name="ty" type="text" value=""/></when>'
        "</conditional>"
    )
    nested = _tool(
        inputs,
        '<test><conditional name="c"><param name="mode" value="x"/>'
        '<param name="ix" value="7"/></conditional></test>',
    )
    assert all_test_cases_provably_clean(nested)
    piped = _tool(
        inputs,
        '<test><param name="c|mode" value="y"/><param name="c|ty" value="hi"/></test>',
    )
    assert all_test_cases_provably_clean(piped)
    bad_value = _tool(
        inputs,
        '<test><conditional name="c"><param name="mode" value="zzz"/>'
        "</conditional></test>",
    )
    assert not all_test_cases_provably_clean(bad_value)
    wrong_branch = _tool(
        inputs,
        '<test><param name="c|mode" value="x"/><param name="c|ty" value="hi"/></test>',
    )
    # ty lives under the y branch; with mode=x it is an unknown input.
    assert not all_test_cases_provably_clean(wrong_branch)


def test_section_params_resolve_through_the_section() -> None:
    inputs = (
        '<section name="adv" title="Advanced">'
        '<param name="i" type="integer" value="1"/></section>'
    )
    assert all_test_cases_provably_clean(
        _tool(
            inputs,
            '<test><section name="adv"><param name="i" value="2"/></section></test>',
        )
    )
    assert all_test_cases_provably_clean(
        _tool(inputs, '<test><param name="adv|i" value="2"/></test>')
    )
    assert not all_test_cases_provably_clean(
        _tool(inputs, '<test><param name="adv|nosuch" value="2"/></test>')
    )


def test_repeat_omitted_when_inner_has_defaults_is_clean() -> None:
    # A repeat with no `min` and a defaulted inner param: an empty test is valid
    # (Galaxy materialises zero instances), and one explicit instance validates.
    inputs = (
        '<repeat name="r" title="R">'
        '<param name="i" type="integer" value="1"/></repeat>'
    )
    assert all_test_cases_provably_clean(_tool(inputs, "<test/>"))
    assert all_test_cases_provably_clean(
        _tool(
            inputs,
            '<test><repeat name="r"><param name="i" value="5"/></repeat></test>',
        )
    )
    # Two instances, the second carries a junk integer value -> not clean.
    assert not all_test_cases_provably_clean(
        _tool(
            inputs,
            '<test><repeat name="r"><param name="i" value="5"/></repeat>'
            '<repeat name="r"><param name="i" value="abc"/></repeat></test>',
        )
    )


def test_repeat_unknown_inner_param_is_not_clean() -> None:
    inputs = (
        '<repeat name="r"><param name="i" type="integer" value="1"/></repeat>'
    )
    assert not all_test_cases_provably_clean(
        _tool(
            inputs,
            '<test><repeat name="r"><param name="i" value="1"/>'
            '<param name="nope" value="2"/></repeat></test>',
        )
    )


def test_repeat_max_count_is_enforced() -> None:
    inputs = (
        '<repeat name="r" max="1">'
        '<param name="i" type="integer" value="1"/></repeat>'
    )
    assert all_test_cases_provably_clean(
        _tool(
            inputs,
            '<test><repeat name="r"><param name="i" value="1"/></repeat></test>',
        )
    )
    # Two instances exceed max=1 -> Galaxy rejects (List max_length).
    assert not all_test_cases_provably_clean(
        _tool(
            inputs,
            '<test><repeat name="r"><param name="i" value="1"/></repeat>'
            '<repeat name="r"><param name="i" value="2"/></repeat></test>',
        )
    )


def test_repeat_min_with_required_inner_must_be_supplied() -> None:
    # min=1 and a required (no-default) inner integer: an omitted repeat pads to one
    # empty instance whose required field is missing -> Galaxy rejects.
    inputs = '<repeat name="r" min="1"><param name="i" type="integer"/></repeat>'
    assert not all_test_cases_provably_clean(_tool(inputs, "<test/>"))
    assert all_test_cases_provably_clean(
        _tool(
            inputs,
            '<test><repeat name="r"><param name="i" value="3"/></repeat></test>',
        )
    )


def test_collections_and_exotics_are_never_provable() -> None:
    collection = _tool(
        '<param name="dc" type="data_collection" collection_type="paired"/>',
        '<test><param name="dc" value="x"/></test>',
    )
    assert not all_test_cases_provably_clean(collection)
    drill = _tool(
        '<param name="dd" type="drill_down">'
        '<options><option name="a" value="a"/></options></param>',
        '<test><param name="dd" value="a"/></test>',
    )
    assert not all_test_cases_provably_clean(drill)


def test_leading_underscore_names_are_never_provable() -> None:
    # Pydantic reserves leading-underscore field names, so Galaxy's model
    # builder raises rather than validate; we cannot prove clean (regression
    # for the astro tools' `_selector` / `_data_product` conditionals).
    leading_param = _tool(
        '<param name="_x" type="integer" value="1"/>',
        '<test><param name="_x" value="2"/></test>',
    )
    assert not all_test_cases_provably_clean(leading_param)
    leading_conditional = _tool(
        '<conditional name="_c"><param name="_s" type="select">'
        '<option value="a">A</option></param>'
        '<when value="a"><param name="i" type="integer" value="1"/></when>'
        "</conditional>",
        '<test><conditional name="_c"><param name="_s" value="a"/>'
        '<param name="i" value="2"/></conditional></test>',
    )
    assert not all_test_cases_provably_clean(leading_conditional)


def test_macro_constructs_in_inputs_are_never_provable() -> None:
    # An un-expanded <expand> in <inputs> means we cannot see the full model.
    root = _tool(
        '<expand macro="common_inputs"/>',
        '<test><param name="i" value="1"/></test>',
    )
    assert not all_test_cases_provably_clean(root)


# --- parity against Galaxy's real validator (the one-directional contract) ---------

# Every (inputs, tests) shape the value-rule tests above exercise; the parity
# test holds our verdict against Galaxy's real validator on each.
_PARITY_FIXTURES: tuple[tuple[str, str], ...] = (
    (
        '<param name="i" type="integer" value="1"/>',
        '<test><param name="i" value="-2"/></test>',
    ),
    (
        '<param name="i" type="integer" value="1"/>',
        '<test><param name="i" value="abc"/></test>',
    ),
    (
        '<param name="i" type="integer" value="5" min="1" max="10"/>',
        '<test><param name="i" value="10"/></test>',
    ),
    (
        '<param name="i" type="integer" value="5" min="1" max="10"/>',
        '<test><param name="i" value="11"/></test>',
    ),
    (
        '<param name="f" type="float" value="0.5" min="0" max="1"/>',
        '<test><param name="f" value="0.75"/></test>',
    ),
    (
        '<param name="f" type="float" value="0.5" min="0" max="1"/>',
        '<test><param name="f" value="1.5"/></test>',
    ),
    (
        '<param name="b" type="boolean" truevalue="--x" falsevalue=""/>',
        '<test><param name="b" value="YES"/></test>',
    ),
    (
        '<param name="b" type="boolean" truevalue="--x" falsevalue=""/>',
        '<test><param name="b" value="--x"/></test>',
    ),
    (
        '<param name="t" type="text" value=""/>',
        '<test><param name="t" value="anything"/></test>',
    ),
    (
        '<param name="s" type="select"><option value="a">A</option>'
        '<option value="b" selected="true">B</option></param>',
        '<test><param name="s" value="a"/></test>',
    ),
    (
        '<param name="s" type="select"><option value="a">A</option>'
        '<option value="b" selected="true">B</option></param>',
        '<test><param name="s" value="A"/></test>',
    ),
    (
        '<param name="s" type="select" multiple="true">'
        '<option value="a">A</option><option value="b">B</option></param>',
        '<test><param name="s" value="a,b"/></test>',
    ),
    (
        '<param name="d" type="data" format="txt"/>',
        '<test><param name="d" value="in.txt"/></test>',
    ),
    ('<param name="d" type="data" format="txt"/>', "<test/>"),
    ('<param name="d" type="data" format="txt" optional="true"/>', "<test/>"),
    ('<param name="i" type="integer"/>', "<test/>"),
    ('<param name="i" type="integer" value="3"/>', "<test/>"),
    (
        '<param name="d" type="data" format="tabular"/>'
        '<param name="c" type="data_column" data_ref="d" value="1"/>',
        '<test><param name="d" value="x.tsv"/><param name="c" value="2"/></test>',
    ),
    (
        '<conditional name="c"><param name="mode" type="select">'
        '<option value="x">X</option><option value="y">Y</option></param>'
        '<when value="x"><param name="ix" type="integer" value="1"/></when>'
        '<when value="y"><param name="ty" type="text" value=""/></when>'
        "</conditional>",
        '<test><conditional name="c"><param name="mode" value="x"/>'
        '<param name="ix" value="7"/></conditional></test>',
    ),
    (
        '<section name="adv" title="Advanced">'
        '<param name="i" type="integer" value="1"/></section>',
        '<test><section name="adv"><param name="i" value="2"/></section></test>',
    ),
    # color casing: Galaxy rejects uppercase hex (the cp_overlay_outlines case).
    (
        '<param name="col" type="color" value="#000000"/>',
        '<test><param name="col" value="#548dd4"/></test>',
    ),
    (
        '<param name="col" type="color" value="#000000"/>',
        '<test><param name="col" value="#FF0000"/></test>',
    ),
    # repeats — the construct A2 added; each must hold against Galaxy's validator.
    (
        '<repeat name="r"><param name="i" type="integer" value="1"/></repeat>',
        "<test/>",
    ),
    (
        '<repeat name="r"><param name="i" type="integer" value="1"/></repeat>',
        '<test><repeat name="r"><param name="i" value="5"/></repeat></test>',
    ),
    (
        '<repeat name="r" max="1"><param name="i" type="integer" value="1"/></repeat>',
        '<test><repeat name="r"><param name="i" value="1"/></repeat>'
        '<repeat name="r"><param name="i" value="2"/></repeat></test>',
    ),
    (
        '<repeat name="r" min="1"><param name="i" type="integer"/></repeat>',
        "<test/>",
    ),
    (
        '<repeat name="r" min="1"><param name="i" type="integer"/></repeat>',
        '<test><repeat name="r"><param name="i" value="3"/></repeat></test>',
    ),
)


def test_parity_against_real_validator(tmp_path: object) -> None:
    """Our one-directional contract, executed: our-clean implies Galaxy-clean.

    Runs Galaxy's actual strict validator (the galaxy-tool-util dev
    dependency, the same oracle as ``scripts.measure
    test-case-validation-truth``) over every parity fixture. A fixture our
    checker calls clean that Galaxy rejects is an unsound suppression and
    fails here, in CI, before any corpus run would catch it.
    """
    from pathlib import Path

    from galaxy.tool_util.parameters.case import (
        validate_test_cases_for_tool_source,
    )
    from galaxy.tool_util.parser.factory import get_tool_source

    assert isinstance(tmp_path, Path)
    for index, (inputs, tests) in enumerate(_PARITY_FIXTURES):
        tests_with_check = tests.replace(
            "</test>", f'<output name="o">{_CHECK}</output></test>'
        )
        root = _tool(inputs, tests_with_check)
        ours = all_test_cases_provably_clean(root)
        path = tmp_path / f"fixture_{index}.xml"
        path.write_bytes(etree.tostring(root))
        try:
            results = validate_test_cases_for_tool_source(
                get_tool_source(str(path)), use_latest_profile=True
            )
            galaxy_clean = all(case.validation_error is None for case in results)
        except Exception:  # noqa: BLE001 — a raising validator reads as not-clean
            galaxy_clean = False
        assert not (ours and not galaxy_clean), (
            f"UNSOUND suppression on fixture {index}: our checker says clean, "
            f"Galaxy rejects it.\ninputs: {inputs}\ntests: {tests}"
        )
