"""The concrete advisory checks.

Each check is a small LBYL query over the parsed ``ToolDocument`` and yields a
``Violation`` located on the offending element. All are ``detect_only`` — they
report, they never fix. Three are the **advisory residual** sub-rules of a
partition practice (``GTR018.2`` / ``GTR019.2`` / ``GTR020.2``): they flag only the
part the fixable sibling (``GTR018.1`` / ``GTR019.1`` / ``GTR020.1``) cannot reach,
so the practice's fix and advisory partition cleanly (registry ``docs/decisions.md``
D10). The residual boundary reuses the **shared tier-1 predicates**
(``galaxy_tool_xml.cdata`` / ``galaxy_tool_xml.command_vars``), so it can never drift
from what the fix accepts. ``GTR032`` (``&&`` vs lone ``&``) stays a no-op stub.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from typing import TYPE_CHECKING, ClassVar

from galaxy_tool_refactor_rules.meta import RuleMeta
from galaxy_tool_refactor_rules.violation import Violation
from galaxy_tool_xml.cdata import cdata_wrappable, needs_cdata
from galaxy_tool_xml.command_text import unquoted_cheetah_vars
from galaxy_tool_xml.command_vars import input_param_info, provably_quotable
from lxml import etree
from packaging.version import InvalidVersion, Version

from galaxy_tool_xml_check.rules import CheckRule

if TYPE_CHECKING:
    from galaxy_tool_xml.document import ToolDocument

_IUC = "https://galaxy-iuc-standards.readthedocs.io/en/latest/best_practices/tool_xml.html"

# IUC tool ids are lowercase letters, digits, and ``_ . + -`` — no spaces, no
# uppercase. (Galaxy itself is more permissive; this is the convention.)
_ID_CHARSET = re.compile(r"[a-z0-9_.+-]+")


def _violation(
    document: ToolDocument,
    element: etree._Element,
    meta: RuleMeta,
    message: str,
    /,
) -> Violation:
    """Build a ``Violation`` for *meta* located on *element*."""
    line = element.sourceline
    return Violation(
        code=meta.code,
        sourceline=line if line is not None else 0,
        xpath=str(document.tree.getpath(element)),
        message=message,
    )


def _has_text(element: etree._Element, /) -> bool:
    """Whether *element* has non-whitespace text content."""
    return bool((element.text or "").strip())


def _is_pep440(value: str, /) -> bool:
    """Whether *value* parses as a PEP 440 version.

    ``packaging`` exposes no validity predicate, so the ``try``/``except`` is the
    sanctioned third-party boundary (mirrors ``profiles.is_newer_profile``).
    """
    try:
        Version(value)
    except InvalidVersion:
        return False
    return True


class TestsPresent(CheckRule):
    """GTR021 — the tool should ship at least one functional ``<test>``."""

    meta: ClassVar[RuleMeta] = RuleMeta(
        code="GTR021",
        summary="Tool should ship at least one functional <test>.",
        since="0.0.1",
        cite=_IUC,
        detect_only=True,
    )

    def detect(self, document: ToolDocument, /) -> Iterable[Violation]:
        root = document.root
        tests = root.find("tests")
        if tests is None or tests.find("test") is None:
            yield _violation(
                document, root, self.meta, "no <tests> with at least one <test>"
            )


class CommandCdata(CheckRule):
    """GTR018.2 — the ``<command>`` body should be wrapped in CDATA (advisory residual).

    The advisory half of the GTR018 practice: the fixable sibling ``GTR018.1``
    (``WrapCommandCdata``) wraps the pure-text bodies, so this flags only the
    **residual** the fix cannot reach — a body that needs CDATA but is mixed-content
    or carries a ``]]>`` terminator (``needs_cdata and not cdata_wrappable``, the
    shared tier-1 predicate).
    """

    meta: ClassVar[RuleMeta] = RuleMeta(
        code="GTR018.2",
        parent="GTR018",
        summary="<command> CDATA residual the fix can't reach (mixed-content / ]]>).",
        since="0.0.1",
        cite=_IUC,
        detect_only=True,
    )

    def detect(self, document: ToolDocument, /) -> Iterable[Violation]:
        command = document.root.find("command")
        if (
            command is not None
            and needs_cdata(command)
            and not cdata_wrappable(command)
        ):
            yield _violation(
                document, command, self.meta, "<command> is not wrapped in CDATA"
            )


class IdCharset(CheckRule):
    """GTR023 — the tool ``id`` should use the recommended charset."""

    meta: ClassVar[RuleMeta] = RuleMeta(
        code="GTR023",
        summary="Tool id should use lowercase letters, digits, and '_.+-'.",
        since="0.0.1",
        cite=_IUC,
        detect_only=True,
    )

    def detect(self, document: ToolDocument, /) -> Iterable[Violation]:
        root = document.root
        tool_id = root.get("id")
        if tool_id is not None and _ID_CHARSET.fullmatch(tool_id) is None:
            yield _violation(
                document,
                root,
                self.meta,
                f"tool id {tool_id!r} is not in the recommended charset "
                "(lowercase letters, digits, '_.+-')",
            )


class VersionFormat(CheckRule):
    """GTR024 — the tool ``version`` should be PEP 440 or a ``@...@`` macro."""

    meta: ClassVar[RuleMeta] = RuleMeta(
        code="GTR024",
        summary="Tool version should be PEP 440 or a @...@ version macro.",
        since="0.0.1",
        cite=_IUC,
        detect_only=True,
    )

    def detect(self, document: ToolDocument, /) -> Iterable[Violation]:
        root = document.root
        version = root.get("version")
        if version is None or "@" in version:
            return  # absent (a validity matter) or a macro token like @TOOL_VERSION@
        if not _is_pep440(version):
            yield _violation(
                document,
                root,
                self.meta,
                f"version {version!r} is neither PEP 440 nor a @...@ macro",
            )


class RequirementsPresent(CheckRule):
    """GTR025 — the tool should declare ``<requirements>``."""

    meta: ClassVar[RuleMeta] = RuleMeta(
        code="GTR025",
        summary="Tool should declare <requirements>.",
        since="0.0.1",
        cite=_IUC,
        detect_only=True,
    )

    def detect(self, document: ToolDocument, /) -> Iterable[Violation]:
        root = document.root
        requirements = root.find("requirements")
        if requirements is None or not (
            requirements.findall("requirement") or requirements.findall("container")
        ):
            yield _violation(document, root, self.meta, "no <requirements> declared")


class ErrorHandling(CheckRule):
    """GTR026 — the tool should declare error handling."""

    meta: ClassVar[RuleMeta] = RuleMeta(
        code="GTR026",
        summary="Tool should declare error handling (detect_errors or <stdio>).",
        since="0.0.1",
        cite=_IUC,
        detect_only=True,
    )

    def detect(self, document: ToolDocument, /) -> Iterable[Violation]:
        root = document.root
        command = root.find("command")
        has_detect_errors = bool(command is not None and command.get("detect_errors"))
        if not has_detect_errors and root.find("stdio") is None:
            yield _violation(
                document,
                root,
                self.meta,
                "no explicit error handling (set <command detect_errors=...> "
                "or add <stdio>)",
            )


class EdamXrefs(CheckRule):
    """GTR027 — the tool should declare EDAM topics/operations or ``<xrefs>``."""

    meta: ClassVar[RuleMeta] = RuleMeta(
        code="GTR027",
        summary="Tool should declare EDAM topics/operations or <xrefs>.",
        since="0.0.1",
        cite=_IUC,
        detect_only=True,
    )

    def detect(self, document: ToolDocument, /) -> Iterable[Violation]:
        root = document.root
        if all(
            root.find(tag) is None
            for tag in ("edam_topics", "edam_operations", "xrefs")
        ):
            yield _violation(
                document,
                root,
                self.meta,
                "no EDAM topics/operations or <xrefs>",
            )


class HelpPresent(CheckRule):
    """GTR028 — the tool should provide non-empty ``<help>``."""

    meta: ClassVar[RuleMeta] = RuleMeta(
        code="GTR028",
        summary="Tool should provide non-empty <help>.",
        since="0.0.1",
        cite=_IUC,
        detect_only=True,
    )

    def detect(self, document: ToolDocument, /) -> Iterable[Violation]:
        root = document.root
        help_element = root.find("help")
        if help_element is None or not _has_text(help_element):
            yield _violation(
                document,
                help_element if help_element is not None else root,
                self.meta,
                "no non-empty <help>",
            )


class DescriptionPresent(CheckRule):
    """GTR029 — the tool should provide a non-empty ``<description>``."""

    meta: ClassVar[RuleMeta] = RuleMeta(
        code="GTR029",
        summary="Tool should provide a non-empty <description>.",
        since="0.0.1",
        cite=_IUC,
        detect_only=True,
    )

    def detect(self, document: ToolDocument, /) -> Iterable[Violation]:
        root = document.root
        description = root.find("description")
        if description is None or not _has_text(description):
            yield _violation(
                document,
                description if description is not None else root,
                self.meta,
                "no non-empty <description>",
            )


class HelpCdata(CheckRule):
    """GTR019.2 — the ``<help>`` body should be wrapped in CDATA (advisory residual).

    The advisory half of GTR019: ``GTR019.1`` (``WrapHelpCdata``) wraps the pure-text
    bodies, so this flags only the mixed-content / ``]]>``-bearing residual the fix
    cannot reach (the shared tier-1 ``needs_cdata and not cdata_wrappable``).
    """

    meta: ClassVar[RuleMeta] = RuleMeta(
        code="GTR019.2",
        parent="GTR019",
        summary="<help> CDATA residual the fix can't reach (mixed-content / ]]>).",
        since="0.0.1",
        cite=_IUC,
        detect_only=True,
    )

    def detect(self, document: ToolDocument, /) -> Iterable[Violation]:
        help_element = document.root.find("help")
        if (
            help_element is not None
            and needs_cdata(help_element)
            and not cdata_wrappable(help_element)
        ):
            yield _violation(
                document, help_element, self.meta, "<help> is not wrapped in CDATA"
            )


class SingleQuotedCheetah(CheckRule):
    """GTR020.2 — single-quote Cheetah variables in ``<command>`` (advisory residual).

    The advisory half of GTR020: the fixable sibling ``GTR020.1``
    (``SingleQuoteCommandVars``) auto-quotes the *provable* occurrences, so this
    reports one finding only per **non-provable** unquoted shell-line ``$var`` — a
    free-form ``text`` param, a deliberate ``multiple=`` splat, a dataset-label attr,
    ``$on_string``, or a ``#set``/loop var — where single-quoting is a judgment call a
    static fixer can't make. Provability uses the shared tier-1 ``provably_quotable``
    classifier, so the fix/advisory split never drifts. Cheetah directive lines and
    already-quoted references are excluded by the read-only ``command_text`` lexer.
    """

    meta: ClassVar[RuleMeta] = RuleMeta(
        code="GTR020.2",
        parent="GTR020",
        summary="Single-quote <command> Cheetah vars: the non-provable residual.",
        since="0.0.1",
        cite=_IUC,
        detect_only=True,
    )

    def detect(self, document: ToolDocument, /) -> Iterable[Violation]:
        command = document.root.find("command")
        if command is None:
            return
        base_line = command.sourceline or 0
        xpath = str(document.tree.getpath(command))
        kinds, structural = input_param_info(document.root)
        text = "".join(command.itertext())
        for occurrence in unquoted_cheetah_vars(text):
            if provably_quotable(occurrence.name, kinds, structural):
                continue  # GTR020.1 auto-fixes this one
            yield Violation(
                code=self.meta.code,
                sourceline=base_line + occurrence.line_offset if base_line else 0,
                xpath=xpath,
                message=(
                    f"unquoted Cheetah variable {occurrence.name} in <command> — "
                    f"single-quote it as '{occurrence.name}'"
                ),
            )


class CommandAndJoining(CheckRule):
    """GTR032 — join shell commands with ``&&`` not a lone ``&`` (placeholder).

    Reserved IUC code; ``detect`` is a no-op — now on a **data-backed** basis
    (``docs/decisions.md`` D3, ``scripts.measure command-lone-amp``): of the 431
    corpus tools the crude lone-``&`` heuristic flags, the genuine ``cmd1 & cmd2``
    anti-pattern appears in **one** — the rest are redirections (``2>&1``), quoted
    ``&`` literals (sed/awk), and ``|&`` pipes. A precise check needs the M5 shell
    lexer, not a regex. Deferred. See ``../../docs/iuc_best_practices.md``.
    """

    meta: ClassVar[RuleMeta] = RuleMeta(
        code="GTR032",
        summary="Join shell commands with && not a lone & (not yet implemented).",
        since="0.0.1",
        cite=_IUC,
        detect_only=True,
    )

    def detect(self, document: ToolDocument, /) -> Iterable[Violation]:
        return ()  # placeholder — detection deferred


class RequirementVersionPinned(CheckRule):
    """GTR033 — package ``<requirement>``\\ s should pin a version.

    A conda/``package`` requirement without a ``version`` is not reproducible — a
    later environment solve can pick a different release. Other requirement kinds
    (``set_environment``, ``resource``, …) carry no package version, so only
    ``type="package"`` (Galaxy's default when ``type`` is omitted) is checked.
    Fires on 275 tools / 661 findings (``docs/decisions.md`` D7).
    """

    meta: ClassVar[RuleMeta] = RuleMeta(
        code="GTR033",
        summary="Package <requirement>s should pin a version.",
        since="0.0.1",
        cite=_IUC,
        detect_only=True,
    )

    def detect(self, document: ToolDocument, /) -> Iterable[Violation]:
        requirements = document.root.find("requirements")
        if requirements is None:
            return
        for requirement in requirements.findall("requirement"):
            if requirement.get("type", "package") != "package":
                continue
            version = requirement.get("version")
            if version is None or not version.strip():
                name = (requirement.text or "").strip() or "?"
                yield _violation(
                    document,
                    requirement,
                    self.meta,
                    f"package requirement {name!r} has no version — pin it for "
                    "reproducibility",
                )
