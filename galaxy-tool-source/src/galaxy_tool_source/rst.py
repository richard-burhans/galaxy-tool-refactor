"""reStructuredText validity + surgical, behaviour-preserving repair of ``<help>``.

Galaxy renders a ``<help>`` body as reStructuredText to HTML server-side
(``galaxy.util.rst_to_html``). docutils parses RST but has **no faithful RST writer**
and **no source offsets**, so repair is **surgical line-anchored editing of the
source** — anchored on the docutils reporter's line number — never
parse-and-reserialise (the same constraint the Cheetah lexer was built for).

This module is the **shared predicate** behind the GTR089 fix/advisory partition:

- ``rst_is_invalid(text)`` — the validity test (matches Galaxy's
  ``rst_to_html(error=True)``); GTR089.2 (advisory residual) reports help that is still
  invalid after repair.
- ``repair_help_rst(text)`` — the deterministic, class-based repair GTR089.1 applies. It
  fixes only the classes with an unambiguous recipe, and keeps a fix only behind a
  **strong gate**: each round must strictly reduce serious errors, introduce no new
  error class, **and** leave the docutils doctree structurally identical modulo the
  removed system messages (so the edit changed *nothing but the error*). Returns the
  repaired text, or ``None`` when nothing could be safely repaired.
"""

from __future__ import annotations

import contextlib
import io
import re

import docutils.core
import docutils.nodes
import docutils.utils

_MAX_ROUNDS = 8
_MACRO_TOKEN = re.compile(r"@[A-Z0-9_]+@")


def has_macro_token(text: str, /) -> bool:
    """Whether *text* embeds a Galaxy macro token (``@NAME@``).

    The repair mutates help text, so it leaves macro-bearing help alone (the
    unprovable-macro case): the literal ``@TOKEN@`` is what docutils sees, not the
    expanded value, so an edit there can't be proven safe.
    """
    return _MACRO_TOKEN.search(text) is not None

# Fixable error classes (normalised message text) → a deterministic, general recipe.
# These are class-keyed, not corpus-keyed: they repair any tool exhibiting the class.
# (A trailing transition is deliberately NOT here: docutils renders it as an <hr>, so
# dropping it changes the rendered help — the behaviour gate would reject it anyway.)
_TITLE_UNDERLINE_SHORT = "Title underline too short."
_ENDS_WITHOUT_BLANK = "ends without a blank line"  # the unexpected-unindent family


class _RaisingWarningStream:
    """A docutils ``warning_stream`` that raises on the first real reporter message.

    Mirrors Galaxy's ``rst_to_html`` ``FakeStream(error=True)``: any non-whitespace
    output (a warning or worse) aborts the parse, marking the RST invalid.
    """

    def write(self, message: str) -> None:
        if message and not message.isspace():
            raise ValueError(message)


def rst_is_invalid(text: str, /) -> bool:
    """Whether *text* is invalid reStructuredText (docutils — Galaxy's ``rst_invalid``).

    Publishes through docutils with a ``warning_stream`` that raises on any reported
    message and ``halt_level`` lifted so that stream is the trigger — matching
    ``galaxy.util.rst_to_html(error=True)``. docutils exposes no LBYL validity
    predicate, so the broad ``except`` is the sanctioned third-party boundary; stderr is
    redirected so a noisy role/directive can't leak past.
    """
    overrides = {
        "warning_stream": _RaisingWarningStream(),
        "halt_level": docutils.utils.Reporter.SEVERE_LEVEL + 1,
        "doctitle_xform": False,
        "output_encoding": "unicode",
    }
    try:
        with contextlib.redirect_stderr(io.StringIO()):
            docutils.core.publish_string(
                text, writer="html4css1", settings_overrides=overrides
            )
    except Exception:  # noqa: BLE001 - docutils has no LBYL validity check
        return True
    return False


def _normalise(message: str, /) -> str:
    """Collapse a docutils message to a class by erasing instance specifics."""
    message = re.sub(r"^<string>:\d+: \([^)]*\) ", "", message)
    message = re.sub(r'"[^"]*"', '"X"', message)
    message = re.sub(r"`[^`]*`", "`X`", message)
    message = re.sub(r"\b\d+\b", "N", message)
    return message.strip()


def _serious_messages(text: str, /) -> list[tuple[int | None, str]]:
    """Return ``(line, normalised_class)`` for each docutils message at level >= 2."""
    overrides = {
        "report_level": 1,
        "halt_level": 5,
        "input_encoding": "unicode",
        "doctitle_xform": False,
        "warning_stream": io.StringIO(),
    }
    try:
        with contextlib.redirect_stderr(io.StringIO()):
            doctree = docutils.core.publish_doctree(
                text, settings_overrides=overrides
            )
    except Exception:  # noqa: BLE001 - docutils parse failure: no messages
        return []
    out: list[tuple[int | None, str]] = []
    for node in doctree.findall(docutils.nodes.system_message):
        if int(node["level"]) >= 2:
            first = node.astext().splitlines()[0] if node.astext() else ""
            out.append((node.get("line"), _normalise(first)))
    return out


def _structural_signature(text: str, /) -> str | None:
    """The docutils doctree dump with system messages removed (a structure signature).

    Two RST bodies with the same signature parse to the same structure modulo the
    errors docutils reports — the behaviour-preservation oracle for a repair.
    """
    overrides = {
        "report_level": 5,  # suppress messages from the tree we compare
        "halt_level": 5,
        "input_encoding": "unicode",
        "doctitle_xform": False,
        "warning_stream": io.StringIO(),
    }
    try:
        with contextlib.redirect_stderr(io.StringIO()):
            doctree = docutils.core.publish_doctree(
                text, settings_overrides=overrides
            )
    except Exception:  # noqa: BLE001 - docutils parse failure: no signature
        return None
    for node in list(doctree.findall(docutils.nodes.system_message)):
        if node.parent is not None:
            node.parent.remove(node)
    return str(doctree.pformat())


def _plan_edits(text: str, /) -> list[tuple[int, str, str]]:
    """Plan the line edits for the fixable serious messages in *text*.

    Each edit is ``(line_index, op, payload)`` — ``op`` in
    ``{"replace", "insert_before"}``. Only classes with a deterministic
    recipe are planned; everything else is left for the GTR089.2 advisory residual.
    """
    lines = text.split("\n")
    edits: list[tuple[int, str, str]] = []
    for line, cls in _serious_messages(text):
        if line is None or not (0 <= line - 1 < len(lines)):
            continue
        idx = line - 1
        if cls == _TITLE_UNDERLINE_SHORT and idx - 1 >= 0:
            title = lines[idx - 1].rstrip()
            underline = lines[idx].strip()
            if underline and len(set(underline)) == 1:
                width = max(len(title), len(underline))
                edits.append((idx, "replace", underline[0] * width))
        elif _ENDS_WITHOUT_BLANK in cls:
            edits.append((idx, "insert_before", ""))
    return edits


def _apply_line_edits(text: str, edits: list[tuple[int, str, str]], /) -> str:
    """Apply *edits* to *text*, highest line first (so earlier edits don't shift)."""
    lines = text.split("\n")
    for idx, op, payload in sorted(edits, key=lambda edit: edit[0], reverse=True):
        if op == "replace":
            lines[idx] = payload
        elif op == "insert_before":
            lines.insert(idx, payload)
    return "\n".join(lines)


def _is_behavior_preserving(original: str, candidate: str, /) -> bool:
    """Whether *candidate* strictly improves *original* without changing its meaning."""
    before = _serious_messages(original)
    after = _serious_messages(candidate)
    if len(after) >= len(before):
        return False  # must strictly reduce serious errors
    if {cls for _line, cls in after} - {cls for _line, cls in before}:
        return False  # a new error class would be introduced
    signature = _structural_signature(original)
    return signature is not None and signature == _structural_signature(candidate)


def repair_help_rst(text: str, /) -> str | None:
    """Repair the deterministically-fixable RST errors in *text*, or ``None``.

    Iterates to a fixpoint (bounded): each round plans the fixable edits, applies them,
    and keeps the result only if it is behaviour-preserving (strictly fewer errors, no
    new class, identical doctree structure modulo the removed messages). Returns the
    repaired text if any round applied; ``None`` if nothing could be safely repaired
    (so the codemod no-ops and the residual stays GTR089.2).
    """
    current = text
    changed = False
    for _round in range(_MAX_ROUNDS):
        # Keep only the edits that are individually behaviour-preserving, so one bad
        # edit can't poison an otherwise-fixable round; then re-gate the batch.
        safe = [
            edit
            for edit in _plan_edits(current)
            if _is_behavior_preserving(current, _apply_line_edits(current, [edit]))
        ]
        if not safe:
            break
        candidate = _apply_line_edits(current, safe)
        if not _is_behavior_preserving(current, candidate):
            break
        current = candidate
        changed = True
    return current if changed else None
