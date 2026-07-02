"""The ``convert-help`` subcommand: RST ``<help>`` -> Markdown, render-gated."""

from __future__ import annotations

from pathlib import Path

import click
from galaxy_tool_fmt.cli_support import (
    is_tool_root,
    iter_targets,
    make_backup,
    report_malformed_xml,
)
from galaxy_tool_refactor_registry import facade
from galaxy_tool_source.binding import ToolXmlSyntaxError, load_tool

from galaxy_tool_refactor_cli.options import _BACKUP_OPTION


@click.command(name="convert-help")
@click.argument(
    "paths", nargs=-1, required=True, type=click.Path(exists=True, path_type=Path)
)
@click.option(
    "--check", is_flag=True, help="Report what would convert and write nothing."
)
@_BACKUP_OPTION
def convert_help_command(paths: tuple[Path, ...], check: bool, backup: bool) -> None:
    """Convert RST <help> bodies to Markdown (opt-in, render-equivalence gated).

    Rewrites a tool's reStructuredText ``<help>`` as Markdown and marks it
    ``format="markdown"`` — only when the conversion is *provable*: the tool's
    profile must be >= 24.2 (``<help format=…>`` is not XSD-valid earlier — run
    ``upgrade`` first), and the markdown-it rendering must be semantically equal
    to the docutils rendering (invalid RST is first passed through the GTR089.1
    repair). Anything unprovable is skipped with the reason. This conversion
    swaps Galaxy's rendering engine (server-side docutils -> client-side
    markdown-it), which is why it is a deliberate, separate command — never part
    of ``format``/``upgrade``. Needs the ``galaxy-tool-source[markdown]`` extra.
    """
    converted = skipped = errored = 0
    for target in iter_targets(paths):
        try:
            original = target.read_bytes()
        except OSError as error:
            click.echo(f"error: cannot read {target}: {error}", err=True)
            errored += 1
            continue
        if not is_tool_root(original):
            continue
        try:
            document = load_tool(original)
        except ToolXmlSyntaxError as error:
            report_malformed_xml(target, error=error)
            errored += 1
            continue
        result = facade.convert_help(document)
        if result.converted:
            converted += 1
            if not check:
                if backup:
                    make_backup(target)
                target.write_bytes(result.formatted)
            click.echo(f"{'would convert' if check else 'converted'} {target}")
        else:
            skipped += 1
            click.echo(f"skipped {target}: {result.skip_reason}")
    click.echo(
        f"{converted} converted, {skipped} skipped"
        + (f", {errored} error(s)" if errored else "")
    )
    if errored:
        raise SystemExit(1)
