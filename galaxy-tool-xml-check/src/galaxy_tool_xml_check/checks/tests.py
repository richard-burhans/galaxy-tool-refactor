"""``<tests>`` advisory checks."""


from __future__ import annotations

from collections.abc import Iterable
from typing import TYPE_CHECKING, ClassVar

from galaxy_tool_refactor_rules.meta import RuleMeta
from galaxy_tool_refactor_rules.violation import Violation
from galaxy_tool_xml.macros import has_macros
from lxml import etree

from galaxy_tool_xml_check.rules import CheckRule

if TYPE_CHECKING:
    from galaxy_tool_xml.document import ToolDocument

from galaxy_tool_xml_check.checks._shared import (
    _IUC,
    _string_as_bool,
    _violation,
)

# Assertion elements live under an assert_contents/stdout/stderr/command block.
_ASSERT_BLOCK_XPATH = (
    ".//*[self::assert_contents or self::assert_stdout or self::assert_stderr "
    "or self::assert_command]//*"
)

# Output-comparison attributes and the ``compare`` modes each is valid with (planemo's
# ``TestsOutputCompareAttrib`` ``COMPARE_COMPATIBILITY``).
_COMPARE_COMPATIBILITY: dict[str, frozenset[str]] = {
    "sort": frozenset({"diff", "re_match", "re_match_multiline"}),
    "lines_diff": frozenset({"diff", "re_match", "contains"}),
    "decompress": frozenset({"diff"}),
    "delta": frozenset({"sim_size"}),
    "delta_frac": frozenset({"sim_size"}),
    "metric": frozenset({"image_diff"}),
    "eps": frozenset({"image_diff"}),
}


class TestAssertionsWellFormed(CheckRule):
    """GTR080 — a ``<test>``'s assertions must be well formed.

    Reimplements planemo `TestsAssertsMultiple` (at most one ``assert_stdout`` /
    ``assert_stderr`` / ``assert_command`` per test), `TestsAssertsHasNQuant`
    (``has_n_lines`` / ``has_n_columns`` need ``n`` / ``min`` / ``max``),
    `TestsAssertsHasSizeQuant` (``has_size`` needs ``size`` / ``value`` / ``min`` /
    ``max``) and `TestsAssertsHasSizeOrValueQuant` (``has_size`` must not set both
    ``value`` and ``size``). Detect-only.
    """

    meta: ClassVar[RuleMeta] = RuleMeta(
        code="GTR080",
        summary="A <test>'s assertions must be well formed.",
        since="0.0.1",
        cite=_IUC,
        detect_only=True,
    )

    def detect(self, document: ToolDocument, /) -> Iterable[Violation]:
        for index, test in enumerate(document.root.findall("tests/test"), start=1):
            for assert_tag in ("assert_stdout", "assert_stderr", "assert_command"):
                if len(test.findall(assert_tag)) > 1:
                    yield _violation(
                        document,
                        test,
                        self.meta,
                        f"test {index}: more than one <{assert_tag}> (only the first "
                        "is used)",
                    )
            for assertion in test.xpath(_ASSERT_BLOCK_XPATH):
                attrs = set(assertion.attrib)
                if assertion.tag in ("has_n_lines", "has_n_columns") and not (
                    attrs & {"n", "min", "max"}
                ):
                    yield _violation(
                        document,
                        assertion,
                        self.meta,
                        f"test {index}: <{assertion.tag}> needs 'n', 'min', or 'max'",
                    )
                elif assertion.tag == "has_size":
                    if not (attrs & {"value", "size", "min", "max"}):
                        yield _violation(
                            document,
                            assertion,
                            self.meta,
                            f"test {index}: <has_size> needs 'size', 'min', or 'max'",
                        )
                    if "value" in attrs and "size" in attrs:
                        yield _violation(
                            document,
                            assertion,
                            self.meta,
                            f"test {index}: <has_size> must not set both 'value' and "
                            "'size'",
                        )


class TestOutputCompareAttributes(CheckRule):
    """GTR081 — a test output's attributes must agree with its ``compare`` mode.

    Reimplements planemo `TestsOutputCompareAttrib`: ``sort`` / ``lines_diff`` /
    ``decompress`` / ``delta`` / ``delta_frac`` / ``metric`` / ``eps`` are each valid
    only with specific ``compare`` modes (default ``diff``). Detect-only.
    """

    meta: ClassVar[RuleMeta] = RuleMeta(
        code="GTR081",
        summary="A test output's attributes must agree with its compare mode.",
        since="0.0.1",
        cite=_IUC,
        detect_only=True,
    )

    def detect(self, document: ToolDocument, /) -> Iterable[Violation]:
        for index, test in enumerate(document.root.findall("tests/test"), start=1):
            for output in test.xpath(
                ".//*[self::output or self::element or self::discovered_dataset]"
            ):
                compare = output.get("compare", "diff")
                for attr, allowed in _COMPARE_COMPATIBILITY.items():
                    if attr in output.attrib and compare not in allowed:
                        yield _violation(
                            document,
                            output,
                            self.meta,
                            f"test {index}: attribute '{attr}' is incompatible with "
                            f"compare='{compare}'",
                        )


def _declared_output_map(root: etree._Element, /) -> dict[str, etree._Element]:
    """name → output element for the single ``<outputs>`` block (planemo's
    ``_collect_output_names``). Empty if there isn't exactly one ``<outputs>``."""
    outputs = root.findall("outputs")
    result: dict[str, etree._Element] = {}
    if len(outputs) == 1:
        for output in list(outputs[0]):
            name = output.get("name")
            if name:
                result[name] = output
    return result


class TestOutputNamed(CheckRule):
    """GTR082 — a ``<test>`` ``<output>`` must declare a ``name``.

    Reimplements planemo `TestsOutputName` (``<output_collection>`` names are
    XSD-required). Detect-only.
    """

    meta: ClassVar[RuleMeta] = RuleMeta(
        code="GTR082",
        summary="A test <output> must declare a name.",
        since="0.0.1",
        cite=_IUC,
        detect_only=True,
    )

    def detect(self, document: ToolDocument, /) -> Iterable[Violation]:
        for index, test in enumerate(document.root.findall("tests/test"), start=1):
            for output in test.findall("output"):
                if not output.get("name"):
                    yield _violation(
                        document,
                        output,
                        self.meta,
                        f"test {index}: <output> has no name",
                    )


class TestOutputsCorrespond(CheckRule):
    """GTR083 — a test output must name a declared output of the matching kind.

    Reimplements planemo `TestsOutputDefined` (the name is a declared output),
    `TestsOutputCorresponding` (a test ``<output>`` corresponds to a ``<data>``) and
    `TestsOutputCollectionCorresponding` (a ``<output_collection>`` corresponds to a
    ``<collection>``). The *unknown-name* case is **skipped** for a macro-using tool —
    the declared-output set is incomplete on the raw tree (the GTR079 boundary);
    correspondence is still checked for names that do resolve. Detect-only.
    """

    meta: ClassVar[RuleMeta] = RuleMeta(
        code="GTR083",
        summary="A test output must name a declared output of the matching kind.",
        since="0.0.1",
        cite=_IUC,
        detect_only=True,
    )

    def detect(self, document: ToolDocument, /) -> Iterable[Violation]:
        root = document.root
        declared = _declared_output_map(root)
        macros = has_macros(root)
        for index, test in enumerate(root.findall("tests/test"), start=1):
            test_outputs = list(test.findall("output")) + list(
                test.findall("output_collection")
            )
            for output in test_outputs:
                name = output.get("name")
                if not name:
                    continue
                if name not in declared:
                    if not macros:
                        yield _violation(
                            document,
                            output,
                            self.meta,
                            f"test {index}: {output.tag} '{name}' is not a declared "
                            "output",
                        )
                    continue
                corresponding = declared[name]
                if output.tag == "output" and corresponding.tag != "data":
                    yield _violation(
                        document,
                        output,
                        self.meta,
                        f"test {index}: <output> '{name}' corresponds to a "
                        f"'{corresponding.tag}', expected a <data>",
                    )
                elif output.tag == "output_collection" and corresponding.tag != (
                    "collection"
                ):
                    yield _violation(
                        document,
                        output,
                        self.meta,
                        f"test {index}: <output_collection> '{name}' corresponds to a "
                        f"'{corresponding.tag}', expected a <collection>",
                    )


class TestDiscoveredOutputsChecked(CheckRule):
    """GTR084 — a test of a discovering output must assert on the discovered datasets.

    Reimplements planemo `TestsOutputCheckDiscovered` (a test ``<output>`` for a tool
    output with ``<discover_datasets>`` needs ``count``/``min``/``max`` or
    ``<discovered_dataset>`` children), `TestsOutputCollectionCheckDiscovered` (a
    ``<output_collection>`` needs ``count``/``min``/``max`` or ``<element>`` children)
    and `TestsOutputCollectionCheckDiscoveredNested` (a ``list:list`` / ``list:paired``
    collection needs nested ``<element>`` tags or element children with
    ``count``/``min``/``max``). Only resolved output names are checked, so a
    macro-supplied output simply under-reports. Detect-only.
    """

    meta: ClassVar[RuleMeta] = RuleMeta(
        code="GTR084",
        summary="A discovering output's test must assert on the discovered datasets.",
        since="0.0.1",
        cite=_IUC,
        detect_only=True,
    )

    def detect(self, document: ToolDocument, /) -> Iterable[Violation]:
        declared = _declared_output_map(document.root)
        for index, test in enumerate(document.root.findall("tests/test"), start=1):
            for output in test.findall("output"):
                corresponding = self._discovering_output(output, declared)
                if corresponding is None:
                    continue
                if not (set(output.attrib) & {"count", "min", "max"}) and (
                    output.find("discovered_dataset") is None
                ):
                    yield _violation(
                        document,
                        output,
                        self.meta,
                        f"test {index}: output '{output.get('name')}' discovers "
                        "datasets — assert 'count'/'min'/'max' or list "
                        "<discovered_dataset> children",
                    )
            for output in test.findall("output_collection"):
                corresponding = self._discovering_output(output, declared)
                if corresponding is None:
                    continue
                if not (set(output.attrib) & {"count", "min", "max"}) and (
                    output.find("element") is None
                ):
                    yield _violation(
                        document,
                        output,
                        self.meta,
                        f"test {index}: collection '{output.get('name')}' discovers "
                        "datasets — assert 'count'/'min'/'max' or list <element> "
                        "children",
                    )
                if corresponding.get("type", "") in ("list:list", "list:paired"):
                    has_nested = output.find("element/element") is not None
                    counted = output.xpath("./element[@count or @min or @max]")
                    if not has_nested and not counted:
                        yield _violation(
                            document,
                            output,
                            self.meta,
                            f"test {index}: nested collection "
                            f"'{output.get('name')}' must assert nested <element> tags "
                            "or element children with 'count'/'min'/'max'",
                        )

    @staticmethod
    def _discovering_output(
        test_output: etree._Element, declared: dict[str, etree._Element], /
    ) -> etree._Element | None:
        """The declared output for *test_output* if it discovers datasets, else None."""
        name = test_output.get("name")
        if not name or name not in declared:
            return None
        corresponding = declared[name]
        if corresponding.find(".//discover_datasets") is None:
            return None
        return corresponding


def _test_param_resolves(name: str, names: set[str], arguments: set[str], /) -> bool:
    """Whether a test param *name* matches a tool input by name or argument variants.

    Mirrors planemo `TestsParamInInputs`: an input ``name`` equal to *name*, or an input
    ``argument`` equal to *name* / ``-name`` / ``--name`` (and ``_``→``-`` variants).
    """
    if name in names:
        return True
    candidates = {name, f"-{name}", f"--{name}"}
    if "_" in name:
        dashed = name.replace("_", "-")
        candidates |= {dashed, f"-{dashed}", f"--{dashed}"}
    return bool(candidates & arguments)


def _test_has_expectations(test: etree._Element, /) -> bool | None:
    """planemo's ``_iter_tests`` validity: whether *test* asserts anything.

    A test is valid if it has an ``expect_failure``/``expect_exit_code``/
    ``expect_num_outputs`` attribute, an ``assert_stdout``/``stderr``/``command`` block,
    or an ``<output>``/``<output_collection>``. Returns ``None`` for the malformed
    ``expect_failure`` + outputs/expect_num_outputs case (GTR086 owns that).
    """
    valid = bool(
        set(test.attrib) & {"expect_failure", "expect_exit_code", "expect_num_outputs"}
    )
    if any(
        test.find(tag) is not None
        for tag in ("assert_stdout", "assert_stderr", "assert_command")
    ):
        valid = True
    found_output = (
        test.find("output") is not None or test.find("output_collection") is not None
    )
    if _string_as_bool(test.get("expect_failure", "false")) and (
        found_output or "expect_num_outputs" in test.attrib
    ):
        return None
    return valid or found_output


class TestParamsInInputs(CheckRule):
    """GTR085 — a ``<test>`` ``<param>`` must name a tool input.

    Reimplements planemo `TestsParamInInputs` (matching by input ``name`` or
    ``argument`` variants). A macro-using tool is **skipped** — the input set is
    incomplete on the raw tree, so a test param referencing a macro-supplied input
    can't be proven absent (the
    GTR079 boundary). Detect-only.
    """

    meta: ClassVar[RuleMeta] = RuleMeta(
        code="GTR085",
        summary="A test <param> must name a tool input.",
        since="0.0.1",
        cite=_IUC,
        detect_only=True,
    )

    def detect(self, document: ToolDocument, /) -> Iterable[Violation]:
        root = document.root
        if has_macros(root):
            return
        inputs = root.find("inputs")
        if inputs is None:
            return
        names: set[str] = set()
        arguments: set[str] = set()
        for param in inputs.iterfind(".//param"):
            name = param.get("name")
            if name:
                names.add(name)
            argument = param.get("argument")
            if argument:
                arguments.add(argument)
        for index, test in enumerate(root.findall("tests/test"), start=1):
            for param in test.findall("param"):
                raw_name = param.get("name")
                if not raw_name:
                    continue
                name = raw_name.split("|")[-1]
                if not _test_param_resolves(name, names, arguments):
                    yield _violation(
                        document,
                        param,
                        self.meta,
                        f"test {index}: param '{name}' is not in the tool inputs",
                    )


class TestExpectFailureCoherent(CheckRule):
    """GTR086 — an ``expect_failure`` ``<test>`` must not assert outputs.

    Reimplements planemo `TestsOutputFailing` (a failing test cannot define
    ``<output>``/``<output_collection>``) + `TestsExpectNumOutputsFailing` (nor set
    ``expect_num_outputs``). Detect-only.
    """

    meta: ClassVar[RuleMeta] = RuleMeta(
        code="GTR086",
        summary="An expect_failure test must not assert outputs.",
        since="0.0.1",
        cite=_IUC,
        detect_only=True,
    )

    def detect(self, document: ToolDocument, /) -> Iterable[Violation]:
        for index, test in enumerate(document.root.findall("tests/test"), start=1):
            if not _string_as_bool(test.get("expect_failure", "false")):
                continue
            if (
                test.find("output") is not None
                or test.find("output_collection") is not None
            ):
                yield _violation(
                    document,
                    test,
                    self.meta,
                    f"test {index}: an expect_failure test cannot define outputs",
                )
            elif "expect_num_outputs" in test.attrib:
                yield _violation(
                    document,
                    test,
                    self.meta,
                    f"test {index}: an expect_failure test cannot set "
                    "expect_num_outputs",
                )


class TestExpectNumOutputs(CheckRule):
    """GTR087 — a ``<test>`` should set ``expect_num_outputs`` for filtered outputs.

    Reimplements planemo `TestsExpectNumOutputs`: if any output has a ``<filter>``, each
    non-failure test should set ``expect_num_outputs`` (so the variable output count is
    pinned). Detect-only.
    """

    meta: ClassVar[RuleMeta] = RuleMeta(
        code="GTR087",
        summary="A test should set expect_num_outputs when outputs are filtered.",
        since="0.0.1",
        cite=_IUC,
        detect_only=True,
    )

    def detect(self, document: ToolDocument, /) -> Iterable[Violation]:
        root = document.root
        has_filter = (
            root.find("outputs/data/filter") is not None
            or root.find("outputs/collection/filter") is not None
        )
        if not has_filter:
            return
        for index, test in enumerate(root.findall("tests/test"), start=1):
            if "expect_num_outputs" in test.attrib:
                continue
            if _string_as_bool(test.get("expect_failure", "false")):
                continue
            yield _violation(
                document,
                test,
                self.meta,
                f"test {index}: should set 'expect_num_outputs' (an output has a "
                "<filter>)",
            )


class TestHasExpectations(CheckRule):
    """GTR088 — a ``<test>`` should assert outputs or expectations.

    Reimplements planemo `TestsHasExpectations` (a test with no ``<output>`` /
    ``<output_collection>`` / assert block / ``expect_*`` attribute is likely invalid).
    Subsumes planemo `TestsValid` (the tool-level "no valid test" warning is conveyed by
    flagging each empty test). Detect-only.
    """

    meta: ClassVar[RuleMeta] = RuleMeta(
        code="GTR088",
        summary="A test should assert outputs or expectations.",
        since="0.0.1",
        cite=_IUC,
        detect_only=True,
    )

    def detect(self, document: ToolDocument, /) -> Iterable[Violation]:
        for index, test in enumerate(document.root.findall("tests/test"), start=1):
            if _test_has_expectations(test) is False:
                yield _violation(
                    document,
                    test,
                    self.meta,
                    f"test {index}: defines no outputs or expectations",
                )
