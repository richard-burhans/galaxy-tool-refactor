"""Macro-library advisory checks (``<macros>``: ``<xml>`` vs ``<token>``)."""


from __future__ import annotations

import re
from collections.abc import Iterable, Iterator
from typing import TYPE_CHECKING, ClassVar

from galaxy_tool_refactor_rules.meta import RuleMeta
from galaxy_tool_refactor_rules.violation import Violation
from galaxy_tool_source.macros import imported_macro_paths
from lxml import etree

from galaxy_tool_lint.rules import CheckRule

if TYPE_CHECKING:
    from pathlib import Path

    from galaxy_tool_source.document import ToolDocument

from galaxy_tool_lint.checks._shared import _IUC, _violation

# A Cheetah *directive* line: the first non-blank character is ``#`` followed by a
# directive keyword. ``##`` (a Cheetah comment) does not match, and a bare ``$ref``
# does not either -- a ``$`` inside an ``<xml>`` macro is ordinary and correct (the
# macro's params are referenced by the command that expands around it).
_CHEETAH_DIRECTIVE = re.compile(
    r"^[ \t]*#(?:if|unless|else|elif|end|for|while|repeat|set|del|silent|echo|import"
    r"|from|def|block|call|filter|try|except|finally|raise|assert|pass|break|continue"
    r"|return|include|attr|extends|implements|slurp|compiler)\b",
    re.MULTILINE,
)

# Elements whose text content Galaxy evaluates as a Cheetah template. An ``<xml>``
# macro that wraps one of these *and* carries the Cheetah inside it is correct --
# the directive is spliced in as that element's own body and is evaluated there.
#
# ``environment_variable`` is the SINGULAR element, which is what a macro splices; an
# earlier spelling of this set said ``env_var``, a tag that does not exist in any
# vendored schema (0 occurrences in ``galaxy-26.1.xsd``, against 1 each for
# ``environment_variable`` and its plural container). The XSD's own documentation for
# it reads "The body should be a Cheetah template block that may reference the tool's
# inputs", so a macro wrapping one is the canonical splice-a-single-child pattern --
# and it was being reported.
_CHEETAH_CONTEXT_TAGS = frozenset(
    {
        "command",
        "configfile",
        "configfiles",
        "version_command",
        "environment_variables",
        "environment_variable",
    }
)

# Elements whose text Galaxy never evaluates as Cheetah, and which legitimately carry
# prose or sample code. ``<help>`` is the one that matters: an indented shell or Python
# sample (``#import numpy``, ``#for f in *.fastq``, ``#include <stdio.h>``) starts a
# line with ``#`` + a directive keyword and was reported, with a message about
# ``<command>`` that makes no sense for help text. Markdown ``#`` headings were never
# affected -- the regex requires a directive keyword immediately after the ``#``.
_PROSE_TAGS = frozenset({"help", "description", "citations", "citation", "edam_topics"})


class CheetahInXmlMacro(CheckRule):
    """GTR104 — Cheetah directives in the body of an ``<xml>`` macro.

    ``<xml>`` and ``<token>`` are not interchangeable and the difference is invisible
    at the call site. A ``<token>`` is **text** substitution: ``@NAME@`` is replaced
    wherever it appears, including inside the CDATA of ``<command>``. An ``<xml>``
    macro is **tree** splicing: ``<expand macro="name"/>`` is replaced by the macro's
    child *elements*.

    So a conditional written as an ``<xml>`` macro and "expanded" inside a command
    never arrives. ``<expand .../>`` written inside ``<command>`` is not an element at
    all -- it is characters in the command's text, and Galaxy's macro pass only
    rewrites elements -- so the literal string ``<expand macro="..."/>`` is handed to
    Cheetah, the directive never runs, and the flag it was supposed to add is silently
    missing from every job. Nothing reports it: the XML is valid, ``planemo lint`` is
    silent, and the tool runs.

    Flagged only for a directive that is **not** inside a Cheetah-evaluated element
    (``<command>``, ``<configfile>``, ``<version_command>``, …): an ``<xml>`` macro
    whose body *is* a ``<command>`` element splices that element in whole and its
    Cheetah is evaluated normally, which is a legitimate and common pattern.

    Reads the tool's inline ``<macros>`` and, transitively, the macro files it imports
    (``macros.imported_macro_paths``) -- the ``<xml>`` macros of a suite live in
    ``macros.xml``, not in the tool. ⚠ That helper resolves only **relative imports
    that stay within the tool's directory**: it skips an absolute path or one
    containing ``..`` by design, and Galaxy resolves both. So a suite whose macros live
    at ``../shared/macros.xml`` -- a common tools-iuc layout -- is not scanned, and
    this rule under-reports rather than misreports. Widening that is a tier-1 change
    shared with GTR025/GTR038 and does not belong to this rule.

    A finding in a shared macro file is reported once per tool that imports it; the
    message names the file and the macro.
    Violations anchor on an element of the tool's own tree (the ``<import>`` for an
    imported file) because a foreign tree has no path in ``document.tree``.
    """

    meta: ClassVar[RuleMeta] = RuleMeta(
        code="GTR104",
        summary="An <xml> macro should not contain Cheetah (use a <token>).",
        since="0.3.10",
        cite=_IUC,
        detect_only=True,
        rulesets=frozenset({"strict"}),
    )

    def detect(self, document: ToolDocument, /) -> Iterable[Violation]:
        root = document.root
        macros = root.find("macros")
        if macros is not None:
            for macro, directive in _cheetah_macros(macros):
                yield _violation(
                    document,
                    macro,
                    self.meta,
                    f"<xml> macro {macro.get('name')!r} contains the Cheetah directive "
                    f"{directive!r}, which an <expand> inside <command> never "
                    f"evaluates -- declare it as a <token> instead",
                )
        for path, import_element in _imported_macro_roots(document):
            imported = _parse(path)
            if imported is None:
                continue
            for macro, directive in _cheetah_macros(imported):
                yield _violation(
                    document,
                    import_element,
                    self.meta,
                    f"<xml> macro {macro.get('name')!r} in {path.name} (line "
                    f"{macro.sourceline}) contains the Cheetah directive "
                    f"{directive!r}, which an <expand> inside <command> never "
                    f"evaluates -- declare it as a <token> instead",
                )


def _xml_macros(macros_root: etree._Element, /) -> Iterator[etree._Element]:
    """Every macro definition Galaxy classifies as ``type="xml"``.

    ``<xml>`` is only a *shortcut*: ``galaxy.util.xml_macros._load_embedded_macros``
    reads every ``<macro>`` and, when ``type`` is absent, **defaults it to ``"xml"``**
    before the ``<template>``/``<xml>``/``<token>`` shortcuts are folded in. So
    ``<macro name="x">`` and ``<macro name="x" type="xml">`` are the same thing as
    ``<xml name="x">`` and carry the same bug; scanning only ``iter("xml")`` missed
    both.
    """
    for macro in macros_root.iter("xml"):
        yield macro
    for macro in macros_root.iter("macro"):
        if (macro.get("type") or "xml") == "xml":
            yield macro


def _cheetah_macros(
    macros_root: etree._Element, /
) -> Iterator[tuple[etree._Element, str]]:
    """Yield ``(xml_macro, first_directive)`` for each offending xml-type macro."""
    for macro in _xml_macros(macros_root):
        if macro.get("name") is None:
            continue
        directive = _first_directive(macro)
        if directive is not None:
            yield macro, directive


def _first_directive(macro: etree._Element, /) -> str | None:
    """The first Cheetah directive in *macro* outside a Cheetah-evaluated element."""
    for element in macro.iter():
        if not isinstance(element.tag, str):
            continue
        if _within_cheetah_context(element, macro):
            continue
        if _within_prose(element, macro):
            continue
        for text in (element.text, element.tail):
            match = _CHEETAH_DIRECTIVE.search(text or "")
            if match is not None:
                return match.group(0).strip()
    return None


def _within_prose(element: etree._Element, macro: etree._Element, /) -> bool:
    """Whether *element* sits at or under a tag whose text is prose, not Cheetah."""
    current: etree._Element | None = element
    while current is not None and current is not macro:
        if isinstance(current.tag, str) and current.tag in _PROSE_TAGS:
            return True
        current = current.getparent()
    return False


def _within_cheetah_context(
    element: etree._Element, macro: etree._Element, /
) -> bool:
    """Whether *element* sits at or under a Cheetah-evaluated tag inside *macro*."""
    current: etree._Element | None = element
    while current is not None and current is not macro:
        if isinstance(current.tag, str) and current.tag in _CHEETAH_CONTEXT_TAGS:
            return True
        current = current.getparent()
    return False


def _imported_macro_roots(
    document: ToolDocument, /
) -> Iterator[tuple[Path, etree._Element]]:
    """Yield each imported macro path with the ``<import>`` element to anchor on."""
    macros = document.root.find("macros")
    if macros is None:
        return
    imports = macros.findall("import")
    if not imports:
        return
    by_name = {
        (element.text or "").strip(): element for element in imports if element.text
    }
    for path in imported_macro_paths(document):
        # A transitively-imported file has no <import> of its own in this tool, so it
        # anchors on the first <import> -- the edge the tool is responsible for.
        yield path, by_name.get(path.name, imports[0])


def _parse(path: Path, /) -> etree._Element | None:
    """The root of *path*, or ``None`` when it will not parse (LBYL, never raises)."""
    try:
        return etree.parse(str(path)).getroot()
    except (OSError, etree.XMLSyntaxError):
        return None
