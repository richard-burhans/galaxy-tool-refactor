"""The advisory-check registry and runner.

``all_checks()`` is the enumerated set of active ``CheckRule`` classes (sorted by
IUC code); ``detect_violations(document)`` runs every check and returns the
findings sorted by source line. Mirrors the codemod tier's ``coded_codemods()``
and the fmt tier's ``all_rules()`` — an explicit list, so the cross-tier rule
registry spans this tier with the same convention (adding a check means editing
this list, which ``test_detect.py`` pins by count as the acknowledgement gate).

The concrete checks live in the ``checks`` sub-package, split by element/source
area into themed submodules.
"""

from __future__ import annotations

from functools import cache
from typing import TYPE_CHECKING

from galaxy_tool_xml_check.checks.help import HelpRstResidual
from galaxy_tool_xml_check.checks.inputs import (
    BooleanValuesDistinct,
    ConditionalTestParamAttributes,
    ConditionalTestParamType,
    ConditionalWhensMatchOptions,
    DataOptionsValid,
    DataParamFormatDeclared,
    InputOutputNamesDistinct,
    InputsPresent,
    OptionFilterAttributes,
    OptionFilterExpression,
    OptionFilterReferences,
    ParamNamePresent,
    ParamNamesUnique,
    ParamNameValid,
    ParamTypeChildCombination,
    SelectDisplayConsistent,
    SelectOptionsDefined,
    SelectOptionsDistinct,
    SelectOptionsHaveSource,
    SelectOptionsNotDeprecated,
    SelectOptionsSingle,
    SelectOptionsSourceCoherent,
    SelectOptionValuePresent,
    UnusedParam,
)
from galaxy_tool_xml_check.checks.outputs import (
    CollectionTypeDeclared,
    OutputFilterValid,
    OutputFormatDefined,
    OutputFormatSourceExclusive,
    OutputLabelsDistinct,
    OutputNamesUnique,
    OutputNameValid,
    OutputReferencesValid,
    OutputsPresent,
)
from galaxy_tool_xml_check.checks.partition import (
    CommandCdata,
    HelpCdata,
    SingleQuotedCheetah,
)
from galaxy_tool_xml_check.checks.tests import (
    TestAssertionsWellFormed,
    TestDiscoveredOutputsChecked,
    TestExpectFailureCoherent,
    TestExpectNumOutputs,
    TestHasExpectations,
    TestOutputCompareAttributes,
    TestOutputNamed,
    TestOutputsCorrespond,
    TestParamsInInputs,
)
from galaxy_tool_xml_check.checks.tool import (
    CitationsPresent,
    CommandAndJoining,
    CommandPresent,
    ContainerShapeRecognized,
    DescriptionPresent,
    EdamXrefs,
    ErrorHandling,
    HelpPresent,
    IdCharset,
    NoTodoText,
    ProfileFormatValid,
    RequirementNamePresent,
    RequirementsPresent,
    RequirementVersionPinned,
    StdioRegexValid,
    TestsPresent,
    ToolVersionWhitespace,
    VersionFormat,
)
from galaxy_tool_xml_check.checks.validators import (
    ValidatorExpressionValid,
    ValidatorRequiredAttributes,
    ValidatorTextPresence,
    ValidatorTypeCompatible,
)
from galaxy_tool_xml_check.rules import CheckRule

if TYPE_CHECKING:
    from galaxy_tool_refactor_rules.violation import Violation
    from galaxy_tool_xml.document import ToolDocument


@cache
def all_checks() -> tuple[type[CheckRule], ...]:
    """Return every active advisory check class, sorted by ``meta.code``."""
    classes: list[type[CheckRule]] = [
        # tool-level (presence/shape, command, citations/TODO)
        TestsPresent,
        IdCharset,
        VersionFormat,
        RequirementsPresent,
        ErrorHandling,
        EdamXrefs,
        HelpPresent,
        DescriptionPresent,
        CommandAndJoining,
        RequirementVersionPinned,
        CitationsPresent,
        NoTodoText,
        CommandPresent,
        ProfileFormatValid,
        RequirementNamePresent,
        ToolVersionWhitespace,
        ContainerShapeRecognized,
        StdioRegexValid,
        # partition .2 advisory residuals
        CommandCdata,
        HelpCdata,
        SingleQuotedCheetah,
        # outputs
        OutputNamesUnique,
        OutputNameValid,
        CollectionTypeDeclared,
        OutputFormatSourceExclusive,
        OutputsPresent,
        OutputFormatDefined,
        OutputLabelsDistinct,
        OutputFilterValid,
        OutputReferencesValid,
        # inputs (params, select, options, type/display, conditionals, filters)
        UnusedParam,
        ParamNamePresent,
        ParamNameValid,
        ParamNamesUnique,
        InputOutputNamesDistinct,
        SelectOptionsDefined,
        SelectOptionValuePresent,
        SelectOptionsDistinct,
        SelectOptionsSingle,
        SelectOptionsHaveSource,
        SelectOptionsSourceCoherent,
        SelectOptionsNotDeprecated,
        ConditionalTestParamType,
        ConditionalTestParamAttributes,
        ConditionalWhensMatchOptions,
        InputsPresent,
        ParamTypeChildCombination,
        DataOptionsValid,
        BooleanValuesDistinct,
        SelectDisplayConsistent,
        OptionFilterAttributes,
        OptionFilterExpression,
        OptionFilterReferences,
        DataParamFormatDeclared,
        # validators
        ValidatorTypeCompatible,
        ValidatorTextPresence,
        ValidatorExpressionValid,
        ValidatorRequiredAttributes,
        # tests
        TestAssertionsWellFormed,
        TestOutputCompareAttributes,
        TestOutputNamed,
        TestOutputsCorrespond,
        TestDiscoveredOutputsChecked,
        TestParamsInInputs,
        TestExpectFailureCoherent,
        TestExpectNumOutputs,
        TestHasExpectations,
        # help
        HelpRstResidual,
    ]
    return tuple(sorted(classes, key=lambda cls: cls.meta.code))


def sort_violations(violations: list[Violation]) -> list[Violation]:
    """Sort *violations* in place by ``(sourceline, code)`` and return them.

    The canonical ordering for any aggregated ``Violation`` list — line first,
    code as the stable tie-breaker. Shared so this tier, the registry facade, and
    any future aggregator agree on one key (audit ``§N6``).
    """
    violations.sort(key=lambda violation: (violation.sourceline, violation.code))
    return violations


def detect_violations(document: ToolDocument) -> list[Violation]:
    """Run every advisory check over *document*; return findings sorted by line."""
    violations = [
        violation
        for check_cls in all_checks()
        for violation in check_cls().detect(document)
    ]
    return sort_violations(violations)
