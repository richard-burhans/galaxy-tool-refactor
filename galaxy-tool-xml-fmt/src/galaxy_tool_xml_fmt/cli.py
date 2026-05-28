"""The ``galaxy-tool-xml-fmt`` command-line interface.

Mirrors ``black``'s ergonomics: positional ``FILE...`` (directories
expand to ``*.xml`` recursively), ``--check`` to detect drift without
writing, ``--diff`` to preview the rewrite as a unified diff, ``--quiet``
to suppress per-file output.

Non-Galaxy-tool XML files (root element ≠ ``<tool>``) are skipped
quietly so a directory pointed at a mixed tree (tools, macros, tests)
only reformats the tools. A malformed XML file is reported as an error
but doesn't stop the run; the exit code is non-zero if any file errored
or, under ``--check``, if any file would be reformatted.
"""

from __future__ import annotations

import difflib
import sys
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

import click
from galaxy_tool_xml.binding import ToolXmlSyntaxError, load_tool

from galaxy_tool_xml_fmt.format import format_tool_document


@dataclass
class _Counts:
    """Tally of per-file outcomes across a single CLI invocation.

    The exit code in ``main`` is derived from ``errored`` (any error)
    and, under ``--check``, from ``would_reformat``. ``skipped`` is
    informational only — non-tool XML never affects the exit code.
    """

    reformatted: int = 0
    would_reformat: int = 0
    unchanged: int = 0
    skipped: int = 0
    errored: int = 0


def _iter_targets(paths: Iterable[Path]) -> Iterable[Path]:
    """Expand each positional argument to one or more concrete ``*.xml`` paths.

    A file path yields itself. A directory path yields every ``*.xml``
    file beneath it (recursive). Ordering is stable: directory globs
    are sorted so output is reproducible across platforms.
    """
    for path in paths:
        if path.is_dir():
            yield from sorted(path.rglob("*.xml"))
        else:
            yield path


def _is_tool_root(xml_bytes: bytes) -> bool:
    """Cheap pre-check: does the bytes start with a ``<tool`` root tag?

    Used to skip macro / test XML files before we pay for a full
    parse + format. The check accepts any whitespace, an optional XML
    declaration / comments, and then ``<tool`` as the first element
    open. A false negative on a valid tool with exotic preamble is
    acceptable (the file is then skipped); a false positive is caught
    by the post-parse tag check.
    """
    # Look for the first non-whitespace ``<`` that isn't an XML decl or
    # comment. Cheap text scan; we only need to peek at the start.
    head = xml_bytes[:4096].decode("utf-8", errors="replace")
    index = 0
    while index < len(head):
        if head[index].isspace():
            index += 1
            continue
        if head.startswith("<?", index):
            close = head.find("?>", index)
            if close == -1:
                return False
            index = close + 2
            continue
        if head.startswith("<!--", index):
            close = head.find("-->", index)
            if close == -1:
                return False
            index = close + 3
            continue
        if head.startswith("<!DOCTYPE", index):
            close = head.find(">", index)
            if close == -1:
                return False
            index = close + 1
            continue
        return head.startswith("<tool", index)
    return False


@dataclass
class _Options:
    """CLI flags resolved for one invocation."""

    check: bool
    diff: bool
    quiet: bool


def _process_file(path: Path, options: _Options, counts: _Counts) -> None:
    """Format one file in place, or preview the rewrite per ``options``.

    Per-file errors are reported to stderr and incremented in
    ``counts.errored`` but do not stop the run — the user usually wants
    every file's outcome on the first pass.
    """
    # third-party API: path.read_bytes can raise OSError; the CLI
    # boundary catches it and reports rather than crashing the run.
    try:
        original = path.read_bytes()
    except OSError as error:
        click.echo(f"error: cannot read {path}: {error}", err=True)
        counts.errored += 1
        return
    if not _is_tool_root(original):
        counts.skipped += 1
        return
    try:
        document = load_tool(original)
    except ToolXmlSyntaxError as error:
        click.echo(f"error: {path}: malformed XML: {error}", err=True)
        counts.errored += 1
        return
    if document.root.tag != "tool":
        counts.skipped += 1
        return
    formatted = format_tool_document(document)
    if formatted == original:
        counts.unchanged += 1
        if not options.quiet and not options.check and not options.diff:
            click.echo(f"unchanged {path}")
        return
    if options.diff:
        _print_diff(path, original, formatted)
    if options.check:
        counts.would_reformat += 1
        if not options.quiet:
            click.echo(f"would reformat {path}")
        return
    if options.diff:
        # --diff is preview-only: do not write.
        counts.would_reformat += 1
        return
    try:
        path.write_bytes(formatted)
    except OSError as error:
        click.echo(f"error: cannot write {path}: {error}", err=True)
        counts.errored += 1
        return
    counts.reformatted += 1
    if not options.quiet:
        click.echo(f"reformatted {path}")


def _print_diff(path: Path, original: bytes, formatted: bytes) -> None:
    """Print a unified diff between ``original`` and ``formatted``."""
    diff = difflib.unified_diff(
        original.decode("utf-8", errors="replace").splitlines(keepends=True),
        formatted.decode("utf-8", errors="replace").splitlines(keepends=True),
        fromfile=f"{path} (original)",
        tofile=f"{path} (formatted)",
    )
    click.echo("".join(diff), nl=False)


def _summary(counts: _Counts, options: _Options) -> str:
    """Render the trailing summary line, mirroring black's phrasing."""
    parts: list[str] = []
    if options.check:
        if counts.would_reformat:
            parts.append(
                f"{counts.would_reformat} file(s) would be reformatted"
            )
        if counts.unchanged:
            parts.append(f"{counts.unchanged} file(s) would be left unchanged")
    else:
        if counts.reformatted:
            parts.append(f"{counts.reformatted} file(s) reformatted")
        if counts.unchanged:
            parts.append(f"{counts.unchanged} file(s) left unchanged")
    if counts.skipped:
        parts.append(f"{counts.skipped} skipped (not a Galaxy tool)")
    if counts.errored:
        parts.append(f"{counts.errored} errored")
    return ", ".join(parts) + "." if parts else "no files processed."


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
    """Format Galaxy tool XML files to the project's canonical layout.

    PATHS may be files or directories. Directories are searched
    recursively for ``*.xml`` files; non-Galaxy-tool XML (root element
    not ``<tool>``) is skipped.
    """
    options = _Options(check=check, diff=diff, quiet=quiet)
    counts = _Counts()
    for target in _iter_targets(paths):
        _process_file(target, options, counts)
    if not quiet:
        click.echo(_summary(counts, options), err=False)
    if counts.errored:
        sys.exit(1)
    if check and counts.would_reformat:
        sys.exit(1)


if __name__ == "__main__":
    main()
