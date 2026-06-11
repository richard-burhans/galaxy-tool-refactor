"""Shared-macros version tokenization: create / merge / consensus, proof-gated.

The ``--macros-file`` mode of ``tokenize-version`` puts the IUC version tokens in a
macros file the tool ``<import>``s, instead of an inline ``<macros>`` block. When that
file is shared by several tools, this module decides whether the change is sound *for
every tool that touches the file* and, if so, plans all the edits at once:

- **create**: the named file does not exist: create it with the two tokens and add the
  ``<import>`` to the tool.
- **merge**: the file exists and a tool imports it: add the tokens to it, but only when
  doing so is proven *inert* for every other importer (their macro expansion is
  byte-identical before and after).
- **consensus**: several target tools in the directory share the file at the *same*
  ``version="<base>+galaxy<suffix>"``: tokenize all of them and define the shared tokens
  once. A divergent version among the eligible targets is declined.

Soundness is **proof by execution** (the project-wide discipline): every retargeted tool
must still macro-expand to its original bytes, and the token addition must not change
any other importer's expansion. This holds *by construction* for a novel tool suite,
so the feature is built for the construction, not the corpus frequency (tiny today;
see ``scripts.measure version-token-sharing``). fmt remains the only serializer.
"""

from __future__ import annotations

import copy
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path

from galaxy_tool_fmt.format import format_macro_document, format_tool_document
from galaxy_tool_source import version_tokens
from galaxy_tool_source.binding import ToolXmlSyntaxError, load_macros, parse_tool
from galaxy_tool_source.document import MacroDocument, ToolDocument
from galaxy_tool_source.macros import expand_from_path, imported_macro_paths
from lxml import etree

_TOKEN_NAMES = ("@TOOL_VERSION@", "@VERSION_SUFFIX@")


@dataclass(frozen=True)
class SharedToolEdit:
    """One tool to rewrite as part of a shared tokenization."""

    path: Path
    content: bytes


@dataclass(frozen=True)
class SharedTokenizePlan:
    """The planned edits for tokenizing into a (possibly shared) macros file.

    When ``skip_reason`` is set the whole group is declined and nothing is applied.
    Otherwise apply ``macros_content`` to ``macros_path`` (when not ``None``) and each
    ``SharedToolEdit``; ``skipped`` lists the target tools that are individually not
    eligible (already tokenized, no matching requirement, etc.).
    """

    macros_path: Path
    macros_content: bytes | None
    macros_created: bool
    tool_edits: tuple[SharedToolEdit, ...]
    skipped: tuple[tuple[Path, str], ...]
    base: str | None
    suffix: str | None
    skip_reason: str | None


def _bail(macros_path: Path, reason: str) -> SharedTokenizePlan:
    return SharedTokenizePlan(
        macros_path=macros_path,
        macros_content=None,
        macros_created=False,
        tool_edits=(),
        skipped=(),
        base=None,
        suffix=None,
        skip_reason=reason,
    )


def _version_base_suffix(document: ToolDocument) -> tuple[str, str] | None:
    """The ``(base, suffix)`` of a tokenizable tool, or ``None``."""
    match = version_tokens.GALAXY_SUFFIX_VERSION.fullmatch(
        document.root.get("version") or ""
    )
    if match is None:
        return None
    base = match["base"]
    if not any(
        requirement.get("version") == base
        for requirement in version_tokens.package_requirements(document.root)
    ):
        return None
    return base, match["suffix"]


def _expanded_bytes(path: Path) -> bytes | None:
    """A tool's macro expansion with ``<macros>`` stripped, or ``None`` on failure."""
    tree, errors = expand_from_path(path)
    if tree is None or errors:
        return None
    root = tree.getroot()
    for macros in root.findall("macros"):
        root.remove(macros)
    return bytes(etree.tostring(root))


def _expand_with_overrides(
    src_dir: Path, overrides: dict[str, bytes], target_name: str
) -> bytes | None:
    """Expand *target_name* in a temp copy of *src_dir* with files overridden.

    Copies the directory's ``*.xml`` into a temp dir (so the target's imports resolve),
    overwrites the named files with *overrides*, and returns the target's stripped
    expansion. ``None`` if expansion fails (the import does not resolve, etc.), which
    the caller treats as "cannot prove" and declines.
    """
    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        for entry in src_dir.iterdir():
            if entry.is_file() and entry.suffix == ".xml":
                shutil.copy2(entry, tmp_dir / entry.name)
        for name, content in overrides.items():
            (tmp_dir / name).write_bytes(content)
        return _expanded_bytes(tmp_dir / target_name)


def _load_macros_root(macros_path: Path) -> etree._Element | None:
    """The ``<macros>`` root of *macros_path*, or ``None`` if malformed / not macros."""
    # Boundary: load_macros raises on a malformed file and has no lenient form; a bad
    # macros file simply declines the merge (the import would not expand either).
    try:
        document = load_macros(macros_path)
    except ToolXmlSyntaxError:
        return None
    return document.root if document.root.tag == "macros" else None


def _macros_state(
    macros_path: Path, *, base: str, suffix: str
) -> tuple[str | None, bytes | None, bool]:
    """Plan ``macros_path``: ``(decline_reason, content_to_write, created)``.

    ``content_to_write`` is ``None`` with no reason when the file already defines the
    tokens at the consensus values (no rewrite needed).
    """
    name = macros_path.name
    if not macros_path.exists():
        root = version_tokens.build_version_macros_root(base=base, suffix=suffix)
        content = format_macro_document(MacroDocument(etree.ElementTree(root)))
        return None, content, True
    root = _load_macros_root(macros_path)
    if root is None:
        return f"{name} exists but is not a well-formed <macros> file", None, False
    defined = {
        token.get("name"): (token.text or "").strip()
        for token in root.findall("token")
        if token.get("name") in _TOKEN_NAMES
    }
    for token_name, want in zip(_TOKEN_NAMES, (base, suffix), strict=True):
        if token_name in defined and defined[token_name] != want:
            return (
                f"{name} already defines {token_name} as {defined[token_name]!r}, "
                f"not {want!r}",
                None,
                False,
            )
    if len(defined) == len(_TOKEN_NAMES):
        return None, None, False  # both already defined at the consensus values
    if defined:
        return f"{name} defines only one of the version tokens", None, False
    merged = copy.deepcopy(root)
    version_tokens.append_version_tokens(merged, base=base, suffix=suffix)
    content = format_macro_document(MacroDocument(etree.ElementTree(merged)))
    return None, content, False


def _retarget_tool(
    document: ToolDocument, macros_path: Path, name: str, *, base: str, suffix: str
) -> bytes:
    """A retargeted copy of *document* as fmt bytes (imports *name* if it does not)."""
    trial = ToolDocument(etree.ElementTree(copy.deepcopy(document.root)))
    if macros_path in {p.resolve() for p in imported_macro_paths(document)}:
        version_tokens.retarget_version(trial.root, base=base)
    else:
        version_tokens.tokenize_tree(
            trial.root, base=base, suffix=suffix, macros_file=name
        )
    return format_tool_document(trial)


def _other_importers(macros_path: Path, exclude: set[Path]) -> list[Path]:
    """Every tool in ``macros_path``'s directory that imports it, minus *exclude*."""
    importers: list[Path] = []
    for candidate in sorted(macros_path.parent.glob("*.xml")):
        if candidate.resolve() in exclude or candidate == macros_path:
            continue
        result = parse_tool(candidate)
        if result.document is None or result.document.root.tag != "tool":
            continue
        if macros_path in {p.resolve() for p in imported_macro_paths(candidate)}:
            importers.append(candidate)
    return importers


def plan_shared_tokenization(
    macros_path: Path, /, *, target_tools: list[Path]
) -> SharedTokenizePlan:
    """Plan tokenizing *target_tools* into the (possibly shared) ``macros_path``.

    See the module docstring for the create / merge / consensus modes and the
    proof-by-execution soundness gate.
    """
    macros_path = macros_path.resolve()
    name = macros_path.name
    src_dir = macros_path.parent

    # 1. Classify each target: eligible tools must share one (base, suffix).
    eligible: list[tuple[Path, ToolDocument]] = []
    skipped: list[tuple[Path, str]] = []
    versions: set[tuple[str, str]] = set()
    for tool_path in target_tools:
        document = parse_tool(tool_path).document
        if document is None or document.root.tag != "tool":
            skipped.append((tool_path, "not a tool document"))
            continue
        reason = version_tokens.tokenization_skip_reason(document)
        version = _version_base_suffix(document)
        if reason is not None or version is None:
            skipped.append((tool_path, reason or "version is not tokenizable"))
            continue
        eligible.append((tool_path.resolve(), document))
        versions.add(version)

    if not eligible:
        return SharedTokenizePlan(
            macros_path=macros_path,
            macros_content=None,
            macros_created=False,
            tool_edits=(),
            skipped=tuple(skipped),
            base=None,
            suffix=None,
            skip_reason="no target tool is eligible for tokenization",
        )
    if len(versions) != 1:
        listed = ", ".join(sorted(f"{b}+galaxy{s}" for b, s in versions))
        return _bail(
            macros_path,
            f"eligible tools disagree on version ({listed}); one shared token pair "
            "cannot serve them",
        )
    base, suffix = next(iter(versions))

    # 2. Resolve the macros file's content (create / merge / already-defined / decline).
    reason, macros_content, created = _macros_state(
        macros_path, base=base, suffix=suffix
    )
    if reason is not None:
        return _bail(macros_path, reason)
    if macros_content is not None:
        modified_macros = macros_content
    elif macros_path.exists():
        modified_macros = macros_path.read_bytes()  # already defines them; unchanged
    else:  # pragma: no cover (create always yields content)
        return _bail(macros_path, "could not determine the macros file content")

    # 3. Build + soundness-check each eligible tool's retargeted bytes. The tier-1 gate
    #    proves the tokenization a no-op on the inline form; importing a file that
    #    defines the same tokens is equivalent to inline by construction (Galaxy macro
    #    semantics), so it covers the separate-file rendering too.
    eligible_paths = {tool_path for tool_path, _document in eligible}
    tool_edits: list[SharedToolEdit] = []
    for tool_path, document in eligible:
        if not version_tokens.expansion_equality_holds(
            document, base=base, suffix=suffix
        ):
            return _bail(
                macros_path,
                f"tokenizing {tool_path.name} would change its macro expansion "
                "(could not prove the no-op)",
            )
        retargeted = _retarget_tool(
            document, macros_path, name, base=base, suffix=suffix
        )
        tool_edits.append(SharedToolEdit(path=tool_path, content=retargeted))

    # 4. A merge into an existing shared file must be inert for every other importer.
    if macros_content is not None and not created:
        for importer in _other_importers(macros_path, exclude=eligible_paths):
            before = _expanded_bytes(importer)
            after = _expand_with_overrides(
                src_dir, {name: modified_macros}, importer.name
            )
            if before is None or after is None or before != after:
                return _bail(
                    macros_path,
                    f"adding the tokens to {name} would change the expansion of "
                    f"{importer.name} (which also imports it)",
                )

    return SharedTokenizePlan(
        macros_path=macros_path,
        macros_content=macros_content,
        macros_created=created,
        tool_edits=tuple(tool_edits),
        skipped=tuple(skipped),
        base=base,
        suffix=suffix,
        skip_reason=None,
    )
