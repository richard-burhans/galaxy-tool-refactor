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
