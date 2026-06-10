"""Architecture guard: fmt is the only tier that serialises canonical XML.

The load-bearing invariant ``fmt is the only tier that serialises canonical
output XML`` (``ARCHITECTURE.md``; the registry ``CLAUDE.md`` "fmt is still the
only serializer") is honoured by the code but otherwise unguarded — a future
codemod doing ``path.write_bytes(etree.tostring(...))`` would pass CI silently.

This test greps every package's ``src/`` for the two serialise primitives
(``etree.tostring(`` and ``.write_bytes(``) and fails on any site that is not in
the allowlist below. Every allowed site carries a one-line justification; a new
serialise call must either route through fmt's ``serializer.to_bytes`` /
``format_*`` (and so produce fmt bytes) or be added here with a reason.

Audit provenance: ``docs/architecture_audit.md`` §4.1 (corroborated by the
multi-agent escalation as the priority proposal).
"""

from __future__ import annotations

from pathlib import Path

# The workspace root is two levels up from this test file
# (<root>/galaxy-tool-refactor-registry/tests/<this file>).
_WORKSPACE_ROOT = Path(__file__).resolve().parents[2]

# The two ways a tier could serialise XML to bytes / disk.
_SERIALISE_MARKERS = ("etree.tostring(", ".write_bytes(")

# relative-path -> (allowed markers, justification). A ``src/`` line containing a
# marker is legitimate only if its file is here AND the marker is in that file's
# allowed set. Keep this in sync with ``docs/architecture_audit.md`` §4.1.
_ALLOWLIST: dict[str, tuple[frozenset[str], str]] = {
    "galaxy-tool-xml-codemod/src/galaxy_tool_xml_codemod/codemods"
    "/tokenize_version.py": (
        frozenset({"etree.tostring("}),
        "GTR094's expansion-equality gate compares two throwaway expansions "
        "byte-wise (proof by execution) — never output; output still flows "
        "through fmt via the facade",
    ),
    "galaxy-tool-xml-fmt/src/galaxy_tool_xml_fmt/serializer.py": (
        frozenset({"etree.tostring("}),
        "the sanctioned canonical serialiser (fmt's to_bytes)",
    ),
    "galaxy-tool-xml-fmt/src/galaxy_tool_xml_fmt/cli_support.py": (
        frozenset({".write_bytes("}),
        "writes fmt-produced canonical bytes to disk",
    ),
    "galaxy-tool-refactor-cli/src/galaxy_tool_refactor_cli/cli.py": (
        frozenset({".write_bytes("}),
        "convert-help writes facade-produced (fmt-serialised) bytes after "
        "make_backup; the write-after-backup ordering is CLI policy the "
        "facade's write_path cannot express",
    ),
    "galaxy-tool-refactor-registry/src/galaxy_tool_refactor_registry/facade.py": (
        frozenset({".write_bytes("}),
        "writes fmt-produced canonical bytes when a write_path is given",
    ),
    (
        "galaxy-tool-refactor-registry/src/galaxy_tool_refactor_registry/"
        "macro_profile.py"
    ): (
        frozenset({".write_bytes("}),
        "writes fmt-produced macro-file bytes (format_macro_document)",
    ),
    (
        "galaxy-tool-refactor-registry/src/galaxy_tool_refactor_registry/"
        "macro_datatype.py"
    ): (
        frozenset({".write_bytes("}),
        "writes fmt-produced macro-file bytes (format_macro_document)",
    ),
    (
        "galaxy-tool-refactor-registry/src/galaxy_tool_refactor_registry/"
        "bundle_rename.py"
    ): (
        frozenset({".write_bytes("}),
        "cross-file rename writes fmt-produced tool + macro bytes "
        "(format_tool_document_subset / format_macro_document)",
    ),
    "galaxy-tool-xml-codemod/src/galaxy_tool_xml_codemod/codemods/_coarse_detect.py": (
        frozenset({"etree.tostring("}),
        "internal before/after compare to detect change (not output)",
    ),
    "galaxy-tool-source/src/galaxy_tool_source/cdata.py": (
        frozenset({"etree.tostring("}),
        "serialise one element to a str for read-only CDATA detection",
    ),
    "galaxy-tool-source/src/galaxy_tool_source/document.py": (
        frozenset({"etree.tostring("}),
        "internal serialise-then-reparse to bind the typed model (not output)",
    ),
    "galaxy-tool-source/src/galaxy_tool_source/macros.py": (
        frozenset({"etree.tostring(", ".write_bytes("}),
        "throwaway temp-dir round-trip for Galaxy's path-based macro expander",
    ),
}


def _markers_in(line: str) -> list[str]:
    """Return the serialise markers present in *line*."""
    return [marker for marker in _SERIALISE_MARKERS if marker in line]


def _serialise_sites() -> list[tuple[str, int, str]]:
    """Every ``(relpath, lineno, marker)`` serialise call across all ``src/``."""
    sites: list[tuple[str, int, str]] = []
    for src_dir in sorted(_WORKSPACE_ROOT.glob("*/src")):
        for module in sorted(src_dir.rglob("*.py")):
            relpath = module.relative_to(_WORKSPACE_ROOT).as_posix()
            text = module.read_text(encoding="utf-8")
            for lineno, line in enumerate(text.splitlines(), start=1):
                for marker in _markers_in(line):
                    sites.append((relpath, lineno, marker))
    return sites


def test_no_serialise_site_outside_the_allowlist() -> None:
    """Only fmt (and the documented internal/throwaway sites) may serialise XML."""
    offenders: list[str] = []
    for relpath, lineno, marker in _serialise_sites():
        entry = _ALLOWLIST.get(relpath)
        if entry is None or marker not in entry[0]:
            offenders.append(f"{relpath}:{lineno} uses {marker!r}")

    assert not offenders, (
        "Unsanctioned XML-serialise site(s) found in src/:\n  "
        + "\n  ".join(offenders)
        + "\n\nfmt is the only tier that serialises canonical output XML. Route "
        "the bytes through fmt's serialiser / format_* functions, or — if this "
        "is a genuinely internal/throwaway use — add it to _ALLOWLIST with a "
        "justification (see docs/architecture_audit.md §4.1)."
    )


def test_allowlist_has_no_stale_entries() -> None:
    """Every allowlisted (path, marker) still corresponds to a real src/ site."""
    live: set[tuple[str, str]] = {
        (relpath, marker) for relpath, _lineno, marker in _serialise_sites()
    }
    stale = [
        f"{relpath} :: {marker!r}"
        for relpath, (markers, _why) in _ALLOWLIST.items()
        for marker in markers
        if (relpath, marker) not in live
    ]
    assert not stale, (
        "Stale _ALLOWLIST entries (no longer present in src/); remove them:\n  "
        + "\n  ".join(stale)
    )
