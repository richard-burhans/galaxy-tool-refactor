"""A small read-only lexer over ``<command>`` body text (the GTR020.2 substrate).

Galaxy command text is Cheetah that renders to a shell script. To tell a genuine
shell-argument ``$var`` (which the IUC ``single-quote your Cheetah variables``
practice is about) from template logic and quoted literals, we need to track two
things the crude regex cannot:

- **Cheetah directive lines** (``#if``, ``#set``, ``##`` comments, …) — their
  ``$var`` references are template control flow, not shell arguments.
- **Shell quote state across newlines** — a ``$var`` inside a ``'…'`` / ``"…"``
  span is already quoted, and such a span may cross line boundaries.

This is the **read-only** slice of the eventual Cheetah/shell lexer (the codemod
tier's deferred M5): it classifies, it never rewrites, so it needs none of the
matcher language / mutation cursors / macro provenance that a rewriting lexer
would. It is deliberately a lexer, not a parser — no Cheetah expression grammar,
no shell AST; escapes (``\\'``) are not interpreted.

It lives in tier 1 (the parsing foundation) rather than the advisory-check tier so
that **both** the detect-only GTR020.2 check (tier 3.5) *and* the GTR020 quoting
codemod (tier 2) can share it without a tier-2→tier-3.5 upward dependency. Each
``UnquotedVar`` carries absolute ``start``/``end`` character offsets so the codemod
can splice a single-quote pair around exactly the occurrence it found. Sized by
``scripts.measure command-unquoted-var``; see the check tier's ``docs/decisions.md``
D4 and ``galaxy-tool-xml/docs/decisions.md`` §16.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# A ``$name`` / ``${name}`` / ``$obj.attr`` Cheetah variable reference. ``$1`` and
# ``$(…)`` are not Cheetah variables (no leading ``[A-Za-z_]``), so they are
# excluded — matching ``scripts.measure``'s ``_CHEETAH_VAR``.
_CHEETAH_VAR = re.compile(r"\$\{?[A-Za-z_][\w.]*\}?")


@dataclass(frozen=True)
class UnquotedVar:
    """A genuinely-unquoted shell-line Cheetah ``$var`` occurrence.

    Attributes:
        name: The reference as written, e.g. ``"$input"`` or ``"${x.y}"``.
        line_offset: 0-based count of newlines before the occurrence in the
            scanned text — add to the ``<command>`` element's ``sourceline`` for
            the file line.
        start: 0-based character offset of the occurrence's first character
            (the ``$``) in the scanned text. ``text[start:end] == name``.
        end: Character offset one past the occurrence's last character — the
            half-open span the GTR020 codemod wraps in single quotes.
    """

    name: str
    line_offset: int
    start: int
    end: int


def unquoted_cheetah_vars(text: str, /) -> list[UnquotedVar]:
    """Every fully-unquoted shell-line Cheetah ``$var`` in *text*, in order.

    "Fully unquoted" = outside both ``'…'`` and ``"…"`` (a double-quoted ``$var``
    is a lesser concern and is intentionally *not* reported — it keeps the check
    to the genuine word-splitting/injection hazard and matches the
    ``command-unquoted-var`` target population). Quote state is tracked across
    newlines; a line whose first non-blank character is ``#`` **while not inside a
    quote** is a Cheetah directive/comment and its ``$var``s are skipped.
    """
    found: list[UnquotedVar] = []
    in_single = in_double = False
    line_offset = 0
    index = 0
    length = len(text)
    at_line_start = True
    while index < length:
        if at_line_start and not in_single and not in_double:
            probe = index
            while probe < length and text[probe] in " \t":
                probe += 1
            if probe < length and text[probe] == "#":
                newline = text.find("\n", index)
                if newline == -1:
                    break
                index = newline + 1
                line_offset += 1
                at_line_start = True
                continue
        at_line_start = False
        char = text[index]
        if char == "\n":
            line_offset += 1
            at_line_start = True
            index += 1
        elif char == "'" and not in_double:
            in_single = not in_single
            index += 1
        elif char == '"' and not in_single:
            in_double = not in_double
            index += 1
        elif char == "$" and not in_single and not in_double:
            match = _CHEETAH_VAR.match(text, index)
            if match is None:
                index += 1
            else:
                found.append(
                    UnquotedVar(
                        name=match.group(),
                        line_offset=line_offset,
                        start=match.start(),
                        end=match.end(),
                    )
                )
                index = match.end()
        else:
            index += 1
    return found
