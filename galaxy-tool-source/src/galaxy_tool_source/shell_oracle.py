"""A read-only shell **boundary oracle** over a realized ``<command>`` line (bashlex).

This is the permanent half of the deferred Cheetah/shell **M5** layer: given the
final shell string a tool's ``<command>`` renders to, parse it with bashlex (bash's
own grammar, ported to Python) and read out the *boundary signature* — the argv word
partition and the full file-descriptor redirection topology. That signature is the
exact behaviour a single-quote edit must preserve (quoting deliberately changes bytes
while keeping the partition), so it is the rigorous successor to the value-domain
``command_vars`` heuristic. See
``docs/upgrade_research/cheetah_bashlex_boundary_oracle.md``.

bashlex is **GPL v3+**, so it is isolated behind the optional
``galaxy-tool-source[shell-oracle]`` extra rather than a hard dependency of this
MIT-licensed tier. Every entry point degrades gracefully when the extra is absent
(``shell_oracle_available()`` is
``False``; ``boundary_signature`` / ``quoting_context`` return ``None`` / ``UNKNOWN``;
``quote_is_behavior_preserving`` falls back to the value-domain ``provably_quotable``).

The quoting policy ``quote_is_behavior_preserving`` lives here, beside the value-domain
``provably_quotable`` it composes with, so the GTR020.1 fixer (tier 2) and the GTR020.2
advisory check (tier 3.5) share one notion of "safe to single-quote" and their
fix/advisory partition can never drift — exactly why ``command_vars`` lives in tier 1.

The classifier keeps each Cheetah ``$var`` **as a bash parameter expansion** (it never
substitutes a value) so bash's word-splitting semantics are faithful: an expansion in
an assignment RHS or other no-split context is safe to quote for *any* value, whereas
the same expansion as a bare command word splits and is safe only when the value is
provably space-free. It is a lexer/parse classifier, not an evaluator: ``#if`` /
``#set`` directive lines render to nothing and bashlex treats them as ``#`` comments;
constructs
bashlex cannot parse (``[[ … ]]``, ``$(( … ))``) yield ``UNKNOWN`` and the caller falls
back to the value-domain rule.
"""

from __future__ import annotations

import importlib.util
from dataclasses import dataclass
from enum import Enum
from functools import cache
from typing import TYPE_CHECKING, Any

from galaxy_tool_source.command_text import unquoted_cheetah_vars
from galaxy_tool_source.command_vars import provably_quotable

if TYPE_CHECKING:
    from galaxy_tool_source.command_text import UnquotedVar

# Redirection operators that *duplicate* one file descriptor onto another (``2>&1``,
# ``<&3``). Single-quoting an expansion in this position flips a numeric value from an
# fd-dup to a file redirect, so it is never auto-quoted. ``&>`` (redirect both streams
# to a *file*) is deliberately excluded — its target is an ordinary filename word.
_DUP_OPS = frozenset({">&", "<&"})

# A bash-valid parameter name spliced in for the occurrence under test, so a dotted
# Cheetah reference (``${x.y}`` — invalid bash) does not break the parse.
_TARGET = "GTXSHELLORACLETARGET"


def shell_oracle_available() -> bool:
    """Whether the optional ``shell-oracle`` extra (bashlex) is importable."""
    return _bashlex() is not None


class QuotingContext(Enum):
    """The shell context an expansion occupies, w.r.t. single-quoting safety."""

    SPLIT = "split"  # bare command word / redirect-file target -> bash word-splits it
    NO_SPLIT = "no_split"  # assignment RHS: no-split for a shell *expansion* — but NOT
    # for a Cheetah-rendered literal (those split), so the policy does NOT widen on it
    # (see quote_is_behavior_preserving).
    DUP_TARGET = "dup_target"  # >&/<& fd-dup target -> quoting flips dup<->file
    UNKNOWN = "unknown"  # not located / unparseable -> caller falls back


@dataclass(frozen=True)
class Redirection:
    """One redirection in a realized command line.

    Attributes:
        src_fd: The source file descriptor (an explicit ``2>`` prefix, else the
            operator default: ``0`` for input ops, ``1`` for output ops).
        op: The operator as written (``>``, ``>>``, ``<``, ``>&``, ``2>&1`` → ``>&`` …).
        target: The destination — a filename for a file redirect, ``"&N"`` for an
            fd-dup, ``"-"`` for an fd close.
        is_dup: True iff a descriptor-to-descriptor duplication (``2>&1``).
    """

    src_fd: int
    op: str
    target: str
    is_dup: bool


@dataclass(frozen=True)
class BoundarySignature:
    """The behaviour-defining signature of a realized command line.

    ``words`` is the top-level argv word partition (command-substitution interiors are
    not expanded into it); ``redirections`` is the full fd topology. Two command lines
    with equal signatures present the shell the same arguments and the same
    descriptor wiring.
    """

    words: tuple[str, ...]
    redirections: tuple[Redirection, ...]


@cache
def _bashlex() -> Any | None:
    """The bashlex module if the ``shell-oracle`` extra is installed, else ``None``."""
    if importlib.util.find_spec("bashlex") is None:
        return None
    import bashlex
    import bashlex.ast  # noqa: F401 - register the ``ast`` submodule on the package

    return bashlex


def _parse(line: str, /) -> list[Any] | None:
    """bashlex AST for *line*, or ``None`` when unavailable / unparseable.

    bashlex raises a variety of error types (its own ``ParsingError``,
    ``NotImplementedError`` for ``[[ ]]`` / ``$(( ))``, and assorted ``IndexError`` /
    ``AssertionError`` on malformed input). It is a third-party parser with no LBYL
    form, so the whole parse is guarded and any failure is reported as "cannot
    determine" — the caller then falls back to the value-domain rule.
    """
    bashlex = _bashlex()
    if bashlex is None:
        return None
    try:
        return list(bashlex.parse(line, strictmode=False))
    except Exception:  # noqa: BLE001 - bashlex raises many error types; treat all as unparseable
        return None


def _default_fd(op: str, /) -> int:
    """The implicit source fd for a redirection operator with no explicit prefix."""
    return 0 if op.startswith("<") else 1


def _as_nodes(value: Any, /) -> list[Any]:
    """Normalise a bashlex child attribute to a list — a ``compound``'s ``.list`` is a
    list of nodes for some constructs and a single node for others."""
    return value if isinstance(value, list) else [value]


def boundary_signature(line: str, /) -> BoundarySignature | None:
    """The argv partition + full fd topology of a realized shell *line*.

    ``None`` when the ``shell-oracle`` extra is absent or *line* does not parse as
    bash. Top-level argv words only — command-substitution interiors are treated as
    opaque (part of their enclosing word), matching how the shell hands the outer
    command a single argument.
    """
    trees = _parse(line)
    if trees is None:
        return None
    words: list[str] = []
    redirections: list[Redirection] = []
    for tree in trees:
        _collect(tree, words=words, redirections=redirections)
    return BoundarySignature(words=tuple(words), redirections=tuple(redirections))


def _collect(
    node: Any, /, *, words: list[str], redirections: list[Redirection]
) -> None:
    """Walk *node*, appending top-level argv words and every redirection."""
    kind = node.kind
    if kind == "word":
        words.append(node.word)
        return  # do not descend into command-substitution interiors
    if kind == "redirect":
        redirections.append(_redirection(node))
        return
    if kind in ("command", "pipeline", "list", "if", "for", "while", "until", "case"):
        for part in getattr(node, "parts", ()):
            _collect(part, words=words, redirections=redirections)
        return
    if kind == "compound":
        for item in _as_nodes(node.list):
            _collect(item, words=words, redirections=redirections)
        for redirect in getattr(node, "redirects", ()):
            _collect(redirect, words=words, redirections=redirections)
        return
    # operator / pipe / reservedword / assignment / parameter etc. contribute no
    # top-level argv word and no redirection of their own.


def _redirection(node: Any, /) -> Redirection:
    """Build a ``Redirection`` from a bashlex ``redirect`` node."""
    op = node.type
    output = node.output
    src_fd = node.input if isinstance(node.input, int) else _default_fd(op)
    if isinstance(output, int):
        return Redirection(src_fd=src_fd, op=op, target=f"&{output}", is_dup=True)
    if isinstance(output, str):  # ``-`` fd close
        return Redirection(src_fd=src_fd, op=op, target=output, is_dup=False)
    return Redirection(src_fd=src_fd, op=op, target=output.word, is_dup=False)


def quoting_context(line: str, sentinel: str, /) -> QuotingContext:
    """Classify where the ``$sentinel`` expansion sits in a realized shell *line*.

    Returns ``UNKNOWN`` when the ``shell-oracle`` extra is absent, *line* does not
    parse, or the sentinel parameter is not found (e.g. it landed on a ``#`` comment
    line). Otherwise the context governs single-quoting safety: ``NO_SPLIT`` is safe
    for any value, ``DUP_TARGET`` is never auto-quoted, ``SPLIT`` defers to the
    value-domain rule.
    """
    trees = _parse(line)
    if trees is None:
        return QuotingContext.UNKNOWN
    for tree in trees:
        found = _find_context(tree, sentinel, QuotingContext.SPLIT)
        if found is not None:
            return found
    return QuotingContext.UNKNOWN


def _find_context(
    node: Any, sentinel: str, context: QuotingContext, /
) -> QuotingContext | None:
    """Depth-first search for the ``$sentinel`` parameter, returning its context.

    *context* is the splitting context inherited from the enclosing syntax: a command
    word is ``SPLIT``; an assignment RHS is ``NO_SPLIT``; a fd-dup redirect target is
    ``DUP_TARGET``. A command substitution resets to ``SPLIT`` (a fresh shell word
    context). ``None`` means "not in this subtree".
    """
    kind = node.kind
    if kind == "parameter":
        return context if node.value == sentinel else None
    if kind == "assignment":
        return _search_parts(node, sentinel, QuotingContext.NO_SPLIT)
    if kind == "word":
        return _search_parts(node, sentinel, context)
    if kind in ("commandsubstitution", "processsubstitution"):
        return _find_context(node.command, sentinel, QuotingContext.SPLIT)
    if kind == "redirect":
        target_context = (
            QuotingContext.DUP_TARGET
            if node.type in _DUP_OPS
            else QuotingContext.SPLIT
        )
        if isinstance(node.output, _node_type()):
            return _find_context(node.output, sentinel, target_context)
        return None
    if kind == "compound":
        found = _search_iterable(_as_nodes(node.list), sentinel, QuotingContext.SPLIT)
        if found is not None:
            return found
        return _search_iterable(getattr(node, "redirects", ()), sentinel, context)
    if kind in ("command", "pipeline", "list", "if", "for", "while", "until", "case"):
        return _search_iterable(getattr(node, "parts", ()), sentinel, context)
    return None


def _search_parts(
    node: Any, sentinel: str, context: QuotingContext, /
) -> QuotingContext | None:
    """Search a word/assignment node's expansion ``parts`` for the sentinel."""
    return _search_iterable(getattr(node, "parts", ()), sentinel, context)


def _search_iterable(
    children: Any, sentinel: str, context: QuotingContext, /
) -> QuotingContext | None:
    for child in children:
        found = _find_context(child, sentinel, context)
        if found is not None:
            return found
    return None


@cache
def _node_type() -> Any:
    """The bashlex ``node`` class (for ``isinstance`` of redirect targets)."""
    bashlex = _bashlex()
    assert bashlex is not None  # only called from a parsed-tree walk
    return bashlex.ast.node


def quote_is_behavior_preserving(
    body: str,
    /,
    *,
    occurrence: UnquotedVar,
    kinds: dict[str, str],
    structural: set[str],
) -> bool:
    """Whether single-quoting *occurrence* in a ``<command>`` *body* keeps behaviour.

    Composes the bashlex structural classifier with the value-domain
    ``provably_quotable`` rule — the GTR020.1 fixer and the GTR020.2 advisory check both
    call this so the fix/advisory partition stays exact. The only shell-context
    adjustment on top of the value-domain rule is a **narrowing**:

    - ``DUP_TARGET`` (``>&``/``<&``): never auto-quoted — quoting a numeric fd flips a
      descriptor dup into a file redirect. Conservative: vetoes the rare file-valued
      dup targets too;
    - ``SPLIT`` / ``NO_SPLIT`` / ``UNKNOWN``: defer to ``provably_quotable``.

    **No widening on ``NO_SPLIT``.** Although ``VAR=$x`` is a no-word-splitting context
    for a shell *expansion*, Galaxy renders a Cheetah ``$x`` to its value as **literal
    text** before the shell runs, and a literal ``VAR=foo bar`` *does* split (assignment
    + command ``bar``) — so single-quoting a space-bearing value there changes
    behaviour. The classifier still reports ``NO_SPLIT`` (it is correct about the
    *shell* structure), but the quoting policy must not act on it. (Sound widening of
    Cheetah-rendered command values needs adversarial-shape render verification —
    deferred research.)

    Without the ``shell-oracle`` extra it is exactly ``provably_quotable`` — the
    license-clean default.
    """
    if not shell_oracle_available():
        return provably_quotable(occurrence.name, kinds, structural)
    context = quoting_context(_pseudo_render(body, occurrence=occurrence), _TARGET)
    if context is QuotingContext.DUP_TARGET:
        return False
    return provably_quotable(occurrence.name, kinds, structural)


def _pseudo_render(body: str, /, *, occurrence: UnquotedVar) -> str:
    """Rewrite *body* to parseable shell, each unquoted Cheetah var → ``$expansion``.

    The *occurrence* under test becomes ``$GTXSHELLORACLETARGET`` (locatable) and every
    other unquoted Cheetah var becomes a fresh simple expansion ``$GTXSHELLORACLE_n`` —
    so dotted forms (``${x.y}``, invalid bash) never break the parse — while keeping the
    references as **expansions** rather than substituting a value, preserving bash's
    word-splitting semantics. Replacements run right-to-left to keep offsets valid.
    """
    occurrences = unquoted_cheetah_vars(body)
    rendered = body
    for index, occ in sorted(
        enumerate(occurrences), key=lambda pair: pair[1].start, reverse=True
    ):
        name = (
            _TARGET
            if occ.start == occurrence.start and occ.end == occurrence.end
            else f"GTXSHELLORACLE_{index}"
        )
        rendered = f"{rendered[: occ.start]}${name}{rendered[occ.end :]}"
    return rendered
