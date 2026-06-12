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
(``test_param_qualify.plan_test_param_qualifications``), so the unqualified name
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

from galaxy_tool_codemod.change import Change
from galaxy_tool_codemod.codemods._runtime_gated import RuntimeGatedFix
from galaxy_tool_codemod.test_param_qualify import plan_test_param_qualifications

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
