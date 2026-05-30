"""The advisory-check registry and runner.

``all_checks()`` is the enumerated set of active ``CheckRule`` classes (sorted by
IUC code); ``detect_violations(document)`` runs every check and returns the
findings sorted by source line. Mirrors the codemod tier's ``coded_codemods()``
and the fmt tier's ``all_rules()`` so the cross-tier rule registry spans this
tier too.
"""

from __future__ import annotations

from functools import cache
from typing import TYPE_CHECKING

from galaxy_tool_xml_check.checks import (
    CommandAndJoining,
    CommandCdata,
    DescriptionPresent,
    EdamXrefs,
    ErrorHandling,
    HelpCdata,
    HelpPresent,
    IdCharset,
    RequirementsPresent,
    SingleQuotedCheetah,
    TestsPresent,
    VersionFormat,
)
from galaxy_tool_xml_check.rules import CheckRule

if TYPE_CHECKING:
    from galaxy_tool_refactor_rules.violation import Violation
    from galaxy_tool_xml.document import ToolDocument


@cache
def all_checks() -> tuple[type[CheckRule], ...]:
    """Return every active advisory check class, sorted by ``meta.code``."""
    classes: list[type[CheckRule]] = [
        TestsPresent,
        CommandCdata,
        IdCharset,
        VersionFormat,
        RequirementsPresent,
        ErrorHandling,
        EdamXrefs,
        HelpPresent,
        DescriptionPresent,
        HelpCdata,
        SingleQuotedCheetah,
        CommandAndJoining,
    ]
    return tuple(sorted(classes, key=lambda cls: cls.meta.code))


def detect_violations(document: ToolDocument) -> list[Violation]:
    """Run every advisory check over *document*; return findings sorted by line."""
    violations = [
        violation
        for check_cls in all_checks()
        for violation in check_cls().detect(document)
    ]
    violations.sort(key=lambda violation: (violation.sourceline, violation.code))
    return violations
