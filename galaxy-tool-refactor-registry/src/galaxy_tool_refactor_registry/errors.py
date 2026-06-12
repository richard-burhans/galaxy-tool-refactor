"""Typed, ``click``-free errors the facade raises for bad selections.

These are plain ``ValueError`` subclasses (LBYL: the facade checks membership and
raises before doing any work). The CLI catches them at its error boundary and
re-raises as ``click.BadParameter`` so the user sees a clean message, not a
traceback; the MCP server maps them to a structured error response. Keeping
them ``click``-free keeps the library usable outside the CLI.
"""

from __future__ import annotations


class UnknownRuleCode(ValueError):
    """A rule code passed to ``--select`` / ``--ignore`` is not a selectable rule.

    *hint* explains a code that exists but is deliberately not selectable (a
    non-selectable codemod, e.g. the opt-in-command-only GTR092) — appended so
    the user learns where the rule actually lives instead of "unknown".
    """

    def __init__(self, code: str, /, *, hint: str | None = None) -> None:
        self.code = code
        message = f"unknown rule code: {code!r}"
        if hint is not None:
            message = f"{message} ({hint})"
        super().__init__(message)


class UnknownRuleset(ValueError):
    """A ruleset name passed to ``--ruleset`` is not a known ruleset."""

    def __init__(self, name: str, /) -> None:
        self.name = name
        super().__init__(f"unknown ruleset: {name!r}")


class UnknownProfile(ValueError):
    """A profile passed to ``--target-profile`` is not a vendored Galaxy profile.

    *oldest* and *latest* bound the vendored range, so the message shows what
    is available instead of only rejecting the value.
    """

    def __init__(self, profile: str, /, *, oldest: str, latest: str) -> None:
        self.profile = profile
        super().__init__(
            f"unknown profile: {profile!r}; vendored Galaxy profiles run from"
            f" {oldest} to {latest}"
        )
