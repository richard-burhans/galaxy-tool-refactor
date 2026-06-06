"""Find every Cheetah ``$var`` reference across a tool's Cheetah-templated sections.

The read-only **reference model** powering ``find-references`` (and, later, param
refactors). Where ``command_text.unquoted_cheetah_vars`` reports only the
fully-unquoted shell-line ``$var``\\ s in ``<command>``, this reports **every**
reference in **every** Cheetah-templated section: quoted or not, inside
``#if``/``#set`` directives, in inline ``<configfile>``\\ s, env vars, output
labels, dynamic options — the sections Galaxy runs through ``fill_template``
(see ``../../docs/galaxy_processing_model.md``).

Resolution is **faithful** when the optional ``cheetah-cdm`` extra is installed: the
CT3 span lexer (``cheetah_cdm.cheetah_spans``, §19) classifies each region exactly as
Cheetah does, so a ``$var`` inside a ``##``/``#* *#`` comment, a ``#raw`` block, or
behind an escaped ``\\$`` is **not** reported — only genuine references survive
(``PLACEHOLDER`` spans plus the ``$var``\\ s in ``#if``/``#set``/… ``DIRECTIVE`` heads).
This matches what the rename mutator (``cheetah_rename``, also faithful) would touch, so
``find-references`` and ``rename-param`` agree. When the extra is absent (or CT3 cannot
compile the section, ~0.4%) it falls back to the conservative ``_CHEETAH_VAR`` regex,
which over-reports the comment/raw/escaped cases — the safe direction for a read-only
query. Correctness for novel tool XML (not a corpus-fitted superset) is the goal; the
faithful path is used whenever it is available. References from imported macros /
``<expand>`` live in the macro files and are out of scope for this raw-tree scan.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from lxml import etree

from galaxy_tool_xml.cheetah_cdm import SpanKind, cheetah_spans

# ``$name`` / ``${name}`` / ``$obj.attr`` — a Cheetah variable reference (``$1`` and
# ``$(…)`` excluded). Mirrors ``command_text._CHEETAH_VAR`` / ``scripts.measure``.
_CHEETAH_VAR = re.compile(r"\$\{?[A-Za-z_][\w.]*\}?")


@dataclass(frozen=True)
class CheetahRef:
    """One Cheetah ``$var`` reference found in a tool's templated text.

    Attributes:
        name: The reference as written, e.g. ``"$input"`` or ``"${adv.x}"``.
        segments: The dotted/indexed identifier segments, e.g. ``("adv", "x")`` for
            ``${adv.x}`` — used to match a reference against a parameter name (the leaf
            of a ``$cond.sub`` access is a segment, not just the root).
        section: Which templated section it came from (``"command"``,
            ``"configfile:script"``, ``"output_data_label:out1"``, …).
        sourceline: Best-effort 1-based file line (the section element's ``sourceline``
            plus the newline count before the occurrence), or ``0`` if unknown.
        start: 0-based character offset of the ``$`` within the section text.
        end: Character offset one past the reference's last character.
    """

    name: str
    segments: tuple[str, ...]
    section: str
    sourceline: int
    start: int
    end: int


def _segments(name: str, /) -> tuple[str, ...]:
    """The identifier segments of a reference (``"${adv.x}"`` → ``("adv", "x")``)."""
    bare = name.translate({ord("$"): None, ord("{"): None, ord("}"): None})
    parts = (part.rstrip("]") for part in re.split(r"[.\[]", bare))
    return tuple(part for part in parts if part)


def _ref_at(
    name: str, start: int, end: int, /, *, section: str, base_line: int, text: str
) -> CheetahRef:
    """Build a :class:`CheetahRef` for *name* at absolute span ``[start, end)``."""
    return CheetahRef(
        name=name,
        segments=_segments(name),
        section=section,
        sourceline=base_line + text.count("\n", 0, start),
        start=start,
        end=end,
    )


def cheetah_references(
    text: str, /, *, section: str = "text", base_line: int = 1
) -> list[CheetahRef]:
    """Every Cheetah ``$var`` reference in *text*, in source order.

    Faithful when the ``cheetah-cdm`` extra is present (CT3 span lexer): a reference is
    a ``PLACEHOLDER`` span or a ``$var`` in a ``DIRECTIVE`` head (``#if`` / ``#set``);
    ``COMMENT`` spans, ``#raw`` content, and an escaped ``\\$`` are excluded — Cheetah
    does not treat those as references. Falls back to the conservative ``_CHEETAH_VAR``
    regex (a superset) when the lexer is unavailable / bails. *base_line* is the file
    line the text starts on (an element's ``sourceline``); each reference's
    ``sourceline`` is ``base_line`` plus the newline count before it.
    """
    if "$" not in text:
        return []  # a Cheetah reference always starts with ``$``; skip the lexer
    spans = cheetah_spans(text)
    if spans is None:
        # Conservative fallback: every regex ``$var``, including comment/raw/escaped.
        return [
            _ref_at(
                match.group(),
                match.start(),
                match.end(),
                section=section,
                base_line=base_line,
                text=text,
            )
            for match in _CHEETAH_VAR.finditer(text)
        ]
    refs: list[CheetahRef] = []
    for span in spans:
        if span.kind is SpanKind.COMMENT:
            continue  # ## / #* *# — Cheetah ignores any $var here
        if span.kind is SpanKind.PLACEHOLDER:
            # The span may carry call/index suffixes (``$arr[0]``); the regex match at
            # the span start gives the reference name shape (stops at ``[``).
            match = _CHEETAH_VAR.match(text, span.start)
            if match is not None and match.start() == span.start:
                refs.append(
                    _ref_at(
                        match.group(),
                        match.start(),
                        match.end(),
                        section=section,
                        base_line=base_line,
                        text=text,
                    )
                )
        elif span.directive == "raw":
            continue  # a #raw block is verbatim — its $vars are literal, not refs
        else:  # DIRECTIVE head — its clause may reference vars (``#if $x``, ``#set``)
            for match in _CHEETAH_VAR.finditer(span.text):
                refs.append(
                    _ref_at(
                        match.group(),
                        span.start + match.start(),
                        span.start + match.end(),
                        section=section,
                        base_line=base_line,
                        text=text,
                    )
                )
    return refs


def _scan(
    refs: list[CheetahRef], text: str | None, /, *, section: str, base_line: int | None
) -> None:
    """Append references found in *text* (a no-op for empty / ``$``-free text)."""
    if text and "$" in text:
        refs.extend(cheetah_references(text, section=section, base_line=base_line or 0))


def tool_cheetah_references(root: etree._Element, /) -> list[CheetahRef]:
    """Every Cheetah ``$var`` reference across *root*'s templated sections.

    Scans the **raw** tool tree (real file positions): ``<command>``, inline
    ``<configfile>``\\ s, ``<environment_variable>``\\ s, output ``data``/``collection``
    ``label`` attrs, dynamic ``<options>`` ``from_url``/``request_*`` attrs and
    ``<filter>`` bodies, ``<entry_point>`` attrs, and ``data_source``
    ``redirect_url_params`` — the Cheetah-``fill_template`` sections. References inside
    imported macros / ``<expand>`` are not visible here (they live in the macro files).
    """
    refs: list[CheetahRef] = []

    # On a ``<tool>`` root the ``<command>`` is the single top-level child; on a
    # ``<macros>`` library file the command fragments nest under ``<xml name="…">``,
    # so both are reached by descendant scan (configfile/option/filter already iter).
    if root.tag == "macros":
        commands = list(root.iter("command"))
    else:
        one = root.find("command")
        commands = [one] if one is not None else []
    for command in commands:
        _scan(
            refs,
            "".join(command.itertext()),
            section="command",
            base_line=command.sourceline,
        )

    for configfile in root.iter("configfile"):
        name = configfile.get("name", "")
        _scan(
            refs,
            "".join(configfile.itertext()),
            section=f"configfile:{name}",
            base_line=configfile.sourceline,
        )

    env_parent = root.find("environment_variables")
    if env_parent is not None:
        for env_var in env_parent.iter("environment_variable"):
            _scan(
                refs,
                env_var.text,
                section=f"environment_variable:{env_var.get('name', '')}",
                base_line=env_var.sourceline,
            )

    for tag in ("data", "collection"):
        for output in root.findall(f"outputs/{tag}"):
            _scan(
                refs,
                output.get("label"),
                section=f"output_{tag}_label:{output.get('name', '')}",
                base_line=output.sourceline,
            )

    for option in root.iter("option"):
        for attr in ("from_url", "request_body", "request_headers"):
            _scan(
                refs,
                option.get(attr),
                section=f"option_{attr}",
                base_line=option.sourceline,
            )
    for filter_element in root.iter("filter"):
        _scan(
            refs,
            filter_element.text,
            section="filter",
            base_line=filter_element.sourceline,
        )

    for entry_point in root.iter("entry_point"):
        for attr in ("url", "label", "port"):
            _scan(
                refs,
                entry_point.get(attr),
                section=f"entry_point_{attr}",
                base_line=entry_point.sourceline,
            )

    data_source = root.find("data_source")
    if data_source is not None:
        _scan(
            refs,
            data_source.get("redirect_url_params"),
            section="redirect_url_params",
            base_line=data_source.sourceline,
        )

    return refs


# An identifier token inside an attribute value (a datatype, a cross-ref target, a
# param name). Must start with a letter/underscore so version numbers like ``1.0.0``
# contribute nothing.
_IDENT = re.compile(r"[A-Za-z_]\w*")


def _has_inputs_ancestor(element: etree._Element, /) -> bool:
    """Whether *element* sits anywhere under an ``<inputs>`` (a param definition)."""
    return any(ancestor.tag == "inputs" for ancestor in element.iterancestors())


def referenced_identifiers(root: etree._Element, /) -> set[str]:
    """Every identifier that could name a parameter, anywhere in *root*.

    The set of identifier tokens drawn from **all element text** and **all attribute
    values**, skipping the ``name`` attr of ``<param>`` definitions (a ``<param>`` under
    ``<inputs>``) so a param isn't counted as used by its own declaration.

    Scanning all text (not just ``$var``) is what makes this sound: it captures a
    Cheetah ``$param``, a dotted ``${cond.sub}`` (both segments), and a **bare-name**
    reference in element text — an output ``<filter>`` Python expression
    (``<filter>store_ext</filter>``) or a ``<configfile>`` body. Scanning all attribute
    values subsumes every by-name param cross-reference generically (``data_ref``,
    ``format_source``, ``change_format @input``, options ``filter @ref``, …) — they are
    all attributes, so no allowlist. Conservative: a coincidental token (a
    ``format="fastq"``, a word in ``<help>``) only *protects* a like-named param. GTR034
    uses this set.
    """
    identifiers: set[str] = set()
    for text in root.itertext():
        identifiers.update(_IDENT.findall(text))
    for element in root.iter():
        attrib = getattr(element, "attrib", None)
        if attrib is None:
            continue  # comment / processing-instruction node
        skip_name = element.tag == "param" and _has_inputs_ancestor(element)
        for attr_name, value in attrib.items():
            if skip_name and attr_name == "name":
                continue
            identifiers.update(_IDENT.findall(value))
    return identifiers
