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


class UpgradeFlagError(ValueError):
    """A gate-adjusting flag was requested without a walk mode to apply it to.

    The default ``upgrade`` is the minimal bump: ``profile=`` moves only as far
    as validity strictly requires, so there is no gated walk whose gate the
    flag (``allow_behavior_change`` lifts it, ``block_consider`` tightens it)
    could adjust. Adjusting the gate is meaningful only for the opt-in
    modernize walk (``modernize``) or an explicit ``target_profile``; requiring
    one of them keeps the flag from silently implying a walk the user did not
    ask for.
    """

    def __init__(self, flag: str = "allow_behavior_change", /) -> None:
        self.flag = flag
        super().__init__(
            f"{flag} adjusts the behaviour gate on a modernize walk, but no"
            " walk was requested; combine it with modernize or a"
            " target_profile. The default upgrade is the minimal bump, which"
            " the gate does not apply to."
        )


class UpgradeFlagConflict(ValueError):
    """Mutually exclusive behaviour-gate flags were combined.

    ``allow_behavior_change`` lifts the walk's behaviour gate entirely;
    ``block_consider`` tightens it to stop at consider-level changes too. The
    combination has no coherent meaning, so it is rejected rather than letting
    one flag silently win.
    """

    def __init__(self) -> None:
        super().__init__(
            "block_consider tightens the behaviour gate and"
            " allow_behavior_change lifts it; combine either with a walk mode,"
            " not with each other."
        )


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
