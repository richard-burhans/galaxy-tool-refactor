"""Codemod: inline a deprecated ``<command interpreter=…>`` (GTR016).

Before profile 16.04 Galaxy ran ``<command interpreter="python">script.py …</command>``
as ``python '<tool_dir>/script.py' …`` at runtime — it took the first whitespace
token of the *substituted* command line, resolved it under the tool directory, and
prepended the interpreter attribute **verbatim** (``interpreter + " " +
command_line``, ``release_16.04`` ``evaluation.py:478-484`` … ``release_20.01``;
since ``release_20.09`` spliced at the token as ``f"{interpreter}
{shlex.quote(abs_executable)}"`` — still verbatim, equivalent for a literal first
token, and alive in ``dev:781-787`` for ``legacy_defaults`` tools). From 16.04
the ``interpreter`` attribute is ignored, so an upgraded tool breaks unless the command
is rewritten (Galaxy's ``16_04_fix_interpreter`` *must-fix* upgrade code).

This is a **runtime-gated fix** (like GTR014/GTR015): the construct is XSD-valid at
every profile, so the ``upgrade`` path applies it once a tool *crosses* the 16.04
boundary (``runtime_fixes.py``; crossing-gate, codemod ``docs/decisions.md`` §24). It
acts on "bucket A" — **any non-empty** ``interpreter`` whose body begins with a
literal script filename (``codemods/_interpreter.py``; the verbatim-concatenation
proof above is what admits flag-bearing and non-script values). Bucket B (leading
Cheetah / ``$var`` first token) cannot be rewritten statically and stays in the §23
warning, as does an empty ``interpreter=""`` (legacy-ignored; no composition to
reproduce).

**Positional splice, not ``str.replace`` over the raw body.** The rewrite is anchored
at the offset ``first_command_token_span`` located (the first non-blank, non-``##``
content line), so a script name appearing inside a leading ``##`` comment is never
mistargeted — only the real, first invocation is rewritten. The new body is emitted as
CDATA (GTR018.2) so shell operators stay literal. The path is emitted as the literal
``'$__tool_directory__/<token>'``; see the research note (16_04_fix_interpreter) for
the (admin-controlled, out-of-scope) single-quote boundary vs Galaxy's ``shlex.quote``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from galaxy_tool_refactor_rules.meta import RuleMeta

from galaxy_tool_codemod.change import Change
from galaxy_tool_codemod.codemods._interpreter import interpreter_rewrite
from galaxy_tool_codemod.codemods._runtime_gated import RuntimeGatedFix
from galaxy_tool_codemod.cursor import Cursor

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

    from galaxy_tool_codemod.module import Module


def _inline_interpreter(
    cursor: Cursor, *, body: str, interpreter: str, token: str, offset: int
) -> Callable[[], None]:
    """Return a thunk that path-qualifies *token* and drops the ``interpreter`` attr.

    The replace is restricted to ``body[offset:]`` (at/after the first content line),
    so anything before the anchor — a leading ``##`` comment that happens to mention
    the script name — is left byte-identical.
    """
    replacement = f"{interpreter} '$__tool_directory__/{token}'"
    new_body = body[:offset] + body[offset:].replace(token, replacement, 1)

    def mutate() -> None:
        cursor.set_text(new_body, cdata=True)
        cursor.delete_attribute("interpreter")

    return mutate


class FixInterpreter(RuntimeGatedFix):
    """Inline a deprecated ``<command interpreter=…>`` so a 16.04+ tool still runs."""

    meta: ClassVar[RuleMeta] = RuleMeta(
        code="GTR016",
        summary=(
            "Inline a deprecated <command interpreter=I>script ...</command> as"
            " <command>I '$__tool_directory__/script' ...</command> (any non-empty"
            " interpreter, literal-script first token)."
        ),
        since="0.0.1",
        cite="https://github.com/galaxyproject/galaxy/pull/1688",
        planemo_linters=frozenset({"CommandInterpreterDeprecated"}),
    )

    introduced_profile: ClassVar[str] = "16.04"
    upgrade_code: ClassVar[str] = "16_04_fix_interpreter"

    def detect(self, module: Module, /) -> Iterator[Change]:
        document = module.document
        # No file-exists guard here (unlike the measure's bucket-A refinement): the
        # rewrite is faithful whether or not the script is co-located — Galaxy ran
        # ``interpreter '<tool_dir>/<first-token>' …`` regardless, failing identically
        # if absent. Gating on the script's presence would make the codemod's result
        # depend on whether the tool was loaded from a path (source_path) or bytes,
        # which the corpus sweep correctly flags as non-idempotent.
        plan = interpreter_rewrite(document.root)
        if plan is None:
            return  # bucket B / empty interpreter — left for the §23 warning
        interpreter, token, offset = plan
        command = document.root.find("command")
        if command is None:  # defensive: interpreter_rewrite already found it
            return
        cursor = Cursor(command)
        if cursor.child_node_count() != 0:
            # Mixed-content <command> (a comment / <expand> child): the rewrite builds
            # the new body from itertext() but set_text overwrites only .text, leaving
            # the children and their tails — so the absorbed tail would run twice. We
            # cannot clear the children either (an <expand> carries macro command
            # content). Skip it, matching the other command-rewriting codemods; the §23
            # warning still covers it. (Behaviour-preservation GTR016;
            # ../../docs/behavior_preservation.md.)
            return
        yield Change(
            code=self.meta.code,
            sourceline=cursor.sourceline,
            xpath=cursor.xpath,
            message=(
                f'interpreter="{interpreter}" inlined as'
                f" {interpreter} '$__tool_directory__/{token}'"
            ),
            mutate=_inline_interpreter(
                cursor,
                body="".join(command.itertext()),
                interpreter=interpreter,
                token=token,
                offset=offset,
            ),
        )
