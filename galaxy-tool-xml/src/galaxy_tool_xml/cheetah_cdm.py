"""A faithful Cheetah lexer — the editable **span model** (CDM) over a Cheetah section.

The precision half of the deferred Cheetah **M5** layer: given the raw text of a
Cheetah-templated section (a ``<command>`` body, an inline ``<configfile>`` script),
harvest the *exact* source spans of every ``$placeholder`` / ``#directive`` / comment
by subclassing CT3's own ``Cheetah.Parser.Parser`` and recording each ``eat*`` hook's
extent. Because the real parser drives the harvest, ``##`` comments, ``#raw`` blocks,
escaped ``\\$``, and embedded Python strings are classified exactly as Cheetah would —
unlike the conservative regex in ``cheetah_refs`` / ``command_text``, which a *mutator*
cannot trust (it would rewrite bytes inside a ``#raw`` block or a comment). This is the
substrate the first Cheetah mutator (rename) edits; see
``../../docs/upgrade_research/cheetah_section_editing.md``.

CT3 (the maintained Cheetah3 fork) is reached via the optional ``cheetah-cdm`` extra
(``galaxy-util[template]``), mirroring the ``shell-oracle`` (bashlex) posture: this
MIT-licensed tier keeps CT3 a soft dependency, imports it lazily, and every entry point
degrades gracefully when it is absent — ``cheetah_cdm_available()`` is ``False`` and
``cheetah_spans`` returns ``None`` so the caller falls back to the regex scan.

The spans are **disjoint and in source order**; the literal text between them is the
gap, so a section re-serialises by interleaving the gaps with each ``span.text`` (the
round-trip property a byte-faithful mutator relies on). A directive head swallows the
``$vars`` in its own clause — ``#if $paired`` / ``#set $tmp = $base`` are single
directive spans, not a directive plus nested placeholders — so a reference *inside* a
directive is read from that span's text by the scope-aware consumer, not from the
placeholder list.
"""

from __future__ import annotations

import importlib.util
import warnings
from dataclasses import dataclass
from enum import Enum
from functools import cache


class SpanKind(Enum):
    """What a :class:`CheetahSpan` covers."""

    PLACEHOLDER = "placeholder"  # a ``$var`` / ``${obj.attr}`` reference
    DIRECTIVE = "directive"  # a ``#if`` / ``#set`` / ``#for`` / ``#raw`` / ``#end`` …
    COMMENT = "comment"  # a ``##`` line or ``#* … *#`` block


@dataclass(frozen=True)
class CheetahSpan:
    """One non-literal region of a Cheetah section, with faithful source offsets.

    Attributes:
        kind: Whether the region is a placeholder, a directive, or a comment.
        start: 0-based character offset of the region's first character.
        end: Character offset one past its last character (``text[start:end] == text``).
        text: The exact source slice — re-serialises byte-for-byte.
        directive: The directive keyword (``"if"``, ``"set"``, ``"for"``, ``"end"``, …)
            when ``kind is SpanKind.DIRECTIVE``; ``None`` for placeholders and comments.
    """

    kind: SpanKind
    start: int
    end: int
    text: str
    directive: str | None = None


@cache
def cheetah_cdm_available() -> bool:
    """Whether the optional ``cheetah-cdm`` extra (CT3) is importable."""
    return importlib.util.find_spec("Cheetah") is not None


@cache
def _span_compiler_class() -> type:
    """The CT3 module compiler whose parser harvests spans (built lazily, once).

    Defined inside this cached factory so importing this module never imports CT3 (an
    optional extra) and the ``Parser`` subclass is constructed exactly once. The
    ``eat*`` overrides record each construct's ``[start, pos())`` extent after the real
    parser has consumed it, inheriting CT3's exact handling of comments / ``#raw`` /
    escapes — the ``DirectiveAnalyzer`` pattern CT3 itself ships.
    """
    from Cheetah import Compiler, Parser

    class _SpanParser(Parser.Parser):  # type: ignore[misc]
        def __init__(self, *args: object, **kwargs: object) -> None:
            self.cdm_spans: list[CheetahSpan] = []
            super().__init__(*args, **kwargs)

        def _record(
            self, kind: SpanKind, start: int, /, *, directive: str | None = None
        ) -> None:
            end = self.pos()
            self.cdm_spans.append(
                CheetahSpan(
                    kind=kind,
                    start=start,
                    end=end,
                    text=self[start:end],
                    directive=directive,
                )
            )

        def eatPlaceholder(self) -> object:
            start = self.pos()
            result = super().eatPlaceholder()
            self._record(SpanKind.PLACEHOLDER, start)
            return result

        def eatDirective(self) -> object:
            directive = self.matchDirective()
            start = self.pos()
            result = super().eatDirective()
            self._record(SpanKind.DIRECTIVE, start, directive=directive)
            return result

        def eatComment(self) -> object:
            start = self.pos()
            result = super().eatComment()
            self._record(SpanKind.COMMENT, start)
            return result

        def eatMultiLineComment(self) -> object:
            start = self.pos()
            result = super().eatMultiLineComment()
            self._record(SpanKind.COMMENT, start)
            return result

    class _SpanCompiler(Compiler.ModuleCompiler):  # type: ignore[misc]
        parserClass = _SpanParser

    return _SpanCompiler


def cheetah_spans(text: str, /) -> list[CheetahSpan] | None:
    """Every non-literal Cheetah span in *text*, in source order — or ``None`` to bail.

    Returns the ordered, **disjoint** placeholder / directive / comment spans (the gaps
    between them are literal text, so the section re-serialises by interleaving gaps and
    ``span.text``). Returns ``None`` when the faithful lexer is unavailable (the
    ``cheetah-cdm`` extra is absent) or CT3 cannot compile *text* (~0.4% of the corpus:
    py2-isms, ``#import`` of an absent module, an unbalanced ``#end``) — the caller then
    falls back to the regex scan (``command_text`` / ``cheetah_refs``).
    """
    if not cheetah_cdm_available():
        return None
    from Cheetah import Template

    compiler_class = _span_compiler_class()
    try:
        # CT3 compiles the template to generated Python whose regex string literals can
        # raise SyntaxWarning ("invalid escape sequence") — noise from a dependency's
        # codegen, not the caller's concern, so it is silenced here.
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", SyntaxWarning)
            compiled = Template.Template.compile(text, compilerClass=compiler_class)
    except Exception:  # noqa: BLE001 - any CT3 compile failure ⇒ bail to the regex fallback
        return None
    parser = compiled._CHEETAH_compilerInstance._parser
    return list(parser.cdm_spans)
