"""The ``rulesets`` and ``rules`` introspection subcommands."""

from __future__ import annotations

import click
from galaxy_tool_refactor_registry import facade


@click.command(name="rulesets")
def rulesets_command() -> None:
    """List the available rulesets and the rule codes each one selects."""
    for info in facade.list_rulesets():
        default = " (default)" if info.is_default else ""
        click.echo(f"{info.name}{default}: {info.description}")
        click.echo(f"  rules: {', '.join(info.codes)}")


@click.command(name="rules")
@click.option(
    "--include-upgrade",
    is_flag=True,
    help=(
        "Also list the non-selectable codemods: the upgrade-pipeline steps and "
        "the opt-in-command-only rules (e.g. GTR092, applied by convert-help)."
    ),
)
def rules_command(include_upgrade: bool) -> None:
    """List the baked-in rules: code, family, fixable/advisory, rulesets, planemo.

    The ``planemo:`` field lists the planemo (``galaxy.tool_util.lint``) linter(s)
    each rule covers — those names also work in ``--select`` / ``--ignore``.
    """
    for info in facade.list_rules(include_upgrade=include_upgrade):
        kind = "fixable" if info.fixable else "advisory"
        in_rulesets = ",".join(info.rulesets) if info.rulesets else "-"
        planemo = ",".join(info.planemo_linters) if info.planemo_linters else "-"
        doc = f"  doc:{info.cite}" if info.cite else ""
        click.echo(
            f"{info.code}  [{info.family}/{kind}]  rulesets:{in_rulesets}  "
            f"planemo:{planemo}  {info.summary}{doc}"
        )
