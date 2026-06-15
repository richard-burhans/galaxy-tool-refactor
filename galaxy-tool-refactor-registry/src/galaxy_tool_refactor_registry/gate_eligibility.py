"""Per-rule eligibility for the repository-scale auto-fix system's two halves.

The auto-fix system (plan: ``~/.claude/plans/tools-iuc-autofix-system.md``) has a
one-shot **bulk normalizer** that clears a repository's backlog and a
**forward-enforcement gate** (a pre-merge check, conference §7) that keeps it
clean. Both read their rule set from the same classification so they can never
disagree. Every rule lands in exactly one bucket:

* ``GATE_ELIGIBLE`` — behaviour-preserving AND the canonical target form is
  uncontroversial (IUC-cited, or dictated by the XSD). Runs in BOTH halves.
* ``BULK_ELIGIBLE_ONLY`` — behaviour-preserving but an uncited house convention.
  Offer in the bulk pass; do NOT hard-gate every incoming PR until IUC adopts it
  as a standard.
* ``BLOCKED_PENDING_IUC`` — behaviour-preserving but the canonical form is
  contested upstream, so it cannot run in either half until IUC decides
  (attribute reordering — conference §3).
* ``ADVISORY_ONLY`` — not auto-fixable (``detect_only``). Never auto-applied;
  ``check`` reports it and points to docs.

``detect_only`` rules map mechanically to ``ADVISORY_ONLY``. The 14 fixable rules
each carry an explicit bucket + rationale below; a fixable rule missing from
``_FIXABLE_BUCKETS`` raises, so a newly added fixable rule cannot silently become
gate-eligible (it must be classified deliberately). See registry
``docs/decisions.md`` D26 and ``docs/gate_eligibility.md`` (the generated table).
"""

from __future__ import annotations

import re
from typing import Final

from galaxy_tool_refactor_registry.handle import RuleHandle
from galaxy_tool_refactor_registry.registry import registry

GATE_ELIGIBLE: Final = "gate-eligible"
BULK_ELIGIBLE_ONLY: Final = "bulk-only"
BLOCKED_PENDING_IUC: Final = "blocked-pending-iuc"
ADVISORY_ONLY: Final = "advisory-only"

# Display order for the buckets in the generated table.
BUCKET_ORDER: Final = (
    GATE_ELIGIBLE,
    BULK_ELIGIBLE_ONLY,
    BLOCKED_PENDING_IUC,
    ADVISORY_ONLY,
)

BUCKET_TITLES: Final = {
    GATE_ELIGIBLE: "Gate-eligible (bulk pass + forward gate)",
    BULK_ELIGIBLE_ONLY: "Bulk-only (offer in the bulk pass, not the gate)",
    BLOCKED_PENDING_IUC: "Blocked pending an IUC decision",
    ADVISORY_ONLY: "Advisory-only (report + docs, never auto-applied)",
}

# Explicit per-code bucket + rationale for every FIXABLE rule. detect-only rules
# are classified mechanically (ADVISORY_ONLY) and are not listed here.
_FIXABLE_BUCKETS: Final[dict[str, tuple[str, str]]] = {
    "GTR001": (
        GATE_ELIGIBLE,
        "Canonical indentation; IUC-cited, uncontroversial whitespace.",
    ),
    "GTR002": (
        BLOCKED_PENDING_IUC,
        "Param attribute order is contested upstream (#8090); needs an IUC "
        "canonical-order decision (conference §3).",
    ),
    "GTR004": (
        BULK_ELIGIBLE_ONLY,
        "Empty-element shorthand is an uncited house convention (conference §6); "
        "offer in the bulk pass, do not hard-gate until IUC adopts it.",
    ),
    "GTR005": (
        BLOCKED_PENDING_IUC,
        "Root <tool> attribute order — the same attribute-reordering class as "
        "GTR002; confirm in the §3 conversation.",
    ),
    "GTR006": (
        GATE_ELIGIBLE,
        "Typo repair that restores XSD validity; the target form is dictated by "
        "the schema, not editorial taste (uncited but uncontroversial).",
    ),
    "GTR013": (
        GATE_ELIGIBLE,
        "<tool> child element order is IUC-documented and xs:all-validity-safe; "
        "element (not attribute) reordering. Precondition: the §53 <expand>-pinning "
        "fix (verify before any mass run).",
    ),
    "GTR017": (
        GATE_ELIGIBLE,
        "Boolean-value normalization that restores XSD validity; schema-dictated "
        "form (uncited but uncontroversial).",
    ),
    "GTR018.1": (
        GATE_ELIGIBLE,
        "Wrap a pure-text <command> body in CDATA; behaviour-preserving, IUC #34.",
    ),
    "GTR019.1": (
        GATE_ELIGIBLE,
        "Wrap a pure-text <help> body in CDATA; behaviour-preserving, IUC #42.",
    ),
    "GTR020.1": (
        GATE_ELIGIBLE,
        "Single-quote provably-single-valued command variables; behaviour-"
        "preserving provable subset, IUC-cited.",
    ),
    "GTR035.1": (
        GATE_ELIGIBLE,
        "Trim accidental whitespace in a <requirement> version; behaviour-"
        "preserving, IUC-cited.",
    ),
    "GTR036": (
        GATE_ELIGIBLE,
        "Modernize a deprecated <output> to <data>/<collection> via Galaxy's own "
        "attribute remap; behaviour-preserving, IUC-cited.",
    ),
    "GTR037": (
        GATE_ELIGIBLE,
        "Drop a redundant <param> name equal to the argument-derived name; "
        "behaviour-preserving, IUC-cited.",
    ),
    "GTR089.1": (
        GATE_ELIGIBLE,
        "Repair deterministically-fixable invalid <help> reStructuredText behind a "
        "render-equivalence gate; IUC-cited.",
    ),
}

BEGIN_MARKER: Final = "<!-- BEGIN generated gate-eligibility table -->"
END_MARKER: Final = "<!-- END generated gate-eligibility table -->"


def classify(handle: RuleHandle, /) -> str:
    """Return the eligibility bucket for *handle*.

    ``detect_only`` rules are ADVISORY_ONLY. Every fixable rule must have an
    explicit entry in ``_FIXABLE_BUCKETS`` — a missing one raises ``KeyError`` so
    a new fixable rule cannot silently default into a half of the auto-fix system.
    """
    if handle.meta.detect_only:
        return ADVISORY_ONLY
    code = handle.meta.code
    bucket_rationale = _FIXABLE_BUCKETS.get(code)
    if bucket_rationale is None:
        raise KeyError(
            f"fixable rule {code} has no gate-eligibility classification; add it "
            f"to gate_eligibility._FIXABLE_BUCKETS (it must be classified, not "
            f"silently defaulted)"
        )
    return bucket_rationale[0]


def _rationale(handle: RuleHandle, /) -> str:
    """Return the one-line rationale for *handle*'s bucket (internal to the renderer).

    Fixable rules carry a hand-written rationale; advisory rules share the generic
    "detect-only, never auto-applied" rationale.
    """
    if handle.meta.detect_only:
        return "Detect-only; reported by `check`, never auto-applied."
    return _FIXABLE_BUCKETS[handle.meta.code][1]


def _code_sort_key(code: str, /) -> list[object]:
    """Natural sort key so e.g. ``GTR020.1`` sorts after ``GTR020`` and ``GTR019``."""
    return [int(part) if part.isdigit() else part for part in re.split(r"(\d+)", code)]


def eligibility_groups() -> dict[str, list[str]]:
    """Map each bucket to its sorted rule codes (every registered rule classified)."""
    groups: dict[str, list[str]] = {bucket: [] for bucket in BUCKET_ORDER}
    for code, handle in registry().items():
        groups[classify(handle)].append(code)
    return {
        bucket: sorted(codes, key=_code_sort_key) for bucket, codes in groups.items()
    }


def gate_codes() -> frozenset[str]:
    """The forward gate's rule set: the GATE_ELIGIBLE codes.

    The single source of truth every consumer reads — the forward gate (block and
    suggest modes), the bulk normalizer's gate view, the coverage tracker, and the
    published Action — so they cannot drift on what is auto-enforced. A tool is
    *canonical* (under the gate) when none of these codes fires on it; see
    :func:`galaxy_tool_refactor_registry.facade.is_canonical`.
    """
    return frozenset(eligibility_groups()[GATE_ELIGIBLE])


def bulk_codes() -> frozenset[str]:
    """The bulk normalizer's rule set: gate-eligible PLUS bulk-only.

    A superset of :func:`gate_codes` (never the blocked-pending-IUC or advisory
    buckets), so a tool the bulk pass has cleaned always passes the gate.
    """
    groups = eligibility_groups()
    return frozenset(groups[GATE_ELIGIBLE]) | frozenset(groups[BULK_ELIGIBLE_ONLY])


def render_eligibility_table() -> str:
    """Render the generated body of ``docs/gate_eligibility.md`` (between markers).

    A counts summary, a per-rule table for the fixable rules (where the bucketing
    decisions live), and the advisory-only roster as a compact code list.
    """
    reg = registry()
    groups = eligibility_groups()
    counts = " · ".join(
        f"{len(groups[bucket])} {bucket}" for bucket in BUCKET_ORDER
    )
    lines = [
        f"**{len(reg)} rules**: {counts}.",
        "",
        "## Fixable rules (the auto-fix surface)",
        "",
        "| Bucket | Code | Summary | Rationale |",
        "|---|---|---|---|",
    ]
    for bucket in BUCKET_ORDER:
        for code in groups[bucket]:
            handle = reg[code]
            if handle.meta.detect_only:
                continue
            lines.append(
                f"| {bucket} | {code} | {handle.meta.summary} | {_rationale(handle)} |"
            )
    advisory = groups[ADVISORY_ONLY]
    lines += [
        "",
        f"## Advisory-only rules ({len(advisory)})",
        "",
        "Detect-only checks — reported by `check` and pointed at docs, never "
        "auto-applied in either half:",
        "",
        ", ".join(f"`{code}`" for code in advisory),
    ]
    return "\n".join(lines)
