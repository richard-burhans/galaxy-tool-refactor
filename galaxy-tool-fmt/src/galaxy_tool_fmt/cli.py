"""The ``galaxy-tool-fmt`` command-line interface.

A ``black``-like **cosmetic** formatter: positional ``FILE...`` (directories
expand to ``*.xml`` recursively), ``--check`` to detect drift without writing,
``--diff`` to preview the rewrite, ``--quiet`` to suppress per-file output.
Both tool files (``<tool>`` root) and macro-library files (``<macros>`` root)
are formatted; other XML is skipped quietly.

This CLI applies **cosmetic rules only** (indentation, blank lines,
empty-element shorthand). Each rule runs only on the document kinds it applies
to (``RuleMeta.applies_to``): a macro file gets the generic XML rules
(indentation, empty-element shorthand) but not the tool-only blank-line rule.
Structural canonicalisation (attribute order) and profile upgrades live in the
``galaxy-tool-refactor`` app (``galaxy-tool-refactor-cli``), which composes the
codemod and fmt tiers; this package stays a single-purpose cosmetic formatter.
"""

from __future__ import annotations

import sys
from pathlib import Path

import click

from galaxy_tool_fmt.cli_support import (
    Action,
    RunOptions,
    TransformOutcome,
    run,
)
from galaxy_tool_fmt.format import format_macro_document, format_tool_document

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
    """Cosmetically format Galaxy tool and macro XML files to the canonical layout.

    PATHS may be files or directories. Directories are searched recursively for
    ``*.xml`` files; tool (``<tool>``) and macro-library (``<macros>``) files are
    formatted, other XML is skipped. Macro files receive only the kind-applicable
    rules (indentation, empty-element shorthand).
    """
    options = RunOptions(check=check, diff=diff, quiet=quiet)
    code = run(
        paths,
        transform=lambda document: TransformOutcome(
            format_tool_document(document)
        ),
        macro_transform=lambda document: TransformOutcome(
            format_macro_document(document)
        ),
        action=_ACTION,
        options=options,
    )
    sys.exit(code)


if __name__ == "__main__":
    main()
