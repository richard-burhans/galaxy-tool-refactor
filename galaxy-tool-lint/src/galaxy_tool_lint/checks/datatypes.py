"""Datatype checks (GTR098 ValidDatatypes, GTR099 DatatypesCustomConf).

Reimplements Galaxy's ``galaxy.tool_util.linters.datatypes`` pair as detect-only
checks, with **no runtime ``galaxy-tool-util`` dependency**. The built-in datatype
registry is the extension set parsed from a vendored snapshot of Galaxy's bundled
``datatypes_conf.xml.sample`` (``../data/``).

Soundness / faithfulness: planemo's ``ValidDatatypes`` validates ``format``/``ftype``/
``ext`` against the extensions registered in *its own bundled* sample — it does not
consult a live registry. So matching that bundled sample IS faithful parity. We vendor
the sample (drift-guarded against the installed ``galaxy-tool-util`` in tests) rather
than depend on it. An extension newer than our snapshot would false-positive — the
same limitation Galaxy's own linter has against a plugin-registered type; refresh the
snapshot to track. See ``docs/decisions.md`` D36 and
``../../docs/galaxy_reimplementations.md``.
"""

from __future__ import annotations

from collections.abc import Iterable
from functools import cache
from importlib import resources
from typing import TYPE_CHECKING, ClassVar

from galaxy_tool_refactor_rules.meta import RuleMeta
from lxml import etree
from packaging.version import InvalidVersion, Version

from galaxy_tool_lint.checks._shared import _IUC, _violation
from galaxy_tool_lint.rules import CheckRule

if TYPE_CHECKING:
    from galaxy_tool_refactor_rules.violation import Violation
    from galaxy_tool_source.document import ToolDocument


def _parse_datatypes(data: bytes, /) -> frozenset[str]:
    """The registered extension set parsed from a ``datatypes_conf.xml`` document.

    Mirrors Galaxy's ``galaxy.tool_util.linters.datatypes._parse_datatypes``: each
    ``<registration><datatype extension=…>`` contributes its extension, and every
    ``auto_compressed_types`` entry (comma-split, ``galaxy.util.listify`` semantics)
    contributes ``f"{extension}.{act}"``.
    """
    root = etree.fromstring(data)
    extensions: set[str] = set()
    for elem in root.findall("./registration/datatype"):
        extension = elem.get("extension", "")
        extensions.add(extension)
        raw = elem.get("auto_compressed_types", "")
        for act in raw.split(",") if raw else []:
            extensions.add(f"{extension}.{act}")
    return frozenset(extensions)


@cache
def builtin_datatypes() -> frozenset[str]:
    """Galaxy's built-in datatype extensions, from the vendored sample (cached)."""
    # Single-component joinpath chained via ``/`` so it type-checks on Python 3.10,
    # whose importlib.resources Traversable.joinpath takes only one argument
    # (multi-arg joinpath is 3.11+). See galaxy-tool-lint mypy CI on 3.10.
    data = (
        resources.files("galaxy_tool_lint") / "data" / "datatypes_conf.xml.sample"
    ).read_bytes()
    return _parse_datatypes(data)


def _input_is_free_pass(document: ToolDocument, /) -> bool:
    """Whether ``format="input"`` is allowed unchecked (profile ≤ 16.04).

    Mirrors Galaxy's gate (``Version(profile) <= Version("16.04")``). Absent
    ``profile`` defaults to ``16.01`` (Galaxy's ``parse_profile`` default). A macro
    token or otherwise-unparseable profile resolves conservatively to ``True`` — we
    decline to flag ``input`` rather than risk a false positive.
    """
    profile = document.profile or "16.01"
    if "@" in profile:
        return True
    try:
        return Version(profile) <= Version("16.04")
    except InvalidVersion:
        return True


class DatatypesCustomConf(CheckRule):
    """GTR099 — a tool should not ship a custom ``datatypes_conf.xml``.

    Reimplements planemo ``DatatypesCustomConf``: a ``datatypes_conf.xml`` beside the
    tool registers datatypes locally, which is discouraged (the datatype belongs in
    Galaxy itself). Needs the tool's on-disk location, so it is silent for a document
    parsed from bytes. Detect-only.
    """

    meta: ClassVar[RuleMeta] = RuleMeta(
        code="GTR099",
        summary="A tool should not ship a custom datatypes_conf.xml.",
        since="0.0.1",
        cite=_IUC,
        detect_only=True,
        rulesets=frozenset({"strict"}),
        planemo_linters=frozenset({"DatatypesCustomConf"}),
    )

    def detect(self, document: ToolDocument, /) -> Iterable[Violation]:
        source = document.source_path
        if source is None:
            return
        conf = source.parent / "datatypes_conf.xml"
        if conf.exists():
            yield _violation(
                document,
                document.root,
                self.meta,
                "a custom datatypes_conf.xml ships beside this tool; registering "
                "datatypes locally is discouraged in favour of contributing the "
                "datatype to Galaxy",
            )


class ValidDatatypes(CheckRule):
    """GTR098 — ``format``/``ftype``/``ext`` should name a known Galaxy datatype.

    Reimplements planemo ``ValidDatatypes`` against a vendored snapshot of Galaxy's
    built-in datatype registry (``builtin_datatypes``), merged with the tool's own
    ``datatypes_conf.xml`` when present. Runs on the raw tree and skips ``@…@`` macro
    tokens (planemo lints the expanded tree; a token's value is supplied there) — so
    macro-injected formats are unseen, the accepted under-report side of the boundary.
    Detect-only.
    """

    meta: ClassVar[RuleMeta] = RuleMeta(
        code="GTR098",
        summary="format/ftype/ext should name a known Galaxy datatype.",
        since="0.0.1",
        cite=_IUC,
        detect_only=True,
        rulesets=frozenset({"strict"}),
        planemo_linters=frozenset({"ValidDatatypes"}),
    )

    def detect(self, document: ToolDocument, /) -> Iterable[Violation]:
        datatypes = builtin_datatypes()
        source = document.source_path
        if source is not None:
            conf = source.parent / "datatypes_conf.xml"
            if conf.exists():
                datatypes = datatypes | _parse_datatypes(conf.read_bytes())

        input_is_free_pass = _input_is_free_pass(document)
        root = document.root
        for attrib in ("format", "ftype", "ext"):
            for elem in root.iterfind(f".//*[@{attrib}]"):
                tag = elem.tag
                # "format" in <help> denotes markup, not a datatype.
                if not isinstance(tag, str) or tag == "help":
                    continue
                value = elem.get(attrib, "")
                if "@" in value:
                    continue
                formats = value.split(",")
                # A data param accepts exactly one real datatype; auto/input there is
                # invalid (Galaxy reports these as a distinct error).
                if tag == "param" and any(f in ("auto", "input") for f in formats):
                    yield _violation(
                        document,
                        elem,
                        self.meta,
                        "format 'auto' or 'input' is not valid on an input param",
                    )
                    continue
                for fmt in formats:
                    if fmt == "auto" or (input_is_free_pass and fmt == "input"):
                        continue
                    if fmt not in datatypes:
                        yield _violation(
                            document,
                            elem,
                            self.meta,
                            f"datatype '{fmt}' on <{tag}> is not a known Galaxy "
                            "datatype",
                        )
