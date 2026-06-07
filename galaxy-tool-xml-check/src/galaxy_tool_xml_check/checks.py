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

import ast
import re
import warnings
from collections.abc import Iterable
from typing import TYPE_CHECKING, ClassVar

from galaxy_tool_refactor_rules.meta import RuleMeta
from galaxy_tool_refactor_rules.violation import Violation
from galaxy_tool_xml.cdata import cdata_wrappable, needs_cdata
from galaxy_tool_xml.cheetah_refs import referenced_identifiers
from galaxy_tool_xml.command_text import unquoted_cheetah_vars
from galaxy_tool_xml.command_vars import input_param_info
from galaxy_tool_xml.macros import expand_from_tree, has_macros
from galaxy_tool_xml.shell_oracle import quote_is_behavior_preserving
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
    (``SingleQuoteCommandVars``) auto-quotes the behaviour-preserving occurrences, so
    this reports one finding only per unquoted shell-line ``$var`` it *cannot* — a
    free-form ``text`` param or ``multiple=`` splat in a word-splitting position, a
    dataset-label attr, ``$on_string``, a ``#set``/loop var, or (when the
    ``shell-oracle`` extra is present) an fd-dup target. The residual is computed with
    the **same** shared tier-1 policy ``quote_is_behavior_preserving`` the fixer uses
    (value-domain ``provably_quotable``, plus the bashlex fd-dup narrowing when the
    extra is installed), so the fix/advisory split never drifts. A
    mixed-content ``<command>`` (which GTR020.1 skips wholesale) reports all its
    unquoted vars. Cheetah directive lines and already-quoted references are excluded
    by the read-only ``command_text`` lexer.
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
        # GTR020.1 only rewrites a pure-text body; in a mixed-content <command> it fixes
        # nothing, so every unquoted var there is residual.
        mixed_content = len(command) > 0
        for occurrence in unquoted_cheetah_vars(text):
            fixed_by_gtr020_1 = not mixed_content and quote_is_behavior_preserving(
                text, occurrence=occurrence, kinds=kinds, structural=structural
            )
            if fixed_by_gtr020_1:
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


class CitationsPresent(CheckRule):
    """GTR038 — the tool should declare at least one non-empty citation.

    Reimplements planemo's `CitationsMissing` (no `<citations>`) and `CitationsNoText`
    (an empty ``doi``/``bibtex`` citation), `galaxy.tool_util.linters.citations`.
    Detect-only: a citation is author-supplied content, never synthesised.
    """

    meta: ClassVar[RuleMeta] = RuleMeta(
        code="GTR038",
        summary="Tool should declare a non-empty <citation> (doi/bibtex).",
        since="0.0.1",
        cite=_IUC,
        detect_only=True,
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
    )

    def detect(self, document: ToolDocument, /) -> Iterable[Violation]:
        root = document.root
        for tag in ("command", "help"):
            element = root.find(tag)
            if element is not None and "TODO" in (element.text or ""):
                msg = f"<{tag}> contains a 'TODO' placeholder"
                yield _violation(document, element, self.meta, msg)


# A valid Cheetah placeholder name (Galaxy `is_valid_cheetah_placeholder`): a leading
# letter/underscore then word characters. An output name must be one to be addressable.
_CHEETAH_PLACEHOLDER = re.compile(r"^[a-zA-Z_]\w*$")


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


# Recognized container-identifier shapes (planemo `containers.CONTAINER_PREFIXES` +
# `DOCKER_IMAGE_RE`): a known registry prefix, or a Docker-Hub ``<image>[:<tag>]``.
_CONTAINER_PREFIXES = ("quay.io/biocontainers/", "docker://", "oras://")
_DOCKER_IMAGE = re.compile(
    r"^[a-zA-Z0-9][a-zA-Z0-9._-]*(/[a-zA-Z0-9._-]+)*(:[\w][\w.-]*)?$"
)


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


def _is_valid_regex(pattern: str, /) -> bool:
    """Whether *pattern* compiles as a regular expression (``re.error`` boundary)."""
    try:
        re.compile(pattern)
    except re.error:
        return False
    return True


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


def _param_name(param: etree._Element, /) -> str | None:
    """Galaxy's resolved parameter name: ``name``, else derived from ``argument``.

    Mirrors ``galaxy.tool_util.parser.util._parse_name``: when ``name`` is absent the
    name is derived from ``argument`` (leading dashes stripped, the rest ``-``→``_``).
    Returns ``None`` when the param declares neither (the GTR054 case).
    """
    name = param.get("name")
    if name is not None:
        return str(name)
    argument = param.get("argument")
    if argument is None:
        return None
    return str(argument).lstrip("-").replace("-", "_")


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


def _select_params(root: etree._Element, /) -> Iterable[tuple[etree._Element, str]]:
    """Each input ``<param type="select">`` with its resolved name."""
    for param, name in _iter_named_params(root):
        if param.get("type") == "select":
            yield param, name


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


def _string_as_bool(value: object, /) -> bool:
    """Galaxy's ``string_as_bool``: truthy for ``true``/``yes``/``on``/``1`` (any case).

    Case-insensitive, mirroring ``galaxy.util.string_as_bool``.
    """
    return str(value).lower() in ("true", "yes", "on", "1")


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
