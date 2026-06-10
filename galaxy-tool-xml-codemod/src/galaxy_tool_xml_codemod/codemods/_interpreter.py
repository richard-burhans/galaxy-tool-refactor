"""Eligibility core for the ``16_04_fix_interpreter`` rewrite (pure, shared).

Galaxy's legacy ``<command interpreter="python">myscript.py …</command>`` ran, at
runtime, as ``python '<tool_dir>/myscript.py' …`` — it took the first whitespace token
of the *substituted* command line, resolved it under the tool directory, and prepended
the interpreter attribute **verbatim**::

    executable = command_line.split()[0]            # after Cheetah substitution
    abs_executable = os.path.join(tool_dir, executable)
    command_line = command_line.replace(executable, abs_executable, 1)
    command_line = interpreter + " " + command_line  # plain string concatenation

(byte-identical from ``release_16.04`` ``lib/galaxy/tools/evaluation.py:478-484``
through ``release_20.01`` ``:509-514`` — the whole era honoring ``interpreter=``;
removed by 20.09; gated on ``if interpreter:``, so an *empty* attribute was ignored.)
From profile 16.04 the attribute is ignored, so an upgraded tool breaks unless the
command is rewritten (Galaxy's ``16_04_fix_interpreter`` *must-fix* code).

Because the composition is verbatim concatenation, **any** non-empty interpreter
value — flags (``Rscript --no-save``), non-scripts (``java -jar``), even compound
prefixes (``export …; java -jar``) — rewrites mechanically. The only static
requirement is that the script is **statically the first token**: the command body
must start with a literal script filename, not a Cheetah directive
(``#if``/``#for``/…) or a ``$var`` (Galaxy chose the token *after* Cheetah
substitution; we cannot). This module defines that "bucket A" eligibility as a pure
predicate so the corpus measure (``scripts/measure.py interpreter-bucket-split``)
and the codemod (``fix_interpreter.py``) agree by construction. See
``../../docs/upgrade_research/16_04_fix_interpreter.md``.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

    from lxml import etree

# A literal script filename: starts alphanumeric/underscore, has an extension, and
# carries no Cheetah/shell sigils (``$``, ``@``, ``#``, quotes, spaces).
_SCRIPT_TOKEN = re.compile(r"^[A-Za-z0-9_][\w./-]*\.[A-Za-z0-9_]+$")
# A line whose first token is a Cheetah directive (block or line form).
_CHEETAH_DIRECTIVE_LINE = re.compile(
    r"^#(?:if|for|set|def|import|echo|while|try|raw|slurp|end|else|elif)\b"
)


def first_command_token_span(body: str, /) -> tuple[str, int] | None:
    """The first content token of a command *body* and its anchor offset, or ``None``.

    Skips blank lines and ``##`` Cheetah comments; returns ``None`` if the first
    content line is a Cheetah directive (the script is then not statically first).
    The second element is the **character offset in *body* of the chosen content
    line** — a rewrite must restrict itself to ``body[offset:]`` so a script name
    appearing inside a leading ``##`` comment (or any skipped line) is never
    mistargeted; only the real, first invocation is rewritten.
    """
    offset = 0
    for raw_line in body.splitlines(keepends=True):
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("##"):
            offset += len(raw_line)
            continue
        if _CHEETAH_DIRECTIVE_LINE.match(stripped):
            return None
        return stripped.split()[0], offset
    return None


def first_command_token(body: str, /) -> str | None:
    """Return the first content token of a command *body*, or ``None`` (see span)."""
    span = first_command_token_span(body)
    return span[0] if span is not None else None


def interpreter_rewrite(
    root: etree._Element, /, *, tool_dir: Path | None = None
) -> tuple[str, str, int] | None:
    """The full ``16_04_fix_interpreter`` rewrite plan, or ``None`` if not bucket A.

    Returns ``(interpreter, token, offset)`` when *root* is "bucket A" — any
    non-empty ``interpreter`` whose command body begins with a literal script
    filename — where *offset* is the body anchor for the rewrite (see
    ``first_command_token_span``). Else ``None``: bucket B (non-literal first
    token), or an empty ``interpreter=""`` (legacy gated on ``if interpreter:``,
    so an empty attribute was ignored — there is no composition to reproduce).
    When *tool_dir* is given the named script must exist beside the tool (kills
    false positives); the check is skipped when it is ``None``.
    """
    command = root.find("command")
    if command is None:
        return None
    interpreter = command.get("interpreter")
    if not interpreter:  # absent, or empty = legacy-ignored
        return None
    span = first_command_token_span("".join(command.itertext()))
    if span is None:
        return None
    token, offset = span
    if not _SCRIPT_TOKEN.match(token):
        return None
    if tool_dir is not None and not (tool_dir / token).is_file():
        return None
    return interpreter, token, offset


def interpreter_rewrite_target(
    root: etree._Element, /, *, tool_dir: Path | None = None
) -> str | None:
    """The script token a ``16_04_fix_interpreter`` rewrite would path-qualify.

    The token-only view of ``interpreter_rewrite`` (the corpus
    ``interpreter-bucket-split`` measure's bucket-A predicate); ``None`` when not
    bucket A. See ``interpreter_rewrite`` for the full plan the codemod uses.
    """
    plan = interpreter_rewrite(root, tool_dir=tool_dir)
    return plan[1] if plan is not None else None
