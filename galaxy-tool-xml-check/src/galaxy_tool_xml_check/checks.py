"""The concrete advisory IUC checks (IUC001–IUC012).

Each check is a small LBYL query over the parsed ``ToolDocument`` and yields a
``Violation`` located on the offending element. All are ``detect_only`` — they
report, they never fix. The two ``<command>``-CDATA-text heuristics (single-quote
Cheetah, ``&&`` vs lone ``&``) are reserved placeholders (``IUC011`` / ``IUC012``)
whose ``detect`` is a no-op stub, pending tuning to avoid noise; see
``../../docs/iuc_best_practices.md``.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from typing import TYPE_CHECKING, ClassVar

from galaxy_tool_refactor_rules.meta import RuleMeta
from galaxy_tool_refactor_rules.violation import Violation
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


def _is_cdata_wrapped(element: etree._Element, /) -> bool:
    """Whether *element*'s own text body is a CDATA section.

    lxml exposes CDATA as plain ``.text``, so the only way to tell is to
    re-serialise (the tree was parsed with ``strip_cdata=False``, so a CDATA
    section round-trips as ``<![CDATA[...]]>``). We require the section to be the
    element's *own* leading content — the text immediately after the opening tag
    (modulo whitespace) must be the CDATA — so a partly-wrapped body
    (``echo <![CDATA[...]]>``) or a CDATA-bearing *child* does not count as the
    element itself being wrapped.
    """
    serialised: str = etree.tostring(element, encoding="unicode", with_tail=False)
    body = serialised[serialised.index(">") + 1 :]
    return bool(body.lstrip().startswith("<![CDATA["))


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
    """IUC001 — the tool should ship at least one functional ``<test>``."""

    meta: ClassVar[RuleMeta] = RuleMeta(
        code="IUC001",
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
    """IUC002 — the ``<command>`` body should be wrapped in CDATA."""

    meta: ClassVar[RuleMeta] = RuleMeta(
        code="IUC002",
        summary="<command> body should be wrapped in CDATA.",
        since="0.0.1",
        cite=_IUC,
        detect_only=True,
    )

    def detect(self, document: ToolDocument, /) -> Iterable[Violation]:
        command = document.root.find("command")
        if (
            command is not None
            and _has_text(command)
            and not _is_cdata_wrapped(command)
        ):
            yield _violation(
                document, command, self.meta, "<command> is not wrapped in CDATA"
            )


class IdCharset(CheckRule):
    """IUC003 — the tool ``id`` should use the recommended charset."""

    meta: ClassVar[RuleMeta] = RuleMeta(
        code="IUC003",
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
    """IUC004 — the tool ``version`` should be PEP 440 or a ``@...@`` macro."""

    meta: ClassVar[RuleMeta] = RuleMeta(
        code="IUC004",
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
    """IUC005 — the tool should declare ``<requirements>``."""

    meta: ClassVar[RuleMeta] = RuleMeta(
        code="IUC005",
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
    """IUC006 — the tool should declare error handling."""

    meta: ClassVar[RuleMeta] = RuleMeta(
        code="IUC006",
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
    """IUC007 — the tool should declare EDAM topics/operations or ``<xrefs>``."""

    meta: ClassVar[RuleMeta] = RuleMeta(
        code="IUC007",
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
    """IUC008 — the tool should provide non-empty ``<help>``."""

    meta: ClassVar[RuleMeta] = RuleMeta(
        code="IUC008",
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
    """IUC009 — the tool should provide a non-empty ``<description>``."""

    meta: ClassVar[RuleMeta] = RuleMeta(
        code="IUC009",
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
    """IUC010 — the ``<help>`` body should be wrapped in CDATA."""

    meta: ClassVar[RuleMeta] = RuleMeta(
        code="IUC010",
        summary="<help> body should be wrapped in CDATA.",
        since="0.0.1",
        cite=_IUC,
        detect_only=True,
    )

    def detect(self, document: ToolDocument, /) -> Iterable[Violation]:
        help_element = document.root.find("help")
        if (
            help_element is not None
            and _has_text(help_element)
            and not _is_cdata_wrapped(help_element)
        ):
            yield _violation(
                document, help_element, self.meta, "<help> is not wrapped in CDATA"
            )


class SingleQuotedCheetah(CheckRule):
    """IUC011 — single-quote Cheetah variables in ``<command>`` (placeholder).

    Reserved IUC code; ``detect`` is a no-op. Detecting unquoted Cheetah ``$var``
    means parsing shell/Cheetah text inside CDATA, which is heuristic and noisy;
    deferred until it can be tuned. See ``../../docs/iuc_best_practices.md``.
    """

    meta: ClassVar[RuleMeta] = RuleMeta(
        code="IUC011",
        summary="Single-quote Cheetah variables in <command> (not yet implemented).",
        since="0.0.1",
        cite=_IUC,
        detect_only=True,
    )

    def detect(self, document: ToolDocument, /) -> Iterable[Violation]:
        return ()  # placeholder — detection deferred


class CommandAndJoining(CheckRule):
    """IUC012 — join shell commands with ``&&`` not a lone ``&`` (placeholder).

    Reserved IUC code; ``detect`` is a no-op — now on a **data-backed** basis
    (``docs/decisions.md`` D3, ``scripts.measure command-lone-amp``): of the 431
    corpus tools the crude lone-``&`` heuristic flags, the genuine ``cmd1 & cmd2``
    anti-pattern appears in **one** — the rest are redirections (``2>&1``), quoted
    ``&`` literals (sed/awk), and ``|&`` pipes. A precise check needs the M5 shell
    lexer, not a regex. Deferred. See ``../../docs/iuc_best_practices.md``.
    """

    meta: ClassVar[RuleMeta] = RuleMeta(
        code="IUC012",
        summary="Join shell commands with && not a lone & (not yet implemented).",
        since="0.0.1",
        cite=_IUC,
        detect_only=True,
    )

    def detect(self, document: ToolDocument, /) -> Iterable[Violation]:
        return ()  # placeholder — detection deferred
