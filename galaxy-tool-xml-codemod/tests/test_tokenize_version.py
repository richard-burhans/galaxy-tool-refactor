"""Tests for ``TokenizeVersion`` (GTR094, opt-in tokenize-version only)."""

from __future__ import annotations

from lxml import etree

from galaxy_tool_xml_codemod.codemods.tokenize_version import (
    TokenizeVersion,
    tokenization_skip_reason,
)
from galaxy_tool_xml_codemod.parse import parse_module


def _tool(
    *,
    version: str = "1.20+galaxy0",
    requirement: str = (
        '<requirement type="package" version="1.20">samtools</requirement>'
    ),
    macros: str = "",
) -> bytes:
    return (
        f'<tool id="m" name="M" version="{version}" profile="24.0">'
        f"{macros}"
        "<command><![CDATA[echo x]]></command>"
        f"<requirements>{requirement}</requirements>"
        '<inputs><param name="i" type="text"/></inputs>'
        '<outputs><data name="o"/></outputs></tool>'
    ).encode()


def test_clean_candidate_tokenizes_version_and_requirement() -> None:
    module = parse_module(_tool())
    assert tokenization_skip_reason(module) is None
    changes = list(TokenizeVersion().detect(module))
    assert len(changes) == 1 and changes[0].code == "GTR094"
    TokenizeVersion().apply(module)
    root = module.document.root
    assert root.get("version") == "@TOOL_VERSION@+galaxy@VERSION_SUFFIX@"
    requirement = root.find(".//requirement")
    assert requirement.get("version") == "@TOOL_VERSION@"
    tokens = {t.get("name"): t.text for t in root.findall("macros/token")}
    assert tokens == {"@TOOL_VERSION@": "1.20", "@VERSION_SUFFIX@": "0"}


def test_existing_inline_macros_block_is_reused() -> None:
    module = parse_module(
        _tool(macros='<macros><token name="@X@">y</token></macros>')
    )
    TokenizeVersion().apply(module)
    root = module.document.root
    assert len(root.findall("macros")) == 1
    names = {t.get("name") for t in root.findall("macros/token")}
    assert names == {"@X@", "@TOOL_VERSION@", "@VERSION_SUFFIX@"}


def test_skips_when_base_matches_no_requirement() -> None:
    module = parse_module(
        _tool(requirement='<requirement type="package" version="9.9">x</requirement>')
    )
    reason = tokenization_skip_reason(module)
    assert reason is not None and "requirement" in reason
    assert list(TokenizeVersion().detect(module)) == []


def test_skips_already_tokenized_and_non_suffix_versions() -> None:
    assert tokenization_skip_reason(
        parse_module(_tool(version="@TOOL_VERSION@+galaxy0"))
    ) is not None
    assert tokenization_skip_reason(parse_module(_tool(version="1.20"))) is not None


def test_skips_when_token_already_defined() -> None:
    module = parse_module(
        _tool(macros='<macros><token name="@TOOL_VERSION@">1.20</token></macros>')
    )
    reason = tokenization_skip_reason(module)
    assert reason is not None and "@TOOL_VERSION@" in reason


def test_skips_when_macros_import_files() -> None:
    # v1 scope: the expansion-equality gate needs resolvable macros; an
    # <import> on a bytes-parsed tool has no source dir — fail closed.
    module = parse_module(
        _tool(macros="<macros><import>shared.xml</import></macros>")
    )
    assert tokenization_skip_reason(module) is not None


def test_expansion_equality_holds() -> None:
    # The gate's own invariant, asserted directly: expanding the tokenized tool
    # reproduces the original expansion (modulo the cleared <macros> block).
    from galaxy_tool_source.macros import expand_from_tree

    module = parse_module(_tool())
    before, errors = expand_from_tree(module.document.root, source_dir=None)
    assert before is not None and not errors
    TokenizeVersion().apply(module)
    after, errors = expand_from_tree(module.document.root, source_dir=None)
    assert after is not None and not errors
    for tree in (before, after):
        for macros in tree.getroot().findall("macros"):
            macros.getparent().remove(macros)
    assert tree_bytes(before) == tree_bytes(after)


def tree_bytes(tree: etree._ElementTree) -> bytes:
    return etree.tostring(tree.getroot())


def test_is_idempotent() -> None:
    module = parse_module(_tool())
    TokenizeVersion().apply(module)
    once = etree.tostring(module.document.root)
    TokenizeVersion().apply(module)  # now already tokenized -> skip
    assert etree.tostring(module.document.root) == once


def test_meta() -> None:
    assert TokenizeVersion.meta.code == "GTR094"
    assert TokenizeVersion.meta.rulesets == frozenset()
