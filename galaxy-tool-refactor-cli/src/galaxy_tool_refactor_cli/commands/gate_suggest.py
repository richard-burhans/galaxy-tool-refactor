"""The hidden ``gate-suggest`` subcommand: CI plumbing for the forward gate.

The command's logic lives in the sibling module
``galaxy_tool_refactor_cli.gate_suggest`` (imported here as ``gate_suggest_logic``
to avoid the name clash); this module is only the Click binding.
"""

from __future__ import annotations

from pathlib import Path

import click
from galaxy_tool_refactor_registry.gate_eligibility import gate_codes

from galaxy_tool_refactor_cli import gate_suggest as gate_suggest_logic


@click.command(name="gate-suggest", hidden=True)
@click.option(
    "--changed-against", required=True, metavar="REF",
    help="Base ref to diff the PR's changed tools against (e.g. the PR base SHA).",
)
@click.option(
    "--repo", metavar="OWNER/REPO", help="Repository (required unless --dry-run)."
)
@click.option(
    "--pr", type=int, help="Pull request number (required unless --dry-run)."
)
@click.option(
    "--root", type=click.Path(exists=True, file_okay=False, path_type=Path),
    default=Path(), help="Repository root (default: the current directory).",
)
@click.option(
    "--dry-run", is_flag=True,
    help="Print the review payload instead of posting it.",
)
def gate_suggest_command(
    changed_against: str,
    repo: str | None,
    pr: int | None,
    root: Path,
    dry_run: bool,
) -> None:
    """Post a PR's canonical fixes as one-click GitHub review suggestions.

    The forward gate's friendly mode: for each changed tool that is not in canonical
    form, compute the behaviour-preserving fix (the gate-eligible rule subset, the
    same set ``check`` enforces) and post it as GitHub ``suggestion`` review comments
    the author accepts with one click, plus the local ``format`` command and the IUC
    doc link. A fix outside the PR's diff cannot be inlined and is summarized in the
    review body. Non-blocking; intended for a PR CI job (the forward-gate Action's
    ``mode: suggest``). ``--dry-run`` prints the review without posting (no token).
    """
    codes = gate_codes()
    result = gate_suggest_logic.collect_suggestions(root, changed_against, codes=codes)
    if not result.suggestions and not result.skipped:
        click.echo(
            f"all {result.checked} changed tool(s) are canonical; no suggestions"
        )
        return
    payload = gate_suggest_logic.review_payload(
        result.suggestions, result.skipped, codes=codes
    )
    click.echo(
        f"{len(result.suggestions)} suggestion(s), "
        f"{result.skipped} not inlinable",
        err=True,
    )
    if dry_run:
        click.echo(gate_suggest_logic.dump_payload(payload))
        return
    if not repo or pr is None:
        raise click.UsageError("--repo and --pr are required unless --dry-run")
    if not gate_suggest_logic.post_review(repo, pr, payload):
        raise SystemExit(1)
