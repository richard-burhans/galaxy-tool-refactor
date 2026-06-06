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
