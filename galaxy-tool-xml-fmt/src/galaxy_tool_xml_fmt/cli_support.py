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
from galaxy_tool_xml.binding import ToolXmlSyntaxError, load_macros, load_tool
from galaxy_tool_xml.document import MacroDocument, ToolDocument


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


def _root_opens(xml_bytes: bytes, token: str) -> bool:
    """Cheap pre-check: does the document's first element open with *token*?

    Skips a leading XML declaration, comments, and a DOCTYPE, then tests whether
    the root element starts with *token* (e.g. ``"<tool"`` or ``"<macros"``).
    A false negative is acceptable (the file is then skipped); a false positive
    is caught by the post-parse tag check. Avoids a full parse on non-matching
    files (e.g. ``tool_data_table_conf`` / test XML).
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
        return head.startswith(token, index)
    return False


def is_tool_root(xml_bytes: bytes) -> bool:
    """Cheap pre-check: does the document's first element open ``<tool``?"""
    return _root_opens(xml_bytes, "<tool")


def is_macros_root(xml_bytes: bytes) -> bool:
    """Cheap pre-check: does the document's first element open ``<macros``?

    ``"<macros"`` does not match a ``<macro>`` element (missing the trailing
    ``s``), so this fires only on a macro-*library* file's root.
    """
    return _root_opens(xml_bytes, "<macros")


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


def _report_malformed(path: Path, error: ToolXmlSyntaxError, counts: Counts) -> None:
    """Report a malformed-XML load failure to stderr and count it."""
    click.echo(f"error: {path}: malformed XML: {error}", err=True)
    counts.errored += 1


def _transform_file(
    original: bytes,
    path: Path,
    *,
    transform: Callable[[ToolDocument], TransformOutcome],
    macro_transform: Callable[[MacroDocument], TransformOutcome] | None,
    counts: Counts,
) -> TransformOutcome | None:
    """Load *original* by document kind and run the matching transform.

    Returns the outcome, or ``None`` when the file was skipped (not a tool, or a
    macro file with no ``macro_transform``) or errored — ``counts`` is updated in
    those cases. Macro files are only processed when *macro_transform* is given,
    so a caller that does not opt in keeps the historical tool-only behaviour.
    """
    if is_tool_root(original):
        try:
            tool_document = load_tool(original)
        except ToolXmlSyntaxError as error:
            _report_malformed(path, error, counts)
            return None
        if tool_document.root.tag != "tool":
            counts.skipped += 1
            return None
        return transform(tool_document)
    if macro_transform is not None and is_macros_root(original):
        try:
            macro_document = load_macros(original)
        except ToolXmlSyntaxError as error:
            _report_malformed(path, error, counts)
            return None
        if macro_document.root.tag != "macros":
            counts.skipped += 1
            return None
        return macro_transform(macro_document)
    counts.skipped += 1
    return None


def _process_file(
    path: Path,
    *,
    transform: Callable[[ToolDocument], TransformOutcome],
    macro_transform: Callable[[MacroDocument], TransformOutcome] | None,
    action: Action,
    options: RunOptions,
    counts: Counts,
) -> None:
    """Apply the matching transform to one file in place, or preview per ``options``.

    Per-file errors are reported to stderr and counted but never stop the run.
    """
    try:
        original = path.read_bytes()
    except OSError as error:
        click.echo(f"error: cannot read {path}: {error}", err=True)
        counts.errored += 1
        return
    outcome = _transform_file(
        original,
        path,
        transform=transform,
        macro_transform=macro_transform,
        counts=counts,
    )
    if outcome is None:
        return
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
    macro_transform: Callable[[MacroDocument], TransformOutcome] | None = None,
) -> int:
    """Process every target through the matching transform; return an exit code.

    Tool files go through *transform*. When *macro_transform* is given, macro
    *library* files (``<macros>`` root) are processed too; without it they are
    skipped (the historical tool-only behaviour). Exit code is 1 if any file
    errored, or — under ``--check`` — if any file would change; otherwise 0.
    """
    counts = Counts()
    for target in iter_targets(paths):
        _process_file(
            target,
            transform=transform,
            macro_transform=macro_transform,
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
