"""Codemod: factor a literal version into @TOOL_VERSION@/@VERSION_SUFFIX@ (opt-in).

GTR094 — the canonical IUC version-tokenization (ledger item A2,
``../../docs/deferred_fix_opportunities.md``): a literal
``version="<base>+galaxy<suffix>"`` whose ``<base>`` equals a package
``<requirement>`` version becomes ``@TOOL_VERSION@+galaxy@VERSION_SUFFIX@``,
the matching requirement versions become ``@TOOL_VERSION@``, and the two
``<token>`` definitions land in the tool's inline ``<macros>`` (created when
absent). Like GTR092 it belongs to **no ruleset** — a multi-element style
restructure, applied only by the dedicated opt-in ``tokenize-version`` surface.

Soundness is **proof by execution**: the mutation is first applied to a copy
and kept only when macro-expanding the tokenized copy reproduces the original
tool's expansion byte-for-byte (modulo the ``<macros>`` block both expansions
clear) — the tokens substitute back to exactly the literals they replaced, so
the post-expansion tool Galaxy sees is unchanged by construction. Fail-closed
preconditions (``tokenization_skip_reason`` — the single decision path the
codemod and the CLI surface share, the GTR092 pattern):

- the ``version`` must be a literal ``<base>+galaxy<suffix>`` (the precondition
  the Phase-3c sizing measured: ``scripts.measure version-tokenization``);
- ``<base>`` must equal at least one package ``<requirement>`` version (else
  there is no @TOOL_VERSION@ to share — the IUC point of the tokens);
- ``@TOOL_VERSION@`` / ``@VERSION_SUFFIX@`` must not already be defined
  (inline or imported);
- ``<macros>`` must not ``<import>`` files when the tool has no source
  directory (the expansion gate could not resolve them — fail closed).

See ``docs/decisions.md`` §43.
"""

from __future__ import annotations

import copy
import re
from typing import TYPE_CHECKING, ClassVar

from galaxy_tool_refactor_rules.meta import RuleMeta
from galaxy_tool_source.macros import expand_from_tree, token_definitions
from lxml import etree

from galaxy_tool_xml_codemod.codemod import CodemodCommand
from galaxy_tool_xml_codemod.codemods._coarse_detect import coarse_detect

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

    from galaxy_tool_xml_codemod.change import Change
    from galaxy_tool_xml_codemod.module import Module

_IUC = "https://galaxy-iuc-standards.readthedocs.io/en/latest/best_practices/tool_xml.html"

# The extraction precondition (shared shape with `scripts.measure
# version-tokenization`'s _GALAXY_SUFFIX): a literal base + the IUC `+galaxy`
# revision suffix. `@` excluded so an already-tokenized version never matches.
GALAXY_SUFFIX_VERSION = re.compile(r"^(?P<base>[^@]+)\+galaxy(?P<suffix>[^@]*)$")

_TOKEN_NAMES = ("@TOOL_VERSION@", "@VERSION_SUFFIX@")


def _package_requirements(root: etree._Element, /) -> list[etree._Element]:
    return [
        requirement
        for requirement in root.findall("requirements/requirement")
        if requirement.get("type") == "package"
    ]


def tokenization_skip_reason(module: Module, /) -> str | None:
    """Why GTR094 would skip *module*, or ``None`` when tokenization applies."""
    root = module.document.root
    version = root.get("version")
    if version is None:
        return "no version= attribute to tokenize"
    match = GALAXY_SUFFIX_VERSION.fullmatch(version)
    if match is None:
        return (
            'version is not a literal "<base>+galaxy<suffix>" (already tokenized, '
            "or not using the IUC suffix convention)"
        )
    base = match["base"]
    if not any(
        requirement.get("version") == base
        for requirement in _package_requirements(root)
    ):
        return (
            f"no package <requirement> pins version {base!r} — the extraction "
            "precondition (the tokens exist to share the tool/package version)"
        )
    macros = root.find("macros")
    if (
        macros is not None
        and macros.find("import") is not None
        and module.document.source_path is None
    ):
        return (
            "<macros> imports files but the tool was parsed from bytes — the "
            "expansion-equality gate cannot resolve imports (fail closed)"
        )
    defined = {definition.name for definition in token_definitions(module.document)}
    clashes = sorted(set(_TOKEN_NAMES) & defined)
    if clashes:
        return f"token(s) already defined: {', '.join(clashes)}"
    return None


def _tokenize(root: etree._Element, *, base: str, suffix: str) -> None:
    """Apply the tokenization to *root* in place (preconditions already held)."""
    root.set("version", "@TOOL_VERSION@+galaxy@VERSION_SUFFIX@")
    for requirement in _package_requirements(root):
        if requirement.get("version") == base:
            requirement.set("version", "@TOOL_VERSION@")
    macros = root.find("macros")
    if macros is None:
        macros = etree.Element("macros")
        root.insert(0, macros)
    for name, value in (("@TOOL_VERSION@", base), ("@VERSION_SUFFIX@", suffix)):
        token = etree.SubElement(macros, "token")
        token.set("name", name)
        token.text = value


def _expansion_bytes(
    root: etree._Element, *, source_dir: Path | None
) -> bytes | None:
    """Canonical bytes of *root*'s macro expansion (macros block dropped), or None."""
    expanded, errors = expand_from_tree(copy.deepcopy(root), source_dir=source_dir)
    if expanded is None or errors:
        return None
    expanded_root = expanded.getroot()
    for macros in expanded_root.findall("macros"):
        expanded_root.remove(macros)
    return bytes(etree.tostring(expanded_root))


def expansion_equality_holds(module: Module, *, base: str, suffix: str) -> bool:
    """The proof-by-execution gate: tokenizing must not change the expansion."""
    source_path = module.document.source_path
    source_dir = source_path.parent if source_path is not None else None
    before = _expansion_bytes(module.document.root, source_dir=source_dir)
    if before is None:
        return False
    trial = copy.deepcopy(module.document.root)
    _tokenize(trial, base=base, suffix=suffix)
    after = _expansion_bytes(trial, source_dir=source_dir)
    return after is not None and after == before


class TokenizeVersion(CodemodCommand):
    """Factor ``version="<base>+galaxy<suffix>"`` into the IUC version tokens."""

    meta: ClassVar[RuleMeta] = RuleMeta(
        code="GTR094",
        summary=(
            'Factor a literal version="<base>+galaxy<suffix>" into '
            "@TOOL_VERSION@/@VERSION_SUFFIX@ tokens shared with the matching "
            "package requirement (opt-in tokenize-version only)."
        ),
        since="0.0.1",
        cite=_IUC,
    )

    def detect(self, module: Module, /) -> Iterator[Change]:
        if tokenization_skip_reason(module) is not None:
            return iter(())
        return coarse_detect(
            self, module, message="version would be tokenized to @TOOL_VERSION@"
        )

    def apply(self, module: Module, /) -> None:
        if tokenization_skip_reason(module) is not None:
            return
        root = module.document.root
        match = GALAXY_SUFFIX_VERSION.fullmatch(root.get("version") or "")
        if match is None:  # defensive: skip_reason already vetted this
            return
        base, suffix = match["base"], match["suffix"]
        if not expansion_equality_holds(module, base=base, suffix=suffix):
            return  # the gate could not prove the no-op — leave untouched
        _tokenize(root, base=base, suffix=suffix)
