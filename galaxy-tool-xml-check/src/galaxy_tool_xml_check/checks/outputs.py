"""Output-correctness advisory checks."""


from __future__ import annotations

import ast
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
    _CHEETAH_PLACEHOLDER,
    _IUC,
    _param_name,
    _violation,
)


def _named_outputs(root: etree._Element, /) -> Iterable[etree._Element]:
    """Each top-level output ``<data>`` / ``<collection>`` (direct ``<outputs>`` child).

    Deliberately *not* recursive: a ``<data>`` nested inside a ``<collection>`` is a
    structural child in the collection's own namespace, not an independently-named
    top-level output. Matching planemo's direct-child scan keeps these checks from
    over-flagging — the failure mode for a detect-only advisory on novel XML.
    """
    outputs = root.find("outputs")
    if outputs is None:
        return
    for element in outputs:
        if element.tag in ("data", "collection"):
            yield element


class OutputNamesUnique(CheckRule):
    """GTR040 — output ``<data>`` / ``<collection>`` names must be unique.

    Reimplements planemo `OutputsNameDuplicated` (`galaxy.tool_util.linters.output`).
    A duplicate name means one output silently shadows another. Detect-only.
    """

    meta: ClassVar[RuleMeta] = RuleMeta(
        code="GTR040",
        summary="Output <data>/<collection> names must be unique.",
        since="0.0.1",
        cite=_IUC,
        detect_only=True,
        rulesets=frozenset({"strict"}),
        planemo_linters=frozenset({"OutputsNameDuplicated"}),
    )

    def detect(self, document: ToolDocument, /) -> Iterable[Violation]:
        seen: set[str] = set()
        for output in _named_outputs(document.root):
            name = output.get("name")
            if name is None:
                continue
            if name in seen:
                yield _violation(
                    document, output, self.meta, f"duplicate output name '{name}'"
                )
            seen.add(name)


class OutputNameValid(CheckRule):
    """GTR041 — an output ``name`` must be a valid Cheetah placeholder.

    Reimplements planemo `OutputsNameInvalidCheetah`. A name that is not a valid
    placeholder (``^[a-zA-Z_]\\w*$``) cannot be referenced as ``$name``. Detect-only.
    """

    meta: ClassVar[RuleMeta] = RuleMeta(
        code="GTR041",
        summary="Output name should be a valid Cheetah placeholder.",
        since="0.0.1",
        cite=_IUC,
        detect_only=True,
        rulesets=frozenset({"strict"}),
        planemo_linters=frozenset({"OutputsNameInvalidCheetah"}),
    )

    def detect(self, document: ToolDocument, /) -> Iterable[Violation]:
        for output in _named_outputs(document.root):
            name = output.get("name")
            if name is not None and not _CHEETAH_PLACEHOLDER.match(name):
                yield _violation(
                    document,
                    output,
                    self.meta,
                    f"output name '{name}' is not a valid Cheetah placeholder",
                )


class CollectionTypeDeclared(CheckRule):
    """GTR042 — an output ``<collection>`` should declare its structure ``type``.

    Reimplements planemo `OutputsCollectionType`. Lenient vs planemo: a collection that
    derives its structure from ``type_source`` / ``structured_like`` is accepted (those
    are valid ways to supply the type), so only a collection with *none* of them is
    flagged. Detect-only.
    """

    meta: ClassVar[RuleMeta] = RuleMeta(
        code="GTR042",
        summary="Output <collection> should declare a structure 'type'.",
        since="0.0.1",
        cite=_IUC,
        detect_only=True,
        rulesets=frozenset({"strict"}),
        planemo_linters=frozenset({"OutputsCollectionType"}),
    )

    def detect(self, document: ToolDocument, /) -> Iterable[Violation]:
        for output in _named_outputs(document.root):
            if output.tag != "collection":
                continue
            if not any(
                output.get(attr) is not None
                for attr in ("type", "type_source", "structured_like")
            ):
                yield _violation(
                    document, output, self.meta, "collection output has no 'type'"
                )


class OutputFormatSourceExclusive(CheckRule):
    """GTR043 — an output should not set both ``format_source`` and ``format``/``ext``.

    Reimplements planemo `OutputsFormatSourceIncomp`. ``format_source`` derives the
    datatype from another dataset; combining it with an explicit ``format``/``ext`` is
    contradictory. Detect-only.
    """

    meta: ClassVar[RuleMeta] = RuleMeta(
        code="GTR043",
        summary="An output should not set both format_source and format/ext.",
        since="0.0.1",
        cite=_IUC,
        detect_only=True,
        rulesets=frozenset({"strict"}),
        planemo_linters=frozenset({"OutputsFormatSourceIncomp"}),
    )

    def detect(self, document: ToolDocument, /) -> Iterable[Violation]:
        for output in _named_outputs(document.root):
            has_source = output.get("format_source") is not None
            has_explicit = (
                output.get("format") is not None or output.get("ext") is not None
            )
            if has_source and has_explicit:
                yield _violation(
                    document,
                    output,
                    self.meta,
                    "output sets both format_source and format/ext (contradictory)",
                )


# Galaxy's named ``<discover_datasets>`` patterns whose expansion captures the file
# extension (``galaxy.tool_util.parser.output_collection_def.NAMED_PATTERNS`` +
# ``DEFAULT_EXTRA_FILENAME_PATTERN``). A named pattern resolves to a regex, so — like
# planemo's ``_check_pattern`` — we resolve it before looking for the ``(?P<ext>…)``
# capture. ``__name__`` / ``__designation__`` resolve to regexes that do *not* capture
# ext, so they are deliberately absent.
_EXT_CAPTURING_PATTERNS = frozenset(
    {"__default__", "__name_and_ext__", "__designation_and_ext__"}
)


def _tool_provides_metadata(root: etree._Element, /) -> bool:
    """Whether the tool supplies output datatypes at runtime via ``galaxy.json``.

    Mirrors planemo's ``_has_tool_provided_metadata``: a ``provided_metadata_*`` on
    ``<outputs>``, a ``<command>`` that writes ``galaxy.json``, or a ``galaxy.json``
    ``<configfile>``. When present, outputs need not declare a static format, so GTR049
    exempts the whole tool. The ``command.text`` access is LBYL-guarded — on the raw
    tree a macro-supplied ``<command>`` can be empty.
    """
    outputs = root.find("outputs")
    if outputs is not None and (
        outputs.get("provided_metadata_file") is not None
        or outputs.get("provided_metadata_style") is not None
    ):
        return True
    command = root.find("command")
    if command is not None and command.text and "galaxy.json" in command.text:
        return True
    return root.find("configfiles/configfile[@filename='galaxy.json']") is not None


def _output_format_defined(output: etree._Element, /) -> bool:
    """Whether *output* (a top-level ``<data>``/``<collection>``) defines its format.

    Mirrors planemo `OutputsFormat`'s ``_check_format`` / ``_check_pattern``: an
    explicit ``format``/``ext``/``format_source``, a ``<action type="format">``, a
    ``data`` ``auto_format``, a ``collection`` ``structured_like`` + ``inherit_format``,
    or a ``<discover_datasets>`` whose ``pattern`` (resolving named patterns) captures
    ``(?P<ext>…)``.
    """
    if (
        output.get("format") is not None
        or output.get("ext") is not None
        or output.get("format_source") is not None
    ):
        return True
    if output.find(".//action[@type='format']") is not None:
        return True
    if output.tag == "data" and output.get("auto_format"):
        return True
    if (
        output.tag == "collection"
        and output.get("structured_like") is not None
        and output.get("inherit_format") is not None
    ):
        return True
    for sub in output:
        if (
            sub.get("format") is not None
            or sub.get("ext") is not None
            or sub.get("format_source") is not None
        ):
            return True
        if sub.tag == "discover_datasets":
            pattern = sub.get("pattern") or ""
            if pattern in _EXT_CAPTURING_PATTERNS or "(?P<ext>" in pattern:
                return True
    return False


class OutputsPresent(CheckRule):
    """GTR048 — the tool should define an ``<outputs>`` section.

    Reimplements planemo `OutputsMissing`, `galaxy.tool_util.linters.output`. Most tools
    produce outputs. A macro-using tool is **skipped**: a top-level ``<expand>`` may
    inject ``<outputs>`` from an imported macro, and this tier reads the raw tree (the
    GTR044 soundness boundary). Detect-only.
    """

    meta: ClassVar[RuleMeta] = RuleMeta(
        code="GTR048",
        summary="Tool should define an <outputs> section.",
        since="0.0.1",
        cite=_IUC,
        detect_only=True,
        rulesets=frozenset({"strict"}),
        planemo_linters=frozenset({"OutputsMissing"}),
    )

    def detect(self, document: ToolDocument, /) -> Iterable[Violation]:
        root = document.root
        if root.find("outputs") is None and not has_macros(root):
            yield _violation(document, root, self.meta, "no <outputs> section")


class OutputFormatDefined(CheckRule):
    """GTR049 — each output should define its datatype format.

    Reimplements planemo `OutputsFormat`. An output ``<data>``/``<collection>`` with
    none of ``format``/``ext``/``format_source``/a format ``<action>``/``auto_format``/
    ``structured_like`` + ``inherit_format``/an ext-capturing ``<discover_datasets>``
    defaults to the generic ``data`` type. A tool that supplies datatypes at runtime via
    ``galaxy.json`` is exempt (planemo's tool-provided-metadata gate). An output whose
    subtree contains an ``<expand>`` is **skipped** — a macro may inject the
    format-defining structure (the GTR044 raw-tree boundary). Detect-only.
    """

    meta: ClassVar[RuleMeta] = RuleMeta(
        code="GTR049",
        summary="Each output should define its datatype format.",
        since="0.0.1",
        cite=_IUC,
        detect_only=True,
        rulesets=frozenset({"strict"}),
        planemo_linters=frozenset({"OutputsFormat"}),
    )

    def detect(self, document: ToolDocument, /) -> Iterable[Violation]:
        root = document.root
        if _tool_provides_metadata(root):
            return
        for output in _named_outputs(root):
            if output.find(".//expand") is not None:
                continue
            if not _output_format_defined(output):
                name = output.get("name") or "with missing name"
                yield _violation(
                    document,
                    output,
                    self.meta,
                    f"{output.tag} output '{name}' defines no format",
                )


class OutputLabelsDistinct(CheckRule):
    """GTR050 — outputs should not share an explicit ``label``.

    Reimplements planemo `OutputsLabelDuplicatedFilter` +
    `OutputsLabelDuplicatedNoFilter`, narrowed to **explicit** labels: two outputs that
    both omit ``label`` collide on
    Galaxy's default (``${tool.name} on ${on_string}``), but that is normal — Galaxy
    disambiguates by name — so flagging it (as planemo does, on 390 corpus tools vs 104
    for explicit duplicates) is noise. A repeated *explicit* label is the genuinely
    ambiguous case. Outputs with a ``<filter>`` may legitimately reuse a label across
    disjoint conditional branches, so the message says to double-check rather than
    asserting a defect. Detect-only.
    """

    meta: ClassVar[RuleMeta] = RuleMeta(
        code="GTR050",
        summary="Outputs should not share an explicit label.",
        since="0.0.1",
        cite=_IUC,
        detect_only=True,
        rulesets=frozenset({"strict"}),
        planemo_linters=frozenset(
            {
                "OutputsLabelDuplicatedFilter",
                "OutputsLabelDuplicatedNoFilter",
            }
        ),
    )

    def detect(self, document: ToolDocument, /) -> Iterable[Violation]:
        seen: set[str] = set()
        for output in _named_outputs(document.root):
            label = output.get("label")
            if label is None:
                continue
            if label in seen:
                name = output.get("name") or "with missing name"
                if output.find("filter") is not None:
                    message = (
                        f"output '{name}' reuses label '{label}' — check the "
                        "<filter>s cover disjoint cases"
                    )
                else:
                    message = f"output '{name}' reuses label '{label}'"
                yield _violation(document, output, self.meta, message)
            seen.add(label)


def _is_python_eval(expression: str, /) -> bool:
    """Whether *expression* parses as a Python ``eval`` expression.

    ``ast.parse`` has no LBYL validity predicate, so the narrow ``except`` is the
    sanctioned third-party boundary (mirrors ``_is_pep440``). ``SyntaxError`` covers a
    malformed expression; ``ValueError`` covers exotic inputs (e.g. null bytes).
    """
    try:
        ast.parse(expression, mode="eval")
    except (SyntaxError, ValueError):
        return False
    return True


class OutputFilterValid(CheckRule):
    """GTR052 — an output ``<filter>`` should be a valid Python expression.

    Reimplements planemo `OutputsFilterExpression`, `galaxy.tool_util.linters.output`. A
    ``<filter>`` body is a Python expression Galaxy evaluates to decide whether the
    output is produced; a malformed one raises at runtime. A filter carrying a ``@…@``
    token is **skipped** — it is a template fragment, not yet a Python expression (the
    GTR045 raw-tree boundary). Detect-only.
    """

    meta: ClassVar[RuleMeta] = RuleMeta(
        code="GTR052",
        summary="An output <filter> should be a valid Python expression.",
        since="0.0.1",
        cite=_IUC,
        detect_only=True,
        rulesets=frozenset({"strict"}),
        planemo_linters=frozenset({"OutputsFilterExpression"}),
    )

    def detect(self, document: ToolDocument, /) -> Iterable[Violation]:
        outputs = document.root.find("outputs")
        if outputs is None:
            return
        for output_filter in outputs.findall(".//filter"):
            expression = (output_filter.text or "").strip()
            if not expression or "@" in expression:
                continue
            if not _is_python_eval(expression):
                yield _violation(
                    document,
                    output_filter,
                    self.meta,
                    f"output filter {expression!r} is not a valid expression",
                )


def _param_qualified_paths(root: etree._Element, /) -> dict[str, list[str]]:
    """Unqualified param name -> its qualified ``a|b`` path(s) (planemo's collector).

    A qualified path prefixes only ``conditional``/``section`` ancestor names — a
    ``repeat`` contributes nothing (faithful to planemo's ``_get_qualified_name``).
    """
    paths: dict[str, list[str]] = {}
    parent_map = {child: parent for parent in root.iter() for child in parent}
    for param in root.findall("./inputs//param"):
        name = _param_name(param)
        if name is None:
            continue
        parts = [name]
        current: etree._Element = param
        while True:
            parent = parent_map.get(current)
            if parent is None:
                break
            if parent.tag in ("conditional", "section"):
                parent_name = parent.get("name")
                if parent_name:
                    parts.insert(0, str(parent_name))
            elif parent.tag in ("inputs", "tool"):
                break
            current = parent
        paths.setdefault(name, []).append("|".join(parts))
    return paths


class OutputReferencesValid(CheckRule):
    """GTR090 — output ``structured_like``/``format_source`` must reference an input.

    Reimplements planemo `OutputsStructuredLikeReference` +
    `OutputsFormatSourceReference`:
    a ``<collection structured_like=…>`` / ``<data|collection format_source=…>``
    reference must resolve — to a top-level input param (or, for ``format_source``,
    a sibling output); an unqualified reference to a *nested* param is flagged (use
    the ``cond|param`` qualified spelling), an ambiguous one likewise, and an
    unresolvable one is a dangling reference. A ``|``-qualified reference is not
    validated (faithful to planemo). A macro-using tool is **skipped**: an
    ``<expand>`` may supply the referenced param or output the raw tree cannot see
    (the GTR044 soundness boundary; 254 of the 360 corpus tools carrying such a
    reference). Detect-only.
    """

    meta: ClassVar[RuleMeta] = RuleMeta(
        code="GTR090",
        summary="Output structured_like/format_source must reference an input param.",
        since="0.0.1",
        cite=_IUC,
        detect_only=True,
        rulesets=frozenset({"strict"}),
        planemo_linters=frozenset(
            {"OutputsFormatSourceReference", "OutputsStructuredLikeReference"}
        ),
    )

    def detect(self, document: ToolDocument, /) -> Iterable[Violation]:
        root = document.root
        if has_macros(root):
            return
        references = [
            (output, str(output.get("structured_like")), "structured_like")
            for output in root.findall("outputs/collection[@structured_like]")
        ]
        output_names = {
            output.get("name")
            for output in root.findall("outputs/data[@name]")
            + root.findall("outputs/collection[@name]")
        }
        for output in root.findall("outputs/data[@format_source]") + root.findall(
            "outputs/collection[@format_source]"
        ):
            reference = str(output.get("format_source"))
            # format_source may also name a sibling output (planemo skips those).
            if reference in output_names:
                continue
            references.append((output, reference, "format_source"))
        if not references:
            return
        paths = _param_qualified_paths(root)
        for output, reference, attr in references:
            if "|" in reference:
                continue
            if any(qp == reference for plist in paths.values() for qp in plist):
                continue  # a top-level param resolves it directly
            matches = paths.get(reference, [])
            output_name = output.get("name") or "?"
            if len(matches) == 1:
                message = (
                    f"output '{output_name}': unqualified {attr}='{reference}' — "
                    f"use the qualified name '{matches[0]}'"
                )
            elif matches:
                message = (
                    f"output '{output_name}': ambiguous unqualified "
                    f"{attr}='{reference}' (matches {', '.join(matches)})"
                )
            else:
                message = (
                    f"output '{output_name}': {attr}='{reference}' does not match "
                    "any input parameter"
                )
            yield _violation(document, output, self.meta, message)
