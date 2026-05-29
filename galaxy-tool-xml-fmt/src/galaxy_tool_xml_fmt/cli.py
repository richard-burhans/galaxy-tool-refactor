"""The ``galaxy-tool-xml-fmt`` command-line interface.

A ``black``-like **cosmetic** formatter: positional ``FILE...`` (directories
expand to ``*.xml`` recursively), ``--check`` to detect drift without writing,
``--diff`` to preview the rewrite, ``--quiet`` to suppress per-file output.
Non-Galaxy-tool XML (root element ≠ ``<tool>``) is skipped quietly.

This CLI applies **cosmetic rules only** (indentation, blank lines,
empty-element shorthand). Structural canonicalisation (attribute order) and
profile upgrades live in the ``galaxy-tool-refactor`` app
(``galaxy-tool-refactor-cli``), which composes the codemod and fmt tiers; this
package stays a single-purpose cosmetic formatter.
"""

from __future__ import annotations

import sys
from pathlib import Path

import click

from galaxy_tool_xml_fmt.cli_support import (
    Action,
    RunOptions,
    TransformOutcome,
    run,
)
from galaxy_tool_xml_fmt.format import format_tool_document

_ACTION = Action(past="reformatted", conditional="would reformat")


@click.command(context_settings={"help_option_names": ["-h", "--help"]})
@click.argument(
    "paths",
    nargs=-1,
    required=True,
    type=click.Path(exists=True, path_type=Path),
)
@click.option(
    "--check",
    is_flag=True,
    help=(
        "Don't write files. Exit non-zero if any file would be reformatted."
    ),
)
@click.option(
    "--diff",
    is_flag=True,
    help="Don't write files. Print a unified diff of the rewrite to stdout.",
)
@click.option(
    "-q",
    "--quiet",
    is_flag=True,
    help="Suppress per-file output; only errors and the summary are shown.",
)
def main(paths: tuple[Path, ...], check: bool, diff: bool, quiet: bool) -> None:
    """Cosmetically format Galaxy tool XML files to the canonical layout.

    PATHS may be files or directories. Directories are searched recursively
    for ``*.xml`` files; non-Galaxy-tool XML (root element not ``<tool>``) is
    skipped.
    """
    options = RunOptions(check=check, diff=diff, quiet=quiet)
    code = run(
        paths,
        transform=lambda document: TransformOutcome(
            format_tool_document(document)
        ),
        action=_ACTION,
        options=options,
    )
    sys.exit(code)


if __name__ == "__main__":
    main()
