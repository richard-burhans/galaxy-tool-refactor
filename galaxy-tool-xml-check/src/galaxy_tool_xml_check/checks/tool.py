"""Tool-level presence/shape advisory checks (IUC + planemo parity)."""


from __future__ import annotations

import re
from collections.abc import Iterable
from typing import TYPE_CHECKING, ClassVar

from galaxy_tool_refactor_rules.meta import RuleMeta
from galaxy_tool_refactor_rules.violation import Violation
from galaxy_tool_source.macros import has_macros
from lxml import etree
from packaging.version import InvalidVersion, Version

from galaxy_tool_xml_check.lone_amp import classify_lone_amps
from galaxy_tool_xml_check.rules import CheckRule

if TYPE_CHECKING:
    from galaxy_tool_source.document import ToolDocument

from galaxy_tool_xml_check.checks._shared import (
    _IUC,
    _is_valid_regex,
    _violation,
)

# IUC tool ids are lowercase letters, digits, and ``_ . + -`` — no spaces, no
# uppercase. (Galaxy itself is more permissive; this is the convention.)
_ID_CHARSET = re.compile(r"[a-z0-9_.+-]+")


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
        rulesets=frozenset({"strict"}),
        planemo_linters=frozenset({"TestsMissing"}),
    )

    def detect(self, document: ToolDocument, /) -> Iterable[Violation]:
        root = document.root
        tests = root.find("tests")
        if tests is None or tests.find("test") is None:
            yield _violation(
                document, root, self.meta, "no <tests> with at least one <test>"
            )


class IdCharset(CheckRule):
    """GTR023 — the tool ``id`` should use the recommended charset.

    Reimplements planemo's `ToolIDValid` and subsumes `ToolIDWhitespace` — an id
    containing whitespace fails the charset match.
    """

    meta: ClassVar[RuleMeta] = RuleMeta(
        code="GTR023",
        summary="Tool id should use lowercase letters, digits, and '_.+-'.",
        since="0.0.1",
        cite=_IUC,
        detect_only=True,
        rulesets=frozenset({"strict"}),
        planemo_linters=frozenset({"ToolIDValid", "ToolIDWhitespace"}),
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


class NameWhitespace(CheckRule):
    """GTR035.2 — a ``<tool>`` ``name`` should carry no edge whitespace.

    The advisory residual of the GTR035 partition (codemod §33 addendum): the
    trim is *display-contract* preserving (``parse_name`` reads the attribute
    raw, ``tool_util/parser/xml.py:220-221``; HTML rendering collapses edge
    whitespace but the byte difference is visible in API JSON), which is below
    the construction bar for an auto-fix — so it is reported here and the
    ``<requirement version>`` half stays fixable as GTR035.1.
    """

    meta: ClassVar[RuleMeta] = RuleMeta(
        code="GTR035.2",
        parent="GTR035",
        summary=(
            "A <tool> 'name' should have no leading/trailing whitespace "
            "(display-contract residual of GTR035; report-only)."
        ),
        since="0.0.1",
        cite=_IUC,
        detect_only=True,
        rulesets=frozenset({"strict"}),
        planemo_linters=frozenset({"ToolNameWhitespace"}),
    )

    def detect(self, document: ToolDocument, /) -> Iterable[Violation]:
        root = document.root
        name = root.get("name")
        if name is not None and name != name.strip():
            yield _violation(
                document,
                root,
                self.meta,
                "<tool> 'name' has leading/trailing whitespace",
            )


class VersionFormat(CheckRule):
    """GTR024 — the tool ``version`` should be PEP 440 or a ``@...@`` macro."""

    meta: ClassVar[RuleMeta] = RuleMeta(
        code="GTR024",
        summary="Tool version should be PEP 440 or a @...@ version macro.",
        since="0.0.1",
        cite=_IUC,
        detect_only=True,
        rulesets=frozenset({"strict"}),
        planemo_linters=frozenset({"ToolVersionPEP404"}),
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
        rulesets=frozenset({"strict"}),
    )

    def detect(self, document: ToolDocument, /) -> Iterable[Violation]:
        root = document.root
        requirements = root.find("requirements")
        if requirements is None or not (
            requirements.findall("requirement") or requirements.findall("container")
        ):
            yield _violation(document, root, self.meta, "no <requirements> declared")


class ErrorHandling(CheckRule):
    """GTR026 — the tool should declare error handling.

    Reimplements planemo's `StdIOAbsence` / `StdIOAbsenceLegacy` — both report the
    same no-``<stdio>``/``detect_errors`` condition (planemo splits them by profile).
    """

    meta: ClassVar[RuleMeta] = RuleMeta(
        code="GTR026",
        summary="Tool should declare error handling (detect_errors or <stdio>).",
        since="0.0.1",
        cite=_IUC,
        detect_only=True,
        rulesets=frozenset({"strict"}),
        planemo_linters=frozenset({"StdIOAbsence", "StdIOAbsenceLegacy"}),
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
        rulesets=frozenset({"strict"}),
        planemo_linters=frozenset({"BioToolsValid", "EDAMTermsValid"}),
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
        rulesets=frozenset({"strict"}),
        planemo_linters=frozenset({"HelpEmpty", "HelpMissing"}),
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
        rulesets=frozenset({"strict"}),
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


class CommandAndJoining(CheckRule):
    """GTR032 — join shell commands with ``&&``, not a lone ``&``.

    A lone ``&`` between two commands backgrounds the first — almost always a
    typo for ``&&`` (run-if-succeeded) in a tool wrapper. The classifier
    (``lone_amp.classify_lone_amps``, the ``command-lone-amp`` measure's engine)
    is quote/redirect/pipe-aware, so sed/awk literals, ``2>&1``, ``|&`` and an
    intentional trailing ``&`` are never flagged — only the genuine *joining*
    class is. Detect-only: a working tool's lone ``&`` cannot be proven a typo
    (backgrounding is valid shell), so there is no auto-fix (D3 → D34).
    """

    meta: ClassVar[RuleMeta] = RuleMeta(
        code="GTR032",
        summary="Join shell commands with && (a lone & backgrounds the first).",
        since="0.0.1",
        cite=_IUC,
        detect_only=True,
        rulesets=frozenset({"strict"}),
    )

    def detect(self, document: ToolDocument, /) -> Iterable[Violation]:
        command = document.root.find("command")
        if command is None:
            return
        joining = classify_lone_amps("".join(command.itertext()))["joining"]
        if joining:
            yield _violation(
                document,
                command,
                self.meta,
                f"lone '&' joins commands {joining} time(s) — use '&&' "
                "(or end-of-command '&' for intentional backgrounding)",
            )


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
        rulesets=frozenset({"strict"}),
        planemo_linters=frozenset({"RequirementVersionMissing"}),
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


class CitationsPresent(CheckRule):
    """GTR038 — the tool should declare at least one non-empty citation.

    Reimplements planemo's `CitationsMissing` (no `<citations>`) and `CitationsNoText`
    (an empty ``doi``/``bibtex`` citation), and subsumes `CitationsNoValid` (a
    `<citations>` with no `<citation>` children — the same no-children condition this
    detect reports), `galaxy.tool_util.linters.citations`. Detect-only: a citation is
    author-supplied content, never synthesised.
    """

    meta: ClassVar[RuleMeta] = RuleMeta(
        code="GTR038",
        summary="Tool should declare a non-empty <citation> (doi/bibtex).",
        since="0.0.1",
        cite=_IUC,
        detect_only=True,
        rulesets=frozenset({"strict"}),
        planemo_linters=frozenset(
            {"CitationsMissing", "CitationsNoText", "CitationsNoValid"}
        ),
    )

    def detect(self, document: ToolDocument, /) -> Iterable[Violation]:
        root = document.root
        citations = root.find("citations")
        if citations is None or not citations.findall("citation"):
            yield _violation(
                document,
                citations if citations is not None else root,
                self.meta,
                "no citations — consider citing the tool's method/software",
            )
            return
        for citation in citations.findall("citation"):
            citation_type = citation.get("type")
            if citation_type in ("doi", "bibtex") and not _has_text(citation):
                yield _violation(
                    document, citation, self.meta, f"empty {citation_type} citation"
                )


class NoTodoText(CheckRule):
    """GTR039 — a ``<command>`` / ``<help>`` should not carry ``TODO`` placeholder text.

    Reimplements planemo's `CommandTODO` / `HelpTODO`
    (`galaxy.tool_util.linters.command` / `…help`) — a leftover ``TODO`` marks an
    unfinished tool. Matches Galaxy: a literal ``"TODO"`` in the element's ``.text``.
    """

    meta: ClassVar[RuleMeta] = RuleMeta(
        code="GTR039",
        summary="<command>/<help> should not contain 'TODO' placeholder text.",
        since="0.0.1",
        cite=_IUC,
        detect_only=True,
        rulesets=frozenset({"strict"}),
        planemo_linters=frozenset({"CommandTODO", "HelpTODO"}),
    )

    def detect(self, document: ToolDocument, /) -> Iterable[Violation]:
        root = document.root
        for tag in ("command", "help"):
            element = root.find(tag)
            if element is not None and "TODO" in (element.text or ""):
                msg = f"<{tag}> contains a 'TODO' placeholder"
                yield _violation(document, element, self.meta, msg)


# A valid Galaxy profile version: a 21st/22nd-century year and a 1–2 digit minor,
# e.g. ``21.09`` / ``24.0`` (Galaxy's ``general.PROFILE_PATTERN``). ``profile`` is
# optional — its absence means the 16.01 default, which is valid, so only a present
# malformed value is flagged.
_PROFILE_PATTERN = re.compile(r"^[12]\d\.\d{1,2}$")


class CommandPresent(CheckRule):
    """GTR044 — the tool should define a non-empty ``<command>``.

    Reimplements planemo `CommandMissing` (no `<command>`) + `CommandEmpty` (a
    `<command>` whose body is empty), `galaxy.tool_util.linters.command`. A tool with
    no command template cannot run. Detect-only: the template is author content.

    A tool that uses macros is **skipped** for the *missing* case: a top-level
    ``<expand>`` (e.g. ``<expand macro="version_command_config"/>``) commonly injects
    the ``<command>`` from an imported macro. planemo lints the macro-*expanded* tool,
    but this tier reads the raw tree, so it cannot prove the command absent — skipping
    avoids false-positiving the dominant macro-supplied-command pattern (61% of the
    naive findings corpus-wide). An *empty* literal ``<command>`` with no child
    ``<expand>`` is still genuinely empty and flagged.
    """

    meta: ClassVar[RuleMeta] = RuleMeta(
        code="GTR044",
        summary="Tool should define a non-empty <command>.",
        since="0.0.1",
        cite=_IUC,
        detect_only=True,
        rulesets=frozenset({"strict"}),
        planemo_linters=frozenset({"CommandEmpty", "CommandMissing"}),
    )

    def detect(self, document: ToolDocument, /) -> Iterable[Violation]:
        root = document.root
        command = root.find("command")
        if command is None:
            if not has_macros(root):  # a macro may inject the <command>
                yield _violation(document, root, self.meta, "no <command> defined")
        elif not (command.text or "").strip() and len(command) == 0:
            # An <expand> child would supply the body from a macro; a childless,
            # text-empty <command> is genuinely empty.
            yield _violation(document, command, self.meta, "<command> is empty")


class ProfileFormatValid(CheckRule):
    """GTR045 — a declared ``profile`` should be a valid Galaxy profile version.

    Reimplements planemo `ToolProfileInvalid`, `galaxy.tool_util.linters.general`. A
    ``profile`` that is not ``<year>.<minor>`` (e.g. ``21.09``) is silently ignored by
    Galaxy. Absent ``profile`` (the 16.01 default) is valid, not flagged. A ``@…@``
    macro token (``profile="@PROFILE@"``) is skipped — planemo lints the *expanded*
    tool, but this tier runs on the raw tree, so the token resolves later. Detect-only.
    """

    meta: ClassVar[RuleMeta] = RuleMeta(
        code="GTR045",
        summary="A declared profile should be a valid <year>.<minor> version.",
        since="0.0.1",
        cite=_IUC,
        detect_only=True,
        rulesets=frozenset({"strict"}),
        planemo_linters=frozenset({"ToolProfileInvalid"}),
    )

    def detect(self, document: ToolDocument, /) -> Iterable[Violation]:
        root = document.root
        profile = root.get("profile")
        if profile is None or "@" in profile:
            return  # absent (the 16.01 default) or a macro token like @PROFILE@
        if _PROFILE_PATTERN.fullmatch(profile) is None:
            yield _violation(
                document,
                root,
                self.meta,
                f"profile {profile!r} is not a valid <year>.<minor> version",
            )


class RequirementNamePresent(CheckRule):
    """GTR046 — a package ``<requirement>`` must name its package.

    Reimplements planemo `RequirementNameMissing`, `galaxy.tool_util.linters.general`.
    A ``type="package"`` requirement (Galaxy's default when ``type`` is omitted) whose
    body is empty names no package, so the conda solve has nothing to install.
    Detect-only.
    """

    meta: ClassVar[RuleMeta] = RuleMeta(
        code="GTR046",
        summary="A package <requirement> must name its package.",
        since="0.0.1",
        cite=_IUC,
        detect_only=True,
        rulesets=frozenset({"strict"}),
        planemo_linters=frozenset({"RequirementNameMissing"}),
    )

    def detect(self, document: ToolDocument, /) -> Iterable[Violation]:
        requirements = document.root.find("requirements")
        if requirements is None:
            return
        for requirement in requirements.findall("requirement"):
            if requirement.get("type", "package") != "package":
                continue
            if not (requirement.text or "").strip():
                yield _violation(
                    document,
                    requirement,
                    self.meta,
                    "package requirement has no name",
                )


class ToolVersionWhitespace(CheckRule):
    """GTR047 — the tool ``version`` should not be wrapped in whitespace.

    Reimplements planemo `ToolVersionWhitespace`, `galaxy.tool_util.linters.general`.
    Detect-only **by design**: unlike a ``<requirement>`` version (auto-trimmed by the
    GTR035 codemod), the tool ``version`` is used *raw* as the tool's identity, so
    trimming it would change which tool this is — we flag it but never edit it. (Tool
    ``id`` whitespace is caught by GTR023, the id charset check.)
    """

    meta: ClassVar[RuleMeta] = RuleMeta(
        code="GTR047",
        summary="Tool version should not be wrapped in whitespace.",
        since="0.0.1",
        cite=_IUC,
        detect_only=True,
        rulesets=frozenset({"strict"}),
        planemo_linters=frozenset({"ToolVersionWhitespace"}),
    )

    def detect(self, document: ToolDocument, /) -> Iterable[Violation]:
        root = document.root
        version = root.get("version")
        if version is not None and version != version.strip():
            yield _violation(
                document,
                root,
                self.meta,
                f"tool version {version!r} is wrapped in whitespace",
            )


# Recognized container-identifier shapes (planemo `containers.CONTAINER_PREFIXES` +
# `DOCKER_IMAGE_RE`): a known registry prefix, or a Docker-Hub ``<image>[:<tag>]``.
_CONTAINER_PREFIXES = ("quay.io/biocontainers/", "docker://", "oras://")
_DOCKER_IMAGE = re.compile(
    r"^[a-zA-Z0-9][a-zA-Z0-9._-]*(/[a-zA-Z0-9._-]+)*(:[\w][\w.-]*)?$"
)


class ContainerShapeRecognized(CheckRule):
    """GTR051 — a ``<container>`` identifier should match a recognized shape.

    Reimplements planemo `ContainerImageShape`, `galaxy.tool_util.linters.containers`.
    Recognized: a ``quay.io/biocontainers/`` / ``docker://`` / ``oras://`` prefix, or a
    Docker-Hub ``<image>[:<tag>]`` reference. An identifier carrying a ``@…@`` macro
    token is **skipped** — it resolves at expansion, and this tier reads the raw tree
    (the GTR045 boundary). Detect-only.
    """

    meta: ClassVar[RuleMeta] = RuleMeta(
        code="GTR051",
        summary="A <container> identifier should match a recognized shape.",
        since="0.0.1",
        cite=_IUC,
        detect_only=True,
        rulesets=frozenset({"strict"}),
        planemo_linters=frozenset({"ContainerImageShape"}),
    )

    def detect(self, document: ToolDocument, /) -> Iterable[Violation]:
        requirements = document.root.find("requirements")
        if requirements is None:
            return
        for container in requirements.findall("container"):
            identifier = (container.text or "").strip()
            if not identifier:
                continue
            if identifier.startswith(_CONTAINER_PREFIXES):
                continue
            if _DOCKER_IMAGE.match(identifier):
                continue
            if "@" in identifier:
                continue  # an unexpanded macro token -> unprovable on the raw tree
            yield _violation(
                document,
                container,
                self.meta,
                f"container '{identifier}' has an unrecognized shape",
            )


class StdioRegexValid(CheckRule):
    """GTR053 — a ``<stdio>`` ``<regex match>`` should be a valid regular expression.

    Reimplements planemo `StdIORegex`, `galaxy.tool_util.linters.stdio`. A ``match``
    that does not compile silently never matches, so the error condition it guards goes
    undetected. Like planemo, only a tool with exactly one ``<stdio>`` is checked.
    Detect-only.
    """

    meta: ClassVar[RuleMeta] = RuleMeta(
        code="GTR053",
        summary="A <stdio> <regex match> should be a valid regular expression.",
        since="0.0.1",
        cite=_IUC,
        detect_only=True,
        rulesets=frozenset({"strict"}),
        planemo_linters=frozenset({"StdIORegex"}),
    )

    def detect(self, document: ToolDocument, /) -> Iterable[Violation]:
        stdios = document.root.findall("stdio")
        if len(stdios) != 1:
            return
        for child in stdios[0]:
            if child.tag != "regex":
                continue
            match = child.get("match")
            if match and not _is_valid_regex(match):
                yield _violation(
                    document,
                    child,
                    self.meta,
                    f"stdio regex match {match!r} is not a valid regular expression",
                )
