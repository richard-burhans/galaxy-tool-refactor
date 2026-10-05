"""Codemod: fully-qualify a flat ``<test>`` parameter name (GTR096).

From profile 24.2 Galaxy requires a test parameter that targets a nested input
(inside a ``<conditional>``, ``<section>``, or ``<repeat>``) to be written with
its fully-qualified ``parent|...|child`` path; an unqualified leaf name is a
hard error (``24_2_fix_test_case_validation`` *must-fix*). Qualifying the name
is the migration Galaxy itself prescribes.

This is a **runtime-gated fix**: a flat test name is XSD-valid at every profile,
so it does not change ``newest_valid_profile`` and cannot ride the
``UpgradeToLatest`` loop. The ``upgrade`` path applies it once a tool crosses
profile >= 24.2 (``runtime_fixes.py``). It is **behaviour-preserving**: it edits
only ``<tests>``, never a tool runtime element, and the rewrite is made only
when the flat leaf resolves to exactly one nested input parameter
(``test_param_paths.plan_test_param_qualifications``), so the unqualified name
already referred to that one parameter. A name matching no input (a typo, a
removed parameter, or a Galaxy built-in), a top-level input (already correct),
or more than one input (ambiguous) is left untouched, so the fix can only ever
clear an error, never introduce one. Its effect is verified by execution: the
behavior gate credits ``24_2_fix_test_case_validation`` only when re-detection
(``test_case_check``) proves the tests clean after the rewrite, and the corpus
parity oracle (``scripts.measure test-case-validation-truth``) holds zero
unsound suppressions. See ``docs/decisions.md`` §48 and
``docs/galaxy_reimplementations.md``.
"""

from __future__ import annotations

from functools import partial
from typing import TYPE_CHECKING, ClassVar

from galaxy_tool_refactor_rules.meta import RuleMeta
from galaxy_tool_source.test_param_paths import plan_test_param_qualifications

from galaxy_tool_codemod.change import Change
from galaxy_tool_codemod.codemods._runtime_gated import RuntimeGatedFix

if TYPE_CHECKING:
    from collections.abc import Iterator

    from lxml import etree

    from galaxy_tool_codemod.module import Module


def _set_name(param: etree._Element, name: str, /) -> None:
    param.set("name", name)


class FixTestParamQualification(RuntimeGatedFix):
    """Qualify a flat ``<test>`` param name to its unique nested input path."""

    meta: ClassVar[RuleMeta] = RuleMeta(
        code="GTR096",
        summary=(
            "Fully-qualify a flat <test> parameter name to its unique nested"
            " parent|...|child input path (required at profile >= 24.2)."
        ),
        since="0.0.1",
        cite="https://github.com/galaxyproject/galaxy/pull/18679",
        # Selectable in `strict` as of 0.3.10, so the fix is reachable without an
        # `upgrade`. The gap it closes: the runtime-gated path applies only while a
        # profile walk CROSSES 24.2 (`baseline < introduced_profile <= reached`), so a
        # tool AUTHORED at 24.2 or later -- now the common case -- was never visited,
        # and its unqualified test params stayed unfixed. GTR101 reports the condition
        # (Galaxy raises `Invalid parameter name found` from profile 24.2), so the
        # report existed and only the fix was out of reach.
        #
        # It stays out of "default" deliberately: `canonical_codemods()` derives the
        # format pipeline from that set, and this edit belongs to a correctness sweep,
        # not to formatting -- it can turn a test that was green because it exercised
        # nothing into a red one.
        # An EXPLICIT order. Leaving it at RuleMeta's default 100 collided with
        # GTR019.1 (WrapHelpCdata, also 100) once this rule became selectable, and
        # `apply.py` sorts a frozenset of codes by `meta.order` -- a stable sort, so a
        # tie is broken by frozenset iteration over randomized string hashes. Measured:
        # PYTHONHASHSEED=1 and =3 gave different pipeline orders. Benign in effect (this
        # touches only <tests>, GTR019.1 only <help>) but it was real nondeterminism in
        # the apply phase, in a tier whose contract is a derived, deterministic order.
        order=95,
        rulesets=frozenset({"strict"}),
    )

    introduced_profile: ClassVar[str] = "24.2"
    upgrade_code: ClassVar[str] = "24_2_fix_test_case_validation"

    def detect(self, module: Module, /) -> Iterator[Change]:
        # Cross-element resolution (a test name against the whole input tree),
        # so this overrides the per-tag detect dispatch with a coarse detector.
        for param, qualified in plan_test_param_qualifications(module.document.root):
            current = param.get("name")
            tree = param.getroottree()
            sourceline = param.sourceline or 0
            yield Change(
                code=self.meta.code,
                sourceline=sourceline,
                xpath=tree.getpath(param),
                message=(
                    f"test parameter '{current}' targets a nested input; "
                    f"qualify it as '{qualified}' (required at profile >= 24.2)"
                ),
                mutate=partial(_set_name, param, qualified),
            )
