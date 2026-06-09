"""Input-parameter advisory checks (naming, select, type, display, filters)."""


from __future__ import annotations

from collections.abc import Iterable
from functools import lru_cache
from typing import TYPE_CHECKING, ClassVar

from galaxy_tool_refactor_rules.meta import RuleMeta
from galaxy_tool_refactor_rules.violation import Violation
from galaxy_tool_xml.cheetah_refs import referenced_identifiers
from galaxy_tool_xml.macros import expand_from_tree, has_macros
from lxml import etree

from galaxy_tool_xml_check.rules import CheckRule

if TYPE_CHECKING:
    from galaxy_tool_xml.document import ToolDocument

from galaxy_tool_xml_check.checks._shared import (
    _CHEETAH_PLACEHOLDER,
    _IUC,
    _is_valid_regex,
    _param_name,
    _string_as_bool,
    _violation,
)


class UnusedParam(CheckRule):
    """GTR034 — an ``<inputs>`` ``<param>`` never referenced anywhere the tool uses it.

    A general code-quality advisory (an unused param is dead wiring / cruft). Sound by
    conservative over-counting: a param is flagged only if its name appears in **none**
    of the tool's references — neither a Cheetah ``$name`` / ``$cond.name`` use nor any
    by-name cross-reference attribute (``data_ref``, ``format_source``,
    ``change_format @input``, options ``filter @ref``, …). The reference set is the
    shared ``cheetah_refs.referenced_identifiers``, which subsumes every such attribute
    generically (there is no positional or free-text param linking in Galaxy tool XML).
    References are read from the **macro-expanded** tree so a param used only inside an
    ``<expand>`` body is not falsely flagged; if expansion fails the check **bails**
    (reports nothing). Excluded: a ``<conditional>`` **selector** ``<param>``
    (structurally used by its ``<when>`` branches) and macro-supplied params (only
    author-written ``<param>``\\ s are candidates). See ``docs/decisions.md`` D11.
    """

    meta: ClassVar[RuleMeta] = RuleMeta(
        code="GTR034",
        summary="Input <param> is never referenced in the tool.",
        since="0.0.1",
        cite=_IUC,
        detect_only=True,
        rulesets=frozenset({"strict"}),
    )

    def detect(self, document: ToolDocument, /) -> Iterable[Violation]:
        inputs = document.root.find("inputs")
        if inputs is None:
            return
        used = self._used_identifiers(document)
        if used is None:
            return  # macro expansion failed — bail rather than risk a false positive
        for param in inputs.iter("param"):
            name = param.get("name")
            if not name:
                continue
            parent = param.getparent()
            if parent is not None and parent.tag == "conditional":
                continue  # the conditional's selector param is structurally used
            if name not in used:
                yield _violation(
                    document,
                    param,
                    self.meta,
                    f'input <param name="{name}"> is never referenced',
                )

    def _used_identifiers(self, document: ToolDocument, /) -> set[str] | None:
        """Identifiers referenced across the macro-expanded tree, or ``None`` if a
        macro-using tool's expansion fails (the caller then bails)."""
        root = document.root
        if not has_macros(root):
            return referenced_identifiers(root)
        source_dir = document.source_path.parent if document.source_path else None
        expanded, errors = expand_from_tree(root, source_dir=source_dir)
        if expanded is None or errors:
            return None
        return referenced_identifiers(expanded.getroot())


def _iter_named_params(
    root: etree._Element, /
) -> Iterable[tuple[etree._Element, str]]:
    """Each ``<inputs>`` descendant ``<param>`` with its resolved name.

    Skips a param declaring neither ``name`` nor ``argument`` (the GTR054 case),
    matching planemo's ``_iter_param``. Macro-injected params are invisible on the raw
    tree, so
    these checks under-report rather than misfire (the GTR044/GTR045 boundary).
    """
    inputs = root.find("inputs")
    if inputs is None:
        return
    for param in inputs.iterfind(".//param"):
        name = _param_name(param)
        if name is not None:
            yield param, name


def _param_qualified_path(param: etree._Element, name: str, /) -> str:
    """planemo's ``_param_path``: *name* qualified by the enclosing structure.

    Walks parents up to ``<inputs>``, prepending each ``<when>``'s ``value`` (so
    identically-named params in disjoint conditional branches do not collide) or other
    containers' ``name``. The dotted path is the identity planemo dedups on.
    """
    path = [name]
    current = param
    while True:
        parent = current.getparent()
        if parent is None or parent.tag == "inputs":
            break
        if parent.tag == "when":
            path.append(str(parent.get("value")))
        else:
            path.append(str(parent.get("name")))
        current = parent
    return ".".join(reversed(path))


class ParamNamePresent(CheckRule):
    """GTR054 — an input ``<param>`` must declare a ``name`` or ``argument``.

    Reimplements planemo `InputsName`, `galaxy.tool_util.linters.inputs`. Galaxy derives
    a param's identity from ``name`` or, failing that, ``argument``; a param with
    neither cannot be referenced. Detect-only.
    """

    meta: ClassVar[RuleMeta] = RuleMeta(
        code="GTR054",
        summary="An input <param> must declare a name or argument.",
        since="0.0.1",
        cite=_IUC,
        detect_only=True,
        rulesets=frozenset({"strict"}),
        planemo_linters=frozenset({"InputsName"}),
    )

    def detect(self, document: ToolDocument, /) -> Iterable[Violation]:
        inputs = document.root.find("inputs")
        if inputs is None:
            return
        for param in inputs.iterfind(".//param"):
            if param.get("name") is None and param.get("argument") is None:
                yield _violation(
                    document,
                    param,
                    self.meta,
                    "param has neither 'name' nor 'argument'",
                )


class ParamNameValid(CheckRule):
    """GTR055 — an input ``<param>`` name must be a non-empty Cheetah placeholder.

    Reimplements planemo `InputsNameEmpty` + `InputsNameValid` (planemo itself notes the
    two overlap). The resolved name must be non-empty and match ``^[a-zA-Z_]\\w*$`` so
    it can be referenced as ``$name``. A name carrying a ``@…@`` macro token is skipped
    (the raw-tree boundary, cf. GTR045). Detect-only.
    """

    meta: ClassVar[RuleMeta] = RuleMeta(
        code="GTR055",
        summary="An input <param> name must be a valid Cheetah placeholder.",
        since="0.0.1",
        cite=_IUC,
        detect_only=True,
        rulesets=frozenset({"strict"}),
        planemo_linters=frozenset({"InputsNameEmpty", "InputsNameValid"}),
    )

    def detect(self, document: ToolDocument, /) -> Iterable[Violation]:
        for param, name in _iter_named_params(document.root):
            if name.strip() == "":
                yield _violation(document, param, self.meta, "param has an empty name")
            elif "@" not in name and not _CHEETAH_PLACEHOLDER.match(name):
                yield _violation(
                    document,
                    param,
                    self.meta,
                    f"param name '{name}' is not a valid Cheetah placeholder",
                )


class ParamNamesUnique(CheckRule):
    """GTR056 — input ``<param>`` names must be unique within their scope.

    Reimplements planemo `InputsNameDuplicate`. Two params sharing a qualified path
    (name + enclosing conditional/section structure) clash; identically-named params in
    disjoint ``<when>`` branches are fine (the path differs). Detect-only.
    """

    meta: ClassVar[RuleMeta] = RuleMeta(
        code="GTR056",
        summary="Input <param> names must be unique within their scope.",
        since="0.0.1",
        cite=_IUC,
        detect_only=True,
        rulesets=frozenset({"strict"}),
        planemo_linters=frozenset({"InputsNameDuplicate"}),
    )

    def detect(self, document: ToolDocument, /) -> Iterable[Violation]:
        seen: set[str] = set()
        for param, name in _iter_named_params(document.root):
            path = _param_qualified_path(param, name)
            if path in seen:
                yield _violation(
                    document, param, self.meta, f"duplicate parameter name '{path}'"
                )
            seen.add(path)


class InputOutputNamesDistinct(CheckRule):
    """GTR057 — an output name must not duplicate an input parameter name.

    Reimplements planemo `InputsNameDuplicateOutput`. An output sharing a name with an
    input parameter collides in the Cheetah/job namespace. Detect-only.
    """

    meta: ClassVar[RuleMeta] = RuleMeta(
        code="GTR057",
        summary="An output name must not duplicate an input parameter name.",
        since="0.0.1",
        cite=_IUC,
        detect_only=True,
        rulesets=frozenset({"strict"}),
        planemo_linters=frozenset({"InputsNameDuplicateOutput"}),
    )

    def detect(self, document: ToolDocument, /) -> Iterable[Violation]:
        root = document.root
        input_paths = {
            _param_qualified_path(param, name)
            for param, name in _iter_named_params(root)
        }
        outputs = root.find("outputs")
        if outputs is None:
            return
        for output in outputs:
            name = output.get("name")
            if name is not None and name in input_paths:
                yield _violation(
                    document,
                    output,
                    self.meta,
                    f"output name '{name}' collides with an input parameter",
                )


@lru_cache(maxsize=1)
def _select_params(root: etree._Element, /) -> tuple[tuple[etree._Element, str], ...]:
    """Each input ``<param type="select">`` with its resolved name.

    Memoised for the *current* root only (``maxsize=1``): the seven select checks
    (GTR058–GTR064) each scan the same document in one ``detect_violations`` pass,
    so the param subtree is walked once and reused six times. A re-iterable tuple
    (not a generator) so every caller sees the full result; ``maxsize=1`` bounds
    memory to one document and, by holding the root reference, rules out any
    ``id``-reuse stale hit when the next document is scanned.
    """
    return tuple(
        (param, name)
        for param, name in _iter_named_params(root)
        if param.get("type") == "select"
    )


class SelectOptionsDefined(CheckRule):
    """GTR058 — a ``select`` parameter must define its options exactly one valid way.

    Reimplements planemo `InputsSelectOptionsDef` + `InputsSelectOptionsDefConditional`.
    A top-level select must use **exactly one** of ``<option>`` children, an
    ``<options>`` element, or the ``dynamic_options`` attribute; a select controlling a
    ``<conditional>`` must use ``<option>`` children only. A select whose subtree has an
    ``<expand>`` is **skipped** — a macro may inject the options (the raw-tree boundary,
    cf. GTR044). Detect-only.
    """

    meta: ClassVar[RuleMeta] = RuleMeta(
        code="GTR058",
        summary="A select parameter must define its options exactly one valid way.",
        since="0.0.1",
        cite=_IUC,
        detect_only=True,
        rulesets=frozenset({"strict"}),
        planemo_linters=frozenset(
            {
                "InputsSelectOptionsDef",
                "InputsSelectOptionsDefConditional",
            }
        ),
    )

    def detect(self, document: ToolDocument, /) -> Iterable[Violation]:
        for param, name in _select_params(document.root):
            if param.find(".//expand") is not None:
                continue  # a macro may inject <option>/<options>
            dynamic = param.get("dynamic_options") is not None
            options = param.findall("options")
            select_options = param.findall("option")
            parent = param.getparent()
            if parent is not None and parent.tag == "conditional":
                if not select_options or dynamic or options:
                    yield _violation(
                        document,
                        param,
                        self.meta,
                        f"select parameter '{name}' in a conditional must define "
                        "options via <option> children",
                    )
            else:
                ways = (1 if dynamic else 0) + (1 if options else 0) + (
                    1 if select_options else 0
                )
                if ways != 1:
                    yield _violation(
                        document,
                        param,
                        self.meta,
                        f"select parameter '{name}' must define options exactly one "
                        "way (<option> children, an <options> element, or "
                        "dynamic_options)",
                    )


class SelectOptionValuePresent(CheckRule):
    """GTR059 — a static ``select`` ``<option>`` must carry a ``value``.

    Reimplements planemo `InputsSelectOptionValueMissing`. An ``<option>`` with no
    ``value`` cannot be selected. Detect-only.
    """

    meta: ClassVar[RuleMeta] = RuleMeta(
        code="GTR059",
        summary="A static select <option> must carry a value.",
        since="0.0.1",
        cite=_IUC,
        detect_only=True,
        rulesets=frozenset({"strict"}),
        planemo_linters=frozenset({"InputsSelectOptionValueMissing"}),
    )

    def detect(self, document: ToolDocument, /) -> Iterable[Violation]:
        for param, name in _select_params(document.root):
            if any(option.get("value") is None for option in param.findall("option")):
                yield _violation(
                    document,
                    param,
                    self.meta,
                    f"select parameter '{name}' has an <option> without a value",
                )


class SelectOptionsDistinct(CheckRule):
    """GTR060 — a ``select``'s static options should be distinct.

    Reimplements planemo `InputsSelectOptionDuplicateValue` +
    `InputsSelectOptionDuplicateText`.
    Duplicate ``(value, selected)`` or ``(text, selected)`` pairs make options
    indistinguishable; matching planemo, an option's text defaults to its
    ``value.capitalize()`` when the body is empty. Detect-only.
    """

    meta: ClassVar[RuleMeta] = RuleMeta(
        code="GTR060",
        summary="A select's static options should have distinct values and text.",
        since="0.0.1",
        cite=_IUC,
        detect_only=True,
        rulesets=frozenset({"strict"}),
        planemo_linters=frozenset(
            {
                "InputsSelectOptionDuplicateText",
                "InputsSelectOptionDuplicateValue",
            }
        ),
    )

    def detect(self, document: ToolDocument, /) -> Iterable[Violation]:
        for param, name in _select_params(document.root):
            options = param.findall("option")
            values = [
                (option.get("value", ""), option.get("selected", "false"))
                for option in options
            ]
            if len(set(values)) != len(values):
                yield _violation(
                    document,
                    param,
                    self.meta,
                    f"select parameter '{name}' has options with duplicate values",
                )
            texts = [
                (
                    option.text
                    if option.text is not None
                    else option.get("value", "").capitalize(),
                    option.get("selected", "false"),
                )
                for option in options
            ]
            if len(set(texts)) != len(texts):
                yield _violation(
                    document,
                    param,
                    self.meta,
                    f"select parameter '{name}' has options with duplicate text",
                )


# Attributes by which a dynamic ``<options>`` element can supply its option source
# (planemo `InputsSelectOptionsDefinesOptions`); a
# ``<filter type="add_value|data_meta">`` also supplies options.
_OPTIONS_SOURCE_ATTRS = (
    "from_file",
    "from_parameter",
    "from_dataset",
    "from_data_table",
    "from_url",
)
# Deprecated ``<options>`` attributes (planemo `InputsSelectOptionsDeprecatedAttr`).
_DEPRECATED_OPTIONS_ATTRS = (
    "from_file",
    "from_parameter",
    "options_filter_attribute",
    "transform_lines",
)


class SelectOptionsSingle(CheckRule):
    """GTR061 — a ``select`` may have at most one ``<options>`` element.

    Reimplements planemo `InputsSelectOptionsMultiple`. Multiple ``<options>`` are
    ambiguous. Detect-only.
    """

    meta: ClassVar[RuleMeta] = RuleMeta(
        code="GTR061",
        summary="A select may have at most one <options> element.",
        since="0.0.1",
        cite=_IUC,
        detect_only=True,
        rulesets=frozenset({"strict"}),
        planemo_linters=frozenset({"InputsSelectOptionsMultiple"}),
    )

    def detect(self, document: ToolDocument, /) -> Iterable[Violation]:
        for param, name in _select_params(document.root):
            options = param.findall("options")
            if len(options) > 1:
                yield _violation(
                    document,
                    options[1],
                    self.meta,
                    f"select parameter '{name}' has multiple <options> elements",
                )


class SelectOptionsHaveSource(CheckRule):
    """GTR062 — a dynamic ``<options>`` must define an option source.

    Reimplements planemo `InputsSelectOptionsDefinesOptions`. An ``<options>`` with no
    ``from_*`` source attribute and no ``<filter type="add_value|data_meta">`` produces
    no options. An ``<options>`` whose subtree has an ``<expand>`` is **skipped** — a
    macro may inject the source/filter (the raw-tree boundary, cf. GTR058). Detect-only.
    """

    meta: ClassVar[RuleMeta] = RuleMeta(
        code="GTR062",
        summary="A dynamic <options> element must define an option source.",
        since="0.0.1",
        cite=_IUC,
        detect_only=True,
        rulesets=frozenset({"strict"}),
        planemo_linters=frozenset({"InputsSelectOptionsDefinesOptions"}),
    )

    def detect(self, document: ToolDocument, /) -> Iterable[Violation]:
        for param, name in _select_params(document.root):
            options = param.find("options")
            if options is None or options.find(".//expand") is not None:
                continue
            has_source = any(
                options.get(attr) is not None for attr in _OPTIONS_SOURCE_ATTRS
            )
            adds_options = any(
                option_filter.get("type") in ("add_value", "data_meta")
                for option_filter in options.findall("filter")
            )
            if not has_source and not adds_options:
                yield _violation(
                    document,
                    options,
                    self.meta,
                    f"select parameter '{name}' <options> defines no option source",
                )


class SelectOptionsSourceCoherent(CheckRule):
    """GTR063 — a dynamic ``<options>`` source combination must be coherent.

    Reimplements planemo `InputsSelectOptionsFromDatasetAndDatatable` +
    `InputsSelectOptionsMetaFileKey`: ``from_dataset`` and ``from_data_table`` are
    mutually exclusive, and ``meta_file_key`` is only meaningful with ``from_dataset``.
    Detect-only.
    """

    meta: ClassVar[RuleMeta] = RuleMeta(
        code="GTR063",
        summary="A dynamic <options> source combination must be coherent.",
        since="0.0.1",
        cite=_IUC,
        detect_only=True,
        rulesets=frozenset({"strict"}),
        planemo_linters=frozenset(
            {
                "InputsSelectOptionsFromDatasetAndDatatable",
                "InputsSelectOptionsMetaFileKey",
            }
        ),
    )

    def detect(self, document: ToolDocument, /) -> Iterable[Violation]:
        for param, name in _select_params(document.root):
            options = param.find("options")
            if options is None:
                continue
            from_dataset = options.get("from_dataset")
            if from_dataset is not None and options.get("from_data_table") is not None:
                yield _violation(
                    document,
                    options,
                    self.meta,
                    f"select parameter '{name}' <options> sets both from_dataset and "
                    "from_data_table",
                )
            if options.get("meta_file_key") is not None and from_dataset is None:
                yield _violation(
                    document,
                    options,
                    self.meta,
                    f"select parameter '{name}' <options> meta_file_key requires "
                    "from_dataset",
                )


class SelectOptionsNotDeprecated(CheckRule):
    """GTR064 — a ``select`` should not use a deprecated options mechanism.

    Reimplements planemo `InputsSelectDynamicOptions` (the ``dynamic_options`` attr)
    + `InputsSelectOptionsDeprecatedAttr` (``from_file`` / ``from_parameter`` /
    ``options_filter_attribute`` / ``transform_lines`` on ``<options>``). These need
    restructuring (e.g. a data table); advisory, not mechanically fixable. Detect-only.
    """

    meta: ClassVar[RuleMeta] = RuleMeta(
        code="GTR064",
        summary="A select should not use a deprecated options mechanism.",
        since="0.0.1",
        cite=_IUC,
        detect_only=True,
        rulesets=frozenset({"strict"}),
        planemo_linters=frozenset(
            {
                "InputsSelectDynamicOptions",
                "InputsSelectOptionsDeprecatedAttr",
            }
        ),
    )

    def detect(self, document: ToolDocument, /) -> Iterable[Violation]:
        for param, name in _select_params(document.root):
            if param.get("dynamic_options") is not None:
                yield _violation(
                    document,
                    param,
                    self.meta,
                    f"select parameter '{name}' uses the deprecated "
                    "'dynamic_options' attribute",
                )
            options = param.find("options")
            if options is None:
                continue
            for attr in _DEPRECATED_OPTIONS_ATTRS:
                if options.get(attr) is not None:
                    yield _violation(
                        document,
                        options,
                        self.meta,
                        f"select parameter '{name}' <options> uses the deprecated "
                        f"'{attr}' attribute",
                    )


def _iter_conditionals(
    root: etree._Element, /
) -> Iterable[tuple[etree._Element, etree._Element, str | None]]:
    """Each ``<inputs>//conditional`` with its first ``<param>`` and that param's type.

    Mirrors planemo's ``_iter_conditional``: skips a ``value_from`` conditional (the
    upload tool's, which has no ``<when>`` children) and a conditional whose first child
    ``<param>`` is absent (e.g. macro-supplied — invisible on the raw tree).
    """
    inputs = root.find("inputs")
    if inputs is None:
        return
    for conditional in inputs.iterfind(".//conditional"):
        if conditional.get("value_from"):
            continue
        first_param = conditional.find("param")
        if first_param is None:
            continue
        yield conditional, first_param, first_param.get("type")


class ConditionalTestParamType(CheckRule):
    """GTR069 — a ``<conditional>``'s first ``<param>`` should be a ``select``.

    Reimplements planemo `ConditionalParamType` (the test param must be ``select`` or
    ``boolean``) + `ConditionalParamTypeBool` (a ``boolean`` test param is discouraged —
    a ``select`` is preferred). Detect-only.
    """

    meta: ClassVar[RuleMeta] = RuleMeta(
        code="GTR069",
        summary="A conditional's first <param> should be a select.",
        since="0.0.1",
        cite=_IUC,
        detect_only=True,
        rulesets=frozenset({"strict"}),
        planemo_linters=frozenset({"ConditionalParamType", "ConditionalParamTypeBool"}),
    )

    def detect(self, document: ToolDocument, /) -> Iterable[Violation]:
        for conditional, first_param, ptype in _iter_conditionals(document.root):
            name = conditional.get("name") or "with missing name"
            if ptype not in ("boolean", "select"):
                yield _violation(
                    document,
                    first_param,
                    self.meta,
                    f"conditional '{name}' test param should be type 'select'",
                )
            elif ptype == "boolean":
                yield _violation(
                    document,
                    first_param,
                    self.meta,
                    f"conditional '{name}' boolean test param is discouraged; "
                    "use a select",
                )


class ConditionalTestParamAttributes(CheckRule):
    """GTR070 — a ``<conditional>``'s test param must not be optional/multiple.

    Reimplements planemo `ConditionalParamIncompatibleAttributes`: the ``select`` /
    ``boolean`` test param of a conditional cannot be ``optional="true"`` or
    ``multiple="true"``. Detect-only.
    """

    meta: ClassVar[RuleMeta] = RuleMeta(
        code="GTR070",
        summary="A conditional's test param must not be optional or multiple.",
        since="0.0.1",
        cite=_IUC,
        detect_only=True,
        rulesets=frozenset({"strict"}),
        planemo_linters=frozenset({"ConditionalParamIncompatibleAttributes"}),
    )

    def detect(self, document: ToolDocument, /) -> Iterable[Violation]:
        for conditional, first_param, ptype in _iter_conditionals(document.root):
            if ptype not in ("boolean", "select"):
                continue
            name = conditional.get("name") or "with missing name"
            for attr in ("optional", "multiple"):
                if _string_as_bool(first_param.get(attr, False)):
                    yield _violation(
                        document,
                        first_param,
                        self.meta,
                        f"conditional '{name}' test param cannot be {attr}=\"true\"",
                    )


class ConditionalWhensMatchOptions(CheckRule):
    """GTR071 — a ``<conditional>``'s ``<when>`` blocks must match the test options.

    Reimplements planemo `ConditionalWhenMissing` (every test-param option needs a
    ``<when>``) + `ConditionalOptionMissing` / `ConditionalOptionMissingBoolean` (every
    ``<when>`` needs a matching option / ``truevalue``/``falsevalue``). The option set
    is the ``select``'s ``<option value=…>`` values or the ``boolean``'s
    ``truevalue``/``falsevalue``. A conditional whose subtree has an ``<expand>`` is
    **skipped** — a macro may supply the options/whens (the raw-tree boundary).
    Detect-only.
    """

    meta: ClassVar[RuleMeta] = RuleMeta(
        code="GTR071",
        summary="A conditional's <when> blocks must match the test-param options.",
        since="0.0.1",
        cite=_IUC,
        detect_only=True,
        rulesets=frozenset({"strict"}),
        planemo_linters=frozenset(
            {
                "ConditionalOptionMissing",
                "ConditionalOptionMissingBoolean",
                "ConditionalWhenMissing",
            }
        ),
    )

    def detect(self, document: ToolDocument, /) -> Iterable[Violation]:
        for conditional, first_param, ptype in _iter_conditionals(document.root):
            if ptype not in ("boolean", "select"):
                continue
            if conditional.find(".//expand") is not None:
                continue  # a macro may supply options/whens
            name = conditional.get("name") or "with missing name"
            if ptype == "select":
                option_ids = {
                    option.get("value")
                    for option in first_param.findall("./option[@value]")
                }
            else:
                option_ids = {
                    first_param.get("truevalue", "true"),
                    first_param.get("falsevalue", "false"),
                }
            when_ids = {
                when.get("value")
                for when in conditional.findall("./when[@value]")
                if when.get("value") is not None
            }
            for missing_when in option_ids - when_ids:
                yield _violation(
                    document,
                    conditional,
                    self.meta,
                    f"conditional '{name}': no <when> block for option "
                    f"'{missing_when}'",
                )
            label = "truevalue/falsevalue" if ptype == "boolean" else "<option>"
            for missing_option in when_ids - option_ids:
                yield _violation(
                    document,
                    conditional,
                    self.meta,
                    f"conditional '{name}': no {label} for <when value="
                    f"'{missing_option}'>",
                )


# Galaxy's valid parameter-type → child-element combinations (planemo's
# ``PARAM_TYPE_CHILD_COMBINATIONS``): a child at the path is only valid for the listed
# param types.
_PARAM_TYPE_CHILDREN: tuple[tuple[str, frozenset[str]], ...] = (
    ("options", frozenset({"data", "select", "drill_down"})),
    ("options/option", frozenset({"drill_down"})),
    ("options/column", frozenset({"data", "select"})),
)


def _is_datasource(root: etree._Element, /) -> bool:
    """Whether the tool is a data-source tool (planemo's ``is_datasource``)."""
    return root.get("tool_type", "") in ("data_source", "data_source_async")


def _iter_named_typed_params(
    root: etree._Element, /
) -> Iterable[tuple[etree._Element, str, str]]:
    """Each named ``<inputs>//param`` with a non-empty ``type`` (planemo's
    ``_iter_param_type``), as ``(param, name, type)``."""
    for param, name in _iter_named_params(root):
        ptype = param.get("type")
        if ptype:
            yield param, name, str(ptype)


class InputsPresent(CheckRule):
    """GTR072 — most tools should define input parameters.

    Reimplements planemo `InputsMissing`. A tool with no ``<inputs>//param`` (and not a
    ``data_source`` tool) usually indicates a missing inputs section. A macro-using tool
    is **skipped** — a top-level ``<expand>`` may inject the params (the GTR044 raw-tree
    boundary). Detect-only.
    """

    meta: ClassVar[RuleMeta] = RuleMeta(
        code="GTR072",
        summary="Most tools should define input parameters.",
        since="0.0.1",
        cite=_IUC,
        detect_only=True,
        rulesets=frozenset({"strict"}),
        planemo_linters=frozenset({"InputsMissing"}),
    )

    def detect(self, document: ToolDocument, /) -> Iterable[Violation]:
        root = document.root
        inputs = root.find("inputs")
        num_params = len(inputs.findall(".//param")) if inputs is not None else 0
        if num_params == 0 and not _is_datasource(root) and not has_macros(root):
            yield _violation(
                document,
                inputs if inputs is not None else root,
                self.meta,
                "tool defines no input parameters",
            )


class ParamTypeChildCombination(CheckRule):
    """GTR073 — a ``<param>`` child element must be valid for the param type.

    Reimplements planemo `InputsTypeChildCombination`: ``<options>`` is only valid for
    ``data`` / ``select`` / ``drill_down`` params, ``<options><option>`` only for
    ``drill_down``, and ``<options><column>`` only for ``data`` / ``select``.
    Detect-only.
    """

    meta: ClassVar[RuleMeta] = RuleMeta(
        code="GTR073",
        summary="A <param> child element must be valid for the param type.",
        since="0.0.1",
        cite=_IUC,
        detect_only=True,
        rulesets=frozenset({"strict"}),
        planemo_linters=frozenset({"InputsTypeChildCombination"}),
    )

    def detect(self, document: ToolDocument, /) -> Iterable[Violation]:
        for param, name, ptype in _iter_named_typed_params(document.root):
            for child_path, allowed in _PARAM_TYPE_CHILDREN:
                if param.find(child_path) is not None and ptype not in allowed:
                    yield _violation(
                        document,
                        param,
                        self.meta,
                        f"parameter '{name}': '{child_path}' child is not valid for a "
                        f"'{ptype}' param",
                    )


class DataOptionsValid(CheckRule):
    """GTR074 — a ``data`` param's ``<options>`` (metadata filtering) must be valid.

    Reimplements planemo `InputsDataOptionsMultiple` (one ``<options>``), `…Attrib`
    (only ``options_filter_attribute`` is a valid attribute), `…FilterAttribFiltersType`
    (with ``options_filter_attribute`` the filters must be ``type="data_meta"``),
    `…FiltersType` (without it filters must be ``key="dbkey" type="data_meta"``), and
    `…FiltersRef` (every filter needs a ``ref``). Faithful to planemo's strictness —
    e.g. an ``add_value`` filter or a missing ``ref`` in a data param's ``<options>`` is
    flagged. Detect-only.
    """

    meta: ClassVar[RuleMeta] = RuleMeta(
        code="GTR074",
        summary="A data param's <options> (metadata filtering) must be valid.",
        since="0.0.1",
        cite=_IUC,
        detect_only=True,
        rulesets=frozenset({"strict"}),
        planemo_linters=frozenset({"InputsDataOptionsMultiple"}),
    )

    def detect(self, document: ToolDocument, /) -> Iterable[Violation]:
        for param, name, ptype in _iter_named_typed_params(document.root):
            if ptype != "data":
                continue
            all_options = param.findall("options")
            if len(all_options) > 1:
                yield _violation(
                    document,
                    all_options[1],
                    self.meta,
                    f"data parameter '{name}' has multiple <options> elements",
                )
            options = param.find("options")
            if options is None:
                continue
            has_filter_attr = "options_filter_attribute" in options.attrib
            for attr in options.attrib:
                if attr != "options_filter_attribute":
                    yield _violation(
                        document,
                        param,
                        self.meta,
                        f"data parameter '{name}' <options> has invalid attribute "
                        f"'{attr}'",
                    )
            for option_filter in param.findall("options/filter"):
                ftype = option_filter.get("type")
                if has_filter_attr:
                    if ftype != "data_meta":
                        yield _violation(
                            document,
                            option_filter,
                            self.meta,
                            f"data parameter '{name}' filter must be type='data_meta' "
                            f"(found '{ftype}')",
                        )
                elif option_filter.get("key") != "dbkey" or ftype != "data_meta":
                    yield _violation(
                        document,
                        option_filter,
                        self.meta,
                        f"data parameter '{name}' filter must be key='dbkey' "
                        "type='data_meta'",
                    )
                if not option_filter.get("ref"):
                    yield _violation(
                        document,
                        option_filter,
                        self.meta,
                        f"data parameter '{name}' filter needs a 'ref' attribute",
                    )


# Param types whose ``display`` ("checkboxes"/"radio") interacts with multiple/optional.
_DISPLAY_PARAM_TYPES = frozenset({"select", "data_column", "drill_down"})


class BooleanValuesDistinct(CheckRule):
    """GTR075 — a ``boolean`` param's true/false values must be sane.

    Reimplements planemo `InputsBoolDistinctValues` (``truevalue`` and ``falsevalue``
    must differ) + `InputsBoolProblematic` (``truevalue`` should not read as a false
    value, and vice versa). planemo's severity depends on the profile; this report-only
    tier flags it regardless. Detect-only.
    """

    meta: ClassVar[RuleMeta] = RuleMeta(
        code="GTR075",
        summary="A boolean param's truevalue/falsevalue must be distinct and sane.",
        since="0.0.1",
        cite=_IUC,
        detect_only=True,
        rulesets=frozenset({"strict"}),
        planemo_linters=frozenset(
            {
                "InputsBoolDistinctValues",
                "InputsBoolProblematic",
            }
        ),
    )

    def detect(self, document: ToolDocument, /) -> Iterable[Violation]:
        for param, name, ptype in _iter_named_typed_params(document.root):
            if ptype != "boolean":
                continue
            truevalue = str(param.get("truevalue", "true"))
            falsevalue = str(param.get("falsevalue", "false"))
            if truevalue == falsevalue:
                yield _violation(
                    document,
                    param,
                    self.meta,
                    f"boolean parameter '{name}' has identical truevalue/falsevalue "
                    f"'{truevalue}'",
                )
            if truevalue.lower() == "false":
                yield _violation(
                    document,
                    param,
                    self.meta,
                    f"boolean parameter '{name}' truevalue '{truevalue}' reads as a "
                    "false value",
                )
            if falsevalue.lower() == "true":
                yield _violation(
                    document,
                    param,
                    self.meta,
                    f"boolean parameter '{name}' falsevalue '{falsevalue}' reads as a "
                    "true value",
                )


class SelectDisplayConsistent(CheckRule):
    """GTR076 — a select's ``display`` must agree with ``multiple``/``optional``.

    Reimplements planemo `InputsSelectSingleCheckboxes` +
    `InputsSelectMandatoryCheckboxes` (``display="checkboxes"`` needs ``multiple`` *and*
    ``optional``) + `InputsSelectMultipleRadio` + `InputsSelectOptionalRadio`
    (``display="radio"`` is incompatible with ``multiple`` or ``optional``). Applies to
    ``select`` / ``data_column`` / ``drill_down``. ``optional`` defaults to ``multiple``
    when unset, per Galaxy. Detect-only.
    """

    meta: ClassVar[RuleMeta] = RuleMeta(
        code="GTR076",
        summary="A select's display must agree with multiple/optional.",
        since="0.0.1",
        cite=_IUC,
        detect_only=True,
        rulesets=frozenset({"strict"}),
        planemo_linters=frozenset(
            {
                "InputsSelectMandatoryCheckboxes",
                "InputsSelectMultipleRadio",
                "InputsSelectOptionalRadio",
                "InputsSelectSingleCheckboxes",
            }
        ),
    )

    def detect(self, document: ToolDocument, /) -> Iterable[Violation]:
        for param, name, ptype in _iter_named_typed_params(document.root):
            if ptype not in _DISPLAY_PARAM_TYPES:
                continue
            display = param.get("display")
            if display not in ("checkboxes", "radio"):
                continue
            multiple = _string_as_bool(param.get("multiple", "false"))
            optional = _string_as_bool(param.get("optional", multiple))
            if display == "checkboxes":
                if not multiple:
                    yield _violation(
                        document,
                        param,
                        self.meta,
                        f"select '{name}' display=checkboxes needs multiple=true",
                    )
                if not optional:
                    yield _violation(
                        document,
                        param,
                        self.meta,
                        f"select '{name}' display=checkboxes needs optional=true",
                    )
            else:  # radio
                if multiple:
                    yield _violation(
                        document,
                        param,
                        self.meta,
                        f"select '{name}' display=radio is incompatible with "
                        "multiple=true",
                    )
                if optional:
                    yield _violation(
                        document,
                        param,
                        self.meta,
                        f"select '{name}' display=radio is incompatible with "
                        "optional=true",
                    )


# Galaxy's per-filter-type required attributes (planemo ``FILTER_REQUIRED_ATTRIBUTES``).
# ``remove_value`` carries only ``type`` here; its real requirement is the one-of rule
# in ``_remove_value_filter_ok``.
_FILTER_REQUIRED_ATTRS: dict[str, tuple[str, ...]] = {
    "data_meta": ("type", "ref", "key"),
    "param_value": ("type", "ref", "column"),
    "static_value": ("type", "column", "value"),
    "regexp": ("type", "column", "value"),
    "unique_value": ("type", "column"),
    "multiple_splitter": ("type", "column"),
    "attribute_value_splitter": ("type", "column"),
    "add_value": ("type", "value"),
    "remove_value": ("type",),
    "sort_by": ("type", "column"),
    "data_table": ("type", "column", "table_name", "data_table_column"),
}

# Required attributes plus the optional ones allowed (``FILTER_ALLOWED_ATTRIBUTES``).
_FILTER_ALLOWED_ATTRS: dict[str, frozenset[str]] = {
    "data_meta": frozenset(
        {"type", "ref", "key", "column", "multiple", "separator"}
    ),
    "param_value": frozenset({"type", "ref", "column", "keep", "ref_attribute"}),
    "static_value": frozenset({"type", "column", "value", "keep"}),
    "regexp": frozenset({"type", "column", "value", "keep"}),
    "unique_value": frozenset({"type", "column"}),
    "multiple_splitter": frozenset({"type", "column", "separator"}),
    "attribute_value_splitter": frozenset(
        {"type", "column", "pair_separator", "name_val_separator"}
    ),
    "add_value": frozenset({"type", "value", "name", "index"}),
    "remove_value": frozenset({"type", "value", "ref", "meta_ref", "key"}),
    "sort_by": frozenset({"type", "column", "reverse_sort_order"}),
    "data_table": frozenset(
        {"type", "column", "table_name", "data_table_column", "keep"}
    ),
}


def _iter_option_filters(
    root: etree._Element, /
) -> Iterable[tuple[str, etree._Element]]:
    """Each ``<param>``'s ``<options>/<filter>`` with the param name.

    Any named param carrying an ``<options>`` element (planemo iterates all params, not
    only ``select``/``data``). Macro-injected filters are invisible on the raw tree.
    """
    for param, name in _iter_named_params(root):
        if param.find("options") is None:
            continue
        for option_filter in param.findall("options/filter"):
            yield name, option_filter


def _remove_value_filter_ok(option_filter: etree._Element, /) -> bool:
    """planemo's ``remove_value`` rule: exactly one of ``value`` alone, ``ref`` alone,
    or ``meta_ref`` + ``key`` together."""
    attrs = option_filter.attrib
    value, ref = "value" in attrs, "ref" in attrs
    meta_ref, key = "meta_ref" in attrs, "key" in attrs
    return (
        (value and not ref and not meta_ref and not key)
        or (not value and ref and not meta_ref and not key)
        or (not value and not ref and meta_ref and key)
    )


class OptionFilterAttributes(CheckRule):
    """GTR077 — an ``<options>/<filter>`` must carry the attributes its type allows.

    Reimplements planemo `InputsOptionsFiltersRequiredAttributes` (a filter type's
    required attributes are present), `InputsOptionsRemoveValueFilterRequiredAttributes`
    (a ``remove_value`` filter needs exactly one of ``value`` / ``ref`` /
    ``meta_ref``+``key``), and `InputsOptionsFiltersAllowedAttributes` (no attribute
    outside the type's allowed
    set). Detect-only.
    """

    meta: ClassVar[RuleMeta] = RuleMeta(
        code="GTR077",
        summary="An <options>/<filter> must carry the attributes its type allows.",
        since="0.0.1",
        cite=_IUC,
        detect_only=True,
        rulesets=frozenset({"strict"}),
        planemo_linters=frozenset(
            {
                "InputsOptionsFiltersAllowedAttributes",
                "InputsOptionsFiltersRequiredAttributes",
                "InputsOptionsRemoveValueFilterRequiredAttributes",
            }
        ),
    )

    def detect(self, document: ToolDocument, /) -> Iterable[Violation]:
        for name, option_filter in _iter_option_filters(document.root):
            ftype = option_filter.get("type")
            if ftype is None or ftype not in _FILTER_REQUIRED_ATTRS:
                continue
            if ftype == "remove_value" and not _remove_value_filter_ok(option_filter):
                yield _violation(
                    document,
                    option_filter,
                    self.meta,
                    f"parameter '{name}' remove_value filter needs exactly one of "
                    "'value'; 'ref'; or 'meta_ref'+'key'",
                )
            for attr in _FILTER_REQUIRED_ATTRS[ftype]:
                if attr not in option_filter.attrib:
                    yield _violation(
                        document,
                        option_filter,
                        self.meta,
                        f"parameter '{name}' '{ftype}' filter is missing required "
                        f"attribute '{attr}'",
                    )
            for attr in option_filter.attrib:
                if attr not in _FILTER_ALLOWED_ATTRS[ftype]:
                    yield _violation(
                        document,
                        option_filter,
                        self.meta,
                        f"parameter '{name}' '{ftype}' filter has unnecessary "
                        f"attribute '{attr}'",
                    )


class OptionFilterExpression(CheckRule):
    """GTR078 — a ``regexp`` ``<options>/<filter>``'s ``value`` must be a valid regex.

    Reimplements planemo `InputsOptionsRegexFilterExpression`. Detect-only.
    """

    meta: ClassVar[RuleMeta] = RuleMeta(
        code="GTR078",
        summary="A regexp <options>/<filter> value must be a valid regular expression.",
        since="0.0.1",
        cite=_IUC,
        detect_only=True,
        rulesets=frozenset({"strict"}),
        planemo_linters=frozenset({"InputsOptionsRegexFilterExpression"}),
    )

    def detect(self, document: ToolDocument, /) -> Iterable[Violation]:
        for name, option_filter in _iter_option_filters(document.root):
            if option_filter.get("type") != "regexp":
                continue
            value = option_filter.get("value")
            if value is not None and not _is_valid_regex(value):
                yield _violation(
                    document,
                    option_filter,
                    self.meta,
                    f"parameter '{name}' regexp filter value {value!r} is not a valid "
                    "regular expression",
                )


class OptionFilterReferences(CheckRule):
    """GTR079 — an ``<options>/<filter>``'s ``ref``/``meta_ref`` must name a real param.

    Reimplements planemo `InputsOptionsFiltersCheckReferences`. A macro-using tool is
    **skipped** — the param-name set is incomplete on the raw tree, so a reference to a
    macro-supplied param can't be proven missing (the GTR044 boundary). Detect-only.
    """

    meta: ClassVar[RuleMeta] = RuleMeta(
        code="GTR079",
        summary="An <options>/<filter> ref/meta_ref must name a real parameter.",
        since="0.0.1",
        cite=_IUC,
        detect_only=True,
        rulesets=frozenset({"strict"}),
        planemo_linters=frozenset({"InputsOptionsFiltersCheckReferences"}),
    )

    def detect(self, document: ToolDocument, /) -> Iterable[Violation]:
        root = document.root
        if has_macros(root):
            return
        param_names = {name for _param, name in _iter_named_params(root)}
        for name, option_filter in _iter_option_filters(root):
            if option_filter.get("type") is None:
                continue
            for ref_attr in ("meta_ref", "ref"):
                ref = option_filter.get(ref_attr)
                if ref is not None and ref not in param_names:
                    yield _violation(
                        document,
                        option_filter,
                        self.meta,
                        f"parameter '{name}' filter {ref_attr} '{ref}' refers to a "
                        "non-existent parameter",
                    )
