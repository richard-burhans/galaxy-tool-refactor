"""Typed, ``click``-free errors the facade raises for bad selections.

These are plain ``ValueError`` subclasses (LBYL: the facade checks membership and
raises before doing any work). The CLI catches them at its error boundary and
re-raises as ``click.BadParameter`` so the user sees a clean message, not a
traceback; the MCP server maps them to a structured error response. Keeping
them ``click``-free keeps the library usable outside the CLI.
"""

from __future__ import annotations


class UnknownRuleCode(ValueError):
    """A rule code passed to ``--select`` / ``--ignore`` is not a known rule."""

    def __init__(self, code: str, /) -> None:
        self.code = code
        super().__init__(f"unknown rule code: {code!r}")


class UnknownRuleset(ValueError):
    """A ruleset name passed to ``--ruleset`` is not a known ruleset."""

    def __init__(self, name: str, /) -> None:
        self.name = name
        super().__init__(f"unknown ruleset: {name!r}")
