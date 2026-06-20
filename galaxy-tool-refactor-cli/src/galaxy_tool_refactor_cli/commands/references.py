"""The ``find-references`` subcommand: read-only Cheetah ``$NAME`` reference query."""

from __future__ import annotations

import sys
from pathlib import Path

import click
from galaxy_tool_fmt.cli_support import is_tool_root, iter_targets
from galaxy_tool_refactor_registry.bundle_rename import find_references_in_bundle
from galaxy_tool_source.binding import ToolXmlSyntaxError

from galaxy_tool_refactor_cli.options import _PATH_ARGUMENT, _QUIET_OPTION


@click.command(name="find-references")
@click.argument("name")
@_PATH_ARGUMENT
@_QUIET_OPTION
def find_references_command(
    name: str, paths: tuple[Path, ...], quiet: bool
) -> None:
    """Report every Cheetah $NAME reference across a tool **and its imported macros**.

    Read-only query (mutates nothing). For each tool it scans the tool's own
    ``<command>``, inline ``<configfile>``\\ s, env vars, output labels and dynamic
    options **plus every macro file it imports** (where a reference frequently lives),
    and prints one ``file:line  [section]  $ref`` per occurrence whose identifier path
    includes NAME (so ``$NAME``, ``$cond.NAME`` and ``$NAME.ext`` all match). PATHS may
    be files or directories; non-tool XML is skipped. Occurrences are de-duplicated, so
    a macro shared by several scanned tools is reported once. Conservative — may include
    occurrences in comments/``#raw`` (see ``galaxy_tool_source.cheetah_refs``). Non-zero
    exit on errors.
    """
    total = scanned = skipped = errored = 0
    seen: set[tuple[str, int, str, str]] = set()
    for target in iter_targets(paths):
        try:
            original = target.read_bytes()
        except OSError as error:
            click.echo(f"error: cannot read {target}: {error}", err=True)
            errored += 1
            continue
        if not is_tool_root(original):
            skipped += 1
            continue
        try:
            result = find_references_in_bundle(target, name=name)
        except ToolXmlSyntaxError as error:
            click.echo(f"error: {target}: malformed XML: {error}", err=True)
            errored += 1
            continue
        scanned += 1
        for ref in result.references:
            key = (str(ref.path), ref.sourceline, ref.section, ref.reference)
            if key in seen:
                continue
            seen.add(key)
            total += 1
            if not quiet:
                click.echo(
                    f"{ref.path}:{ref.sourceline}  [{ref.section}]  {ref.reference}"
                )
    if not quiet:
        click.echo(f"{total} reference(s) to '{name}' across {scanned} tool(s)")
    sys.exit(1 if errored else 0)
