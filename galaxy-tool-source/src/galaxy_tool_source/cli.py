"""The ``galaxy-tool-source`` command-line interface.

Each command is an error boundary: a foreseeable failure is reported with
``click.echo(..., err=True)`` and turned into a non-zero exit, rather than a
traceback. Unlike the library modules, the CLI installs a logging handler so
the informational and warning messages emitted during resolution and macro
expansion reach the user.
"""

from __future__ import annotations

import logging
from pathlib import Path

import click

from galaxy_tool_source.binding import ValidationResult, validate_tool
from galaxy_tool_source.corrections import suggest_corrections
from galaxy_tool_source.profiles import (
    UnknownProfileError,
    available_profiles,
    latest_profile,
)

_FILES_ARGUMENT = click.argument(
    "files",
    nargs=-1,
    required=True,
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
)


@click.group()
@click.option("-v", "--verbose", is_flag=True, help="Show informational log messages.")
def main(verbose: bool) -> None:
    """Parse, validate, and inspect Galaxy tool definition XML."""
    package_logger = logging.getLogger("galaxy_tool_source")
    if not package_logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
        package_logger.addHandler(handler)
    package_logger.setLevel(logging.INFO if verbose else logging.WARNING)


def _echo_validation(file: Path, result: ValidationResult) -> bool:
    """Print one file's validation result; return whether it had errors."""
    has_errors = bool(result.syntax_errors or result.macro_errors or result.errors)
    if result.valid:
        status = "valid"
    elif not result.validated and not has_errors:
        status = "skipped"
    else:
        status = "invalid"
    suffix = f" (schema {result.schema_version})" if result.schema_version else ""
    click.echo(f"{file}: {status}{suffix}")
    for error in result.syntax_errors:
        click.echo(f"  syntax error: {error}", err=True)
    for macro_error in result.macro_errors:
        click.echo(f"  macro error: {macro_error}", err=True)
    for error in result.errors:
        click.echo(f"  schema error: {error}", err=True)
    return has_errors


@main.command()
@_FILES_ARGUMENT
@click.option("--profile", default=None, help="Override the tool's declared profile.")
@click.option(
    "--on-missing",
    type=click.Choice(["nearest", "exact", "latest"]),
    default="nearest",
    help="How to resolve a profile with no exact vendored schema.",
)
@click.option(
    "--macro-handling",
    type=click.Choice(["off", "skip", "strip", "expand"]),
    default="expand",
    help="How to treat macros before validation.",
)
def validate(
    files: tuple[Path, ...],
    profile: str | None,
    on_missing: str,
    macro_handling: str,
) -> None:
    """Validate Galaxy tool XML against the profile-appropriate XSD."""
    failed = False
    for file in files:
        try:
            result = validate_tool(
                file,
                profile=profile,
                on_missing=on_missing,
                macro_handling=macro_handling,
            )
        except UnknownProfileError as error:
            click.echo(f"{file}: error: {error}", err=True)
            failed = True
            continue
        if _echo_validation(file, result):
            failed = True
    if failed:
        raise SystemExit(1)


@main.command()
@_FILES_ARGUMENT
def suggest(files: tuple[Path, ...]) -> None:
    """Suggest near-miss typo fixes against the schema vocabulary."""
    found = False
    for file in files:
        corrections = suggest_corrections(file)
        for correction in corrections:
            click.echo(f"{file}: {correction}")
        if corrections:
            found = True
        else:
            click.echo(f"{file}: no suggestions")
    if found:
        raise SystemExit(1)


@main.command()
def profiles() -> None:
    """List the vendored XSD profile versions."""
    latest = latest_profile()
    for version in available_profiles():
        marker = "  (latest)" if version == latest else ""
        click.echo(f"{version}{marker}")
