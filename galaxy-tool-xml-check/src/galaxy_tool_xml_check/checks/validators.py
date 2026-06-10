"""Parameter ``<validator>`` advisory checks."""


from __future__ import annotations

import ast
import re
import warnings
from collections.abc import Iterable
from typing import TYPE_CHECKING, ClassVar

from galaxy_tool_refactor_rules.meta import RuleMeta
from galaxy_tool_refactor_rules.violation import Violation
from lxml import etree

from galaxy_tool_xml_check.rules import CheckRule

if TYPE_CHECKING:
    from galaxy_tool_xml.document import ToolDocument

from galaxy_tool_xml_check.checks._shared import (
    _IUC,
    _param_name,
    _violation,
)

# Galaxy's parameter-type → allowed validator-type map (planemo's
# ``PARAMETER_VALIDATOR_TYPE_COMPATIBILITY``). A param type absent from the map (e.g.
# ``boolean``) accepts any validator — not flagged.
_PARAM_VALIDATOR_TYPES: dict[str, frozenset[str]] = {
    "integer": frozenset({"in_range", "expression"}),
    "float": frozenset({"in_range", "expression"}),
    "data": frozenset(
        {
            "metadata",
            "no_options",
            "unspecified_build",
            "dataset_ok_validator",
            "dataset_metadata_equal",
            "dataset_metadata_in_range",
            "dataset_metadata_in_file",
            "dataset_metadata_in_data_table",
            "dataset_metadata_not_in_data_table",
            "expression",
        }
    ),
    "data_collection": frozenset(
        {
            "metadata",
            "no_options",
            "unspecified_build",
            "dataset_ok_validator",
            "dataset_metadata_equal",
            "dataset_metadata_in_range",
            "dataset_metadata_in_file",
            "dataset_metadata_in_data_table",
            "dataset_metadata_not_in_data_table",
            "expression",
        }
    ),
    "text": frozenset(
        {
            "regex",
            "length",
            "empty_field",
            "value_in_data_table",
            "value_not_in_data_table",
            "expression",
        }
    ),
    "select": frozenset(
        {
            "in_range",
            "no_options",
            "regex",
            "length",
            "empty_field",
            "value_in_data_table",
            "value_not_in_data_table",
            "expression",
        }
    ),
    "drill_down": frozenset(
        {
            "no_options",
            "regex",
            "length",
            "empty_field",
            "value_in_data_table",
            "value_not_in_data_table",
            "expression",
        }
    ),
    "data_column": frozenset(
        {
            "no_options",
            "regex",
            "length",
            "empty_field",
            "value_in_data_table",
            "value_not_in_data_table",
            "expression",
        }
    ),
}

# Galaxy's validator-attribute → allowed validator-type map (planemo's
# ``ATTRIB_VALIDATOR_COMPATIBILITY``): an attribute present on a validator of an
# unlisted type is incompatible.
_VALIDATOR_ATTR_TYPES: dict[str, frozenset[str]] = {
    "check": frozenset({"metadata"}),
    "expression": frozenset({"substitute_value_in_message"}),
    "table_name": frozenset(
        {
            "dataset_metadata_in_data_table",
            "dataset_metadata_not_in_data_table",
            "value_in_data_table",
            "value_not_in_data_table",
        }
    ),
    "filename": frozenset({"dataset_metadata_in_file"}),
    "metadata_name": frozenset(
        {
            "dataset_metadata_equal",
            "dataset_metadata_in_data_table",
            "dataset_metadata_not_in_data_table",
            "dataset_metadata_in_file",
            "dataset_metadata_in_range",
        }
    ),
    "metadata_column": frozenset(
        {
            "dataset_metadata_in_data_table",
            "dataset_metadata_not_in_data_table",
            "value_in_data_table",
            "value_not_in_data_table",
            "dataset_metadata_in_file",
        }
    ),
    "line_startswith": frozenset({"dataset_metadata_in_file"}),
    "min": frozenset({"in_range", "length", "dataset_metadata_in_range"}),
    "max": frozenset({"in_range", "length", "dataset_metadata_in_range"}),
    "exclude_min": frozenset({"in_range", "dataset_metadata_in_range"}),
    "exclude_max": frozenset({"in_range", "dataset_metadata_in_range"}),
    "split": frozenset({"dataset_metadata_in_file"}),
    "skip": frozenset({"metadata"}),
    "value": frozenset({"dataset_metadata_equal"}),
    "value_json": frozenset({"dataset_metadata_equal"}),
}

# Validator types whose body is an expression/regex (carry text); all others should not.
_EXPRESSION_VALIDATORS = frozenset({"expression", "regex"})


def _iter_param_validators(
    root: etree._Element, /
) -> Iterable[tuple[str, str, etree._Element, str]]:
    """Each ``(param name, param type, validator, validator type)`` over typed params.

    Mirrors planemo's ``_iter_param_validator``: every ``<inputs>//param[@type]`` and
    its ``<validator type=…>`` children. Macro-injected validators are invisible on the
    raw
    tree (under-report, never misfire — the GTR044 boundary).
    """
    inputs = root.find("inputs")
    if inputs is None:
        return
    for param in inputs.iterfind(".//param[@type]"):
        name = _param_name(param)
        if name is None:
            continue
        param_type = str(param.get("type"))
        for validator in param.findall("validator[@type]"):
            yield name, param_type, validator, str(validator.get("type"))


class ValidatorTypeCompatible(CheckRule):
    """GTR065 — a ``<validator>`` must be compatible with its param and attributes.

    Reimplements planemo `ValidatorParamIncompatible` (the validator ``type`` must be
    allowed for the param ``type``) + `ValidatorAttribIncompatible` (each validator
    attribute must be allowed for the validator ``type``). Detect-only.
    """

    meta: ClassVar[RuleMeta] = RuleMeta(
        code="GTR065",
        summary="A <validator> must be compatible with its param type and attributes.",
        since="0.0.1",
        cite=_IUC,
        detect_only=True,
        rulesets=frozenset({"strict"}),
        planemo_linters=frozenset(
            {
                "ValidatorAttribIncompatible",
                "ValidatorParamIncompatible",
            }
        ),
    )

    def detect(self, document: ToolDocument, /) -> Iterable[Violation]:
        for name, param_type, validator, vtype in _iter_param_validators(document.root):
            allowed = _PARAM_VALIDATOR_TYPES.get(param_type)
            if allowed is not None and vtype not in allowed:
                yield _violation(
                    document,
                    validator,
                    self.meta,
                    f"parameter '{name}': validator type '{vtype}' is incompatible "
                    f"with param type '{param_type}'",
                )
            for attr, attr_types in _VALIDATOR_ATTR_TYPES.items():
                if validator.get(attr) is not None and vtype not in attr_types:
                    yield _violation(
                        document,
                        validator,
                        self.meta,
                        f"parameter '{name}': attribute '{attr}' is incompatible with "
                        f"validator type '{vtype}'",
                    )


class ValidatorTextPresence(CheckRule):
    """GTR066 — a ``<validator>`` body should match its type.

    Reimplements planemo `ValidatorHasText` (``expression`` / ``regex`` validators need
    a body) + `ValidatorHasNoText` (other validators should not carry one). Detect-only.
    """

    meta: ClassVar[RuleMeta] = RuleMeta(
        code="GTR066",
        summary="A <validator> body should match its type (expr/regex carry text).",
        since="0.0.1",
        cite=_IUC,
        detect_only=True,
        rulesets=frozenset({"strict"}),
        planemo_linters=frozenset({"ValidatorHasNoText", "ValidatorHasText"}),
    )

    def detect(self, document: ToolDocument, /) -> Iterable[Violation]:
        for name, _param_type, validator, vtype in _iter_param_validators(
            document.root
        ):
            if vtype in _EXPRESSION_VALIDATORS:
                if validator.text is None:
                    yield _violation(
                        document,
                        validator,
                        self.meta,
                        f"parameter '{name}': '{vtype}' validator needs a body",
                    )
            elif validator.text is not None:
                yield _violation(
                    document,
                    validator,
                    self.meta,
                    f"parameter '{name}': '{vtype}' validator should not carry text",
                )


class ValidatorExpressionValid(CheckRule):
    """GTR067 — an ``expression`` / ``regex`` ``<validator>`` body must be valid.

    Reimplements planemo `ValidatorExpression` (the body must ``re.compile`` /
    ``ast.parse``) + `ValidatorExpressionFuture` (a ``FutureWarning`` is reported as a
    deprecation rather than an error). A body carrying a ``@…@`` macro token is
    **skipped** — it is a template fragment, not yet a regex/expression (the GTR052
    raw-tree boundary). Detect-only.
    """

    meta: ClassVar[RuleMeta] = RuleMeta(
        code="GTR067",
        summary="An expression/regex <validator> body must be valid.",
        since="0.0.1",
        cite=_IUC,
        detect_only=True,
        rulesets=frozenset({"strict"}),
        planemo_linters=frozenset({"ValidatorExpression", "ValidatorExpressionFuture"}),
    )

    def detect(self, document: ToolDocument, /) -> Iterable[Violation]:
        for name, _param_type, validator, vtype in _iter_param_validators(
            document.root
        ):
            if vtype not in _EXPRESSION_VALIDATORS:
                continue
            body = validator.text
            if body is None or "@" in body:
                continue
            with warnings.catch_warnings():
                warnings.simplefilter("error", FutureWarning)
                try:
                    if vtype == "regex":
                        re.compile(body)
                    else:
                        ast.parse(body, mode="eval")
                except FutureWarning as future:
                    yield _violation(
                        document,
                        validator,
                        self.meta,
                        f"parameter '{name}': deprecated {vtype} '{body}': {future}",
                    )
                except (re.error, SyntaxError, ValueError) as error:
                    yield _violation(
                        document,
                        validator,
                        self.meta,
                        f"parameter '{name}': invalid {vtype} '{body}': {error}",
                    )


# Validator types and the attribute set of which at least one is required (planemo's
# `ValidatorMinMax` / `ValidatorMetadataCheckSkip` / `ValidatorTableName` /
# `ValidatorMetadataName`). ``dataset_metadata_equal`` is handled separately below — it
# needs ``(value | value_json)`` *and* ``metadata_name``, and not both value forms.
_VALIDATOR_REQUIRED_ANY: tuple[tuple[frozenset[str], tuple[str, ...]], ...] = (
    (frozenset({"in_range", "length", "dataset_metadata_in_range"}), ("min", "max")),
    (frozenset({"metadata"}), ("check", "skip")),
    (
        frozenset(
            {
                "value_in_data_table",
                "value_not_in_data_table",
                "dataset_metadata_in_data_table",
                "dataset_metadata_not_in_data_table",
            }
        ),
        ("table_name",),
    ),
    (
        frozenset(
            {
                "dataset_metadata_in_data_table",
                "dataset_metadata_not_in_data_table",
                "dataset_metadata_in_file",
                "dataset_metadata_in_range",
            }
        ),
        ("metadata_name",),
    ),
)


class ValidatorRequiredAttributes(CheckRule):
    """GTR068 — a ``<validator>`` must carry the attributes its type requires.

    Reimplements planemo `ValidatorMinMax` (``in_range`` / ``length`` /
    ``dataset_metadata_in_range`` need ``min`` or ``max``), `ValidatorMetadataCheckSkip`
    (``metadata`` needs ``check`` or ``skip``), `ValidatorTableName` (the
    ``*_data_table`` validators need ``table_name``), `ValidatorMetadataName` (the
    ``dataset_metadata_*`` validators need ``metadata_name``), and
    `ValidatorDatasetMetadataEqualValue` + `…OrJson` (``dataset_metadata_equal`` needs
    ``value``/``value_json`` and ``metadata_name``, and not both value forms).
    Detect-only.
    """

    meta: ClassVar[RuleMeta] = RuleMeta(
        code="GTR068",
        summary="A <validator> must carry the attributes its type requires.",
        since="0.0.1",
        cite=_IUC,
        detect_only=True,
        rulesets=frozenset({"strict"}),
        planemo_linters=frozenset(
            {
                "ValidatorDatasetMetadataEqualValue",
                "ValidatorDatasetMetadataEqualValueOrJson",
                "ValidatorMetadataCheckSkip",
                "ValidatorMetadataName",
                "ValidatorMinMax",
                "ValidatorTableName",
            }
        ),
    )

    def detect(self, document: ToolDocument, /) -> Iterable[Violation]:
        for name, _param_type, validator, vtype in _iter_param_validators(
            document.root
        ):
            for types, attrs in _VALIDATOR_REQUIRED_ANY:
                if vtype in types and not any(
                    validator.get(attr) is not None for attr in attrs
                ):
                    joined = " or ".join(f"'{attr}'" for attr in attrs)
                    yield _violation(
                        document,
                        validator,
                        self.meta,
                        f"parameter '{name}': '{vtype}' validator needs the {joined} "
                        "attribute(s)",
                    )
            if vtype == "dataset_metadata_equal":
                has_value = validator.get("value") is not None
                has_json = validator.get("value_json") is not None
                has_name = validator.get("metadata_name") is not None
                if not (has_value or has_json) or not has_name:
                    yield _violation(
                        document,
                        validator,
                        self.meta,
                        f"parameter '{name}': 'dataset_metadata_equal' validator needs "
                        "'value'/'value_json' and 'metadata_name'",
                    )
                if has_value and has_json:
                    yield _violation(
                        document,
                        validator,
                        self.meta,
                        f"parameter '{name}': 'dataset_metadata_equal' validator must "
                        "not set both 'value' and 'value_json'",
                    )
