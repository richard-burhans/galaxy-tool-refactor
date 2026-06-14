"""Tests for the vendored Galaxy datatype registry (GTR098 ValidDatatypes data)."""

from __future__ import annotations

import pytest

from galaxy_tool_lint.checks.datatypes import (
    _parse_datatypes,
    builtin_datatypes,
)


def test_builtin_datatypes_loads_known_extensions() -> None:
    datatypes = builtin_datatypes()
    # A representative spread of the vendored sample's registrations.
    assert {"bam", "fasta", "tabular", "txt", "data"} <= datatypes


def test_builtin_datatypes_is_cached_frozenset() -> None:
    assert isinstance(builtin_datatypes(), frozenset)
    assert builtin_datatypes() is builtin_datatypes()


def test_builtin_datatypes_excludes_pseudo_formats() -> None:
    # ``auto`` and ``input`` are NOT registered datatypes — Galaxy special-cases
    # them in the linter, so they must not leak into the membership set.
    datatypes = builtin_datatypes()
    assert "auto" not in datatypes
    assert "input" not in datatypes


def test_parse_datatypes_expands_auto_compressed_types() -> None:
    data = (
        b"<datatypes><registration>"
        b'<datatype extension="bam" auto_compressed_types="gz,bz2"/>'
        b'<datatype extension="fasta"/>'
        b"</registration></datatypes>"
    )
    assert _parse_datatypes(data) == {"bam", "bam.gz", "bam.bz2", "fasta"}


def test_parse_datatypes_empty_auto_compressed_adds_nothing() -> None:
    data = (
        b"<datatypes><registration>"
        b'<datatype extension="tabular" auto_compressed_types=""/>'
        b"</registration></datatypes>"
    )
    assert _parse_datatypes(data) == {"tabular"}


def test_vendored_snapshot_matches_installed_galaxy_tool_util() -> None:
    """Drift guard: our vendored sample == the installed galaxy-tool-util's.

    Faithful parity means matching what planemo (galaxy-tool-util) reports. The
    snapshot is a vendored copy of the package's bundled ``datatypes_conf.xml.sample``;
    when the dep moves and its sample changes, re-vendor it (copy the installed file).
    Skips when galaxy-tool-util is absent (a dev/CI-only oracle, like the test-case
    validator).
    """
    galaxy_datatypes = pytest.importorskip("galaxy.tool_util.linters.datatypes")
    from galaxy.util.resources import resource_path

    installed = galaxy_datatypes._parse_datatypes(
        resource_path(galaxy_datatypes.__name__, "datatypes_conf.xml.sample")
    )
    assert builtin_datatypes() == set(installed), (
        "the vendored datatypes_conf.xml.sample has drifted from the installed "
        "galaxy-tool-util — re-vendor it (copy the package's bundled sample) so "
        "GTR098 matches what planemo reports"
    )
