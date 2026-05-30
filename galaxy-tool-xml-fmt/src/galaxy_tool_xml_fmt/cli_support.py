"""Shared CLI plumbing for the fmt CLI and the ``galaxy-tool-refactor`` app.

Both CLIs want the same black-like ergonomics around a per-file rewrite:
positional ``FILE...`` (directories expand to ``*.xml`` recursively), ``--check``
to detect drift without writing, ``--diff`` to preview, ``--quiet`` to suppress
per-file output, non-tool-XML skipped quietly, per-file errors isolated, and a
trailing summary. The only thing that differs is the *transform* — the function
that turns a parsed ``ToolDocument`` into the bytes to write — and the action
verbs in the output. This module owns everything else.

It lives in the fmt package (rather than a lower tier) because the transforms
all end in fmt's serializer, and the app tier already depends on fmt.
"""

from __future__ import annotations

import difflib
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path

import click
from galaxy_tool_xml.binding import ToolXmlSyntaxError, load_tool
from galaxy_tool_xml.document import ToolDocument


@dataclass(frozen=True)
class TransformOutcome:
    """The result of a per-file transform.

    Attributes:
        formatted: The bytes to write (or compare against the original).
        notes: Per-file lines to print under the result line, each on its own
            line — e.g. which profile upgrades a tool received, or advisory
            (report-only) findings a selection included that never mutate the
            file. Empty by default.
    """

    formatted: bytes
    notes: tuple[str, ...] = ()


@dataclass(frozen=True)
class Action:
    """The verbs shown in per-file and summary output for one command.

    Attributes:
        past: Past participle, e.g. ``"reformatted"`` / ``"upgraded"``.
        conditional: ``--check`` per-file phrase, e.g. ``"would reformat"``.
    """

    past: str
    conditional: str


@dataclass(frozen=True)
class RunOptions:
    """CLI flags resolved for one invocation."""

    check: bool
    diff: bool
    quiet: bool


@dataclass
class Counts:
    """Tally of per-file outcomes across a single CLI invocation."""

    changed: int = 0
    would_change: int = 0
    unchanged: int = 0
    skipped: int = 0
    errored: int = 0


def iter_targets(paths: Iterable[Path]) -> Iterable[Path]:
    """Expand each positional argument to one or more concrete ``*.xml`` paths.

    A file path yields itself. A directory path yields every ``*.xml`` file
    beneath it (recursive, sorted for reproducible ordering).
    """
    for path in paths:
        if path.is_dir():
            yield from sorted(path.rglob("*.xml"))
        else:
            yield path


def is_tool_root(xml_bytes: bytes) -> bool:
    """Cheap pre-check: does the document's first element open ``<tool``?

    Skips macro / test XML before paying for a full parse. Accepts leading
    whitespace, an XML declaration, comments, and a DOCTYPE before the root.
    A false negative is acceptable (the file is then skipped); a false
    positive is caught by the post-parse tag check.
    """
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


def _print_diff(path: Path, original: bytes, formatted: bytes) -> None:
    """Print a unified diff between ``original`` and ``formatted``."""
    diff = difflib.unified_diff(
        original.decode("utf-8", errors="replace").splitlines(keepends=True),
        formatted.decode("utf-8", errors="replace").splitlines(keepends=True),
        fromfile=f"{path} (original)",
        tofile=f"{path} (rewritten)",
    )
    click.echo("".join(diff), nl=False)


def _echo_notes(outcome: TransformOutcome, options: RunOptions) -> None:
    """Print a transform's per-file notes unless output is suppressed."""
    if options.quiet:
        return
    for note in outcome.notes:
        click.echo(note)


def _process_file(
    path: Path,
    *,
    transform: Callable[[ToolDocument], TransformOutcome],
    action: Action,
    options: RunOptions,
    counts: Counts,
) -> None:
    """Apply ``transform`` to one file in place, or preview per ``options``.

    Per-file errors are reported to stderr and counted but never stop the run.
    """
    try:
        original = path.read_bytes()
    except OSError as error:
        click.echo(f"error: cannot read {path}: {error}", err=True)
        counts.errored += 1
        return
    if not is_tool_root(original):
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
    outcome = transform(document)
    if outcome.formatted == original:
        counts.unchanged += 1
        if not options.quiet and not options.check and not options.diff:
            click.echo(f"unchanged {path}")
            _echo_notes(outcome, options)
        return
    if options.diff:
        _print_diff(path, original, outcome.formatted)
    if options.check:
        counts.would_change += 1
        if not options.quiet:
            click.echo(f"{action.conditional} {path}")
        _echo_notes(outcome, options)
        return
    if options.diff:
        # --diff is preview-only: do not write.
        counts.would_change += 1
        return
    try:
        path.write_bytes(outcome.formatted)
    except OSError as error:
        click.echo(f"error: cannot write {path}: {error}", err=True)
        counts.errored += 1
        return
    counts.changed += 1
    if not options.quiet:
        click.echo(f"{action.past} {path}")
    _echo_notes(outcome, options)


def _summary(counts: Counts, *, action: Action, options: RunOptions) -> str:
    """Render the trailing summary line, mirroring black's phrasing."""
    parts: list[str] = []
    if options.check:
        if counts.would_change:
            parts.append(f"{counts.would_change} file(s) would be {action.past}")
        if counts.unchanged:
            parts.append(f"{counts.unchanged} file(s) would be left unchanged")
    else:
        if counts.changed:
            parts.append(f"{counts.changed} file(s) {action.past}")
        if counts.unchanged:
            parts.append(f"{counts.unchanged} file(s) left unchanged")
    if counts.skipped:
        parts.append(f"{counts.skipped} skipped (not a Galaxy tool)")
    if counts.errored:
        parts.append(f"{counts.errored} errored")
    return ", ".join(parts) + "." if parts else "no files processed."


def run(
    paths: Iterable[Path],
    *,
    transform: Callable[[ToolDocument], TransformOutcome],
    action: Action,
    options: RunOptions,
) -> int:
    """Process every target through ``transform`` and return an exit code.

    Exit code is 1 if any file errored, or — under ``--check`` — if any file
    would change; otherwise 0.
    """
    counts = Counts()
    for target in iter_targets(paths):
        _process_file(
            target,
            transform=transform,
            action=action,
            options=options,
            counts=counts,
        )
    if not options.quiet:
        click.echo(_summary(counts, action=action, options=options))
    if counts.errored:
        return 1
    if options.check and counts.would_change:
        return 1
    return 0
