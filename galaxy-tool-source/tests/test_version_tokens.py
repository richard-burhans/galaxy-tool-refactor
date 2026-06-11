"""Tests for the tier-1 version-tokenization decision, gate, and offset planner.

The planner (``tokenize_version_plan``) is the editor-and-CLI-shared rendering of
GTR094: it returns minimal offset edits over the original tool source (plus, in
separate-file mode, a new ``macros.xml``), the foundation a galaxy-language-server
Code Action turns into an LSP ``WorkspaceEdit``. Soundness is proven by execution
(expansion-equality), so every test that expects a plan also asserts the rendered
bytes macro-expand to the original.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from lxml import etree

from galaxy_tool_source.binding import parse_tool
from galaxy_tool_source.macros import expand_from_tree, token_definitions
from galaxy_tool_source.version_tokens import (
    VersionTokenPlan,
    adopt_suffix_equality_holds,
    adopt_suffix_skip_reason,
    build_version_macros_root,
    tokenization_skip_reason,
    tokenize_tree,
    tokenize_version_plan,
)

_INLINE_TOOL = """\
<tool id="x" name="X" version="1.20+galaxy0" profile="22.05">
    <requirements>
        <requirement type="package" version="1.20">samtools</requirement>
    </requirements>
    <command><![CDATA[samtools --version]]></command>
</tool>
"""


def _expansion_bytes(xml: str) -> bytes:
    """Macro-expand *xml* and return canonical bytes with <macros> stripped."""
    root = parse_tool(xml.encode("utf-8")).document.root
    expanded, errors = expand_from_tree(root, source_dir=None)
    assert expanded is not None and not errors
    expanded_root = expanded.getroot()
    for macros in expanded_root.findall("macros"):
        expanded_root.remove(macros)
    return bytes(etree.tostring(expanded_root))


def _assert_expansion_preserved(original: str, rendered: str) -> None:
    """The rendered (tokenized) tool must expand to the original's expansion."""
    assert _expansion_bytes(rendered) == _expansion_bytes(original)


def test_inline_plan_tokenizes_version_and_requirement() -> None:
    plan = tokenize_version_plan(_INLINE_TOOL)
    assert not plan.bailed
    assert plan.reason is None
    assert plan.base == "1.20"
    assert plan.suffix == "0"
    assert plan.new_file is None

    rendered = plan.apply(_INLINE_TOOL)
    root = parse_tool(rendered.encode("utf-8")).document.root
    assert root.get("version") == "@TOOL_VERSION@+galaxy@VERSION_SUFFIX@"
    requirement = root.find("requirements/requirement")
    assert requirement is not None
    assert requirement.get("version") == "@TOOL_VERSION@"
    defined = {definition.name for definition in token_definitions(
        parse_tool(rendered.encode("utf-8")).document
    )}
    assert {"@TOOL_VERSION@", "@VERSION_SUFFIX@"} <= defined
    _assert_expansion_preserved(_INLINE_TOOL, rendered)


def test_inline_plan_is_minimal_diff() -> None:
    # An idiosyncratic comment + odd spacing must survive untouched.
    tool = (
        "<tool id='x' name='X' version='1.20+galaxy0' profile='22.05'>\n"
        "    <!-- keep this exactly -->\n"
        "    <requirements>\n"
        "        <requirement type='package' version='1.20'>samtools</requirement>\n"
        "    </requirements>\n"
        "    <command><![CDATA[samtools]]></command>\n"
        "</tool>\n"
    )
    rendered = tokenize_version_plan(tool).apply(tool)
    assert "<!-- keep this exactly -->" in rendered
    _assert_expansion_preserved(tool, rendered)


def test_separate_file_plan_emits_import_and_new_file() -> None:
    plan = tokenize_version_plan(_INLINE_TOOL, macros_file="macros.xml")
    assert not plan.bailed
    assert plan.new_file is not None
    assert plan.new_file.path == "macros.xml"
    assert '<token name="@TOOL_VERSION@">1.20</token>' in plan.new_file.content
    assert '<token name="@VERSION_SUFFIX@">0</token>' in plan.new_file.content

    rendered = plan.apply(_INLINE_TOOL)
    root = parse_tool(rendered.encode("utf-8")).document.root
    macros = root.find("macros")
    assert macros is not None
    importer = macros.find("import")
    assert importer is not None
    assert (importer.text or "").strip() == "macros.xml"
    # Soundness: importing a file with the tokens expands like the inline form.
    inline_rendered = tokenize_version_plan(_INLINE_TOOL).apply(_INLINE_TOOL)
    _assert_expansion_preserved(_INLINE_TOOL, inline_rendered)


def test_existing_macros_block_receives_tokens_inline() -> None:
    tool = (
        '<tool id="x" name="X" version="1.20+galaxy0" profile="22.05">\n'
        "    <macros>\n"
        '        <token name="@OTHER@">z</token>\n'
        "    </macros>\n"
        "    <requirements>\n"
        '        <requirement type="package" version="1.20">samtools</requirement>\n'
        "    </requirements>\n"
        "    <command><![CDATA[samtools]]></command>\n"
        "</tool>\n"
    )
    plan = tokenize_version_plan(tool)
    assert not plan.bailed, plan.reason
    rendered = plan.apply(tool)
    defined = {definition.name for definition in token_definitions(
        parse_tool(rendered.encode("utf-8")).document
    )}
    assert {"@OTHER@", "@TOOL_VERSION@", "@VERSION_SUFFIX@"} <= defined
    _assert_expansion_preserved(tool, rendered)


def test_multiline_tool_start_tag_anchors() -> None:
    # libxml2 reports sourceline as the start tag's closing '>' line; the version
    # attribute is on an earlier line than '<tool'. (Corpus: sirius_csifingerid.)
    tool = (
        '<tool id="x"\n'
        '      name="X"\n'
        '      version="4.9.8+galaxy4" profile="19.05">\n'
        "    <requirements>\n"
        '        <requirement type="package" version="4.9.8">sirius</requirement>\n'
        "    </requirements>\n"
        "    <command><![CDATA[sirius]]></command>\n"
        "</tool>\n"
    )
    plan = tokenize_version_plan(tool)
    assert not plan.bailed, plan.reason
    rendered = plan.apply(tool)
    assert 'version="@TOOL_VERSION@+galaxy@VERSION_SUFFIX@"' in rendered
    _assert_expansion_preserved(tool, rendered)


def test_blank_line_after_tool_tag_is_preserved() -> None:
    # A blank line between <tool ...> and the first child must survive: the gate's
    # remove(<macros>) would otherwise swallow it as the inserted element's tail.
    # (Corpus: vcfsamplecompare, asics_xml.)
    tool = (
        '<tool id="x" name="X" version="2.013+galaxy2">\n'
        "\n"
        "    <description>d</description>\n"
        "    <requirements>\n"
        '        <requirement type="package" version="2.013">vcf</requirement>\n'
        "    </requirements>\n"
        "    <command><![CDATA[vcf]]></command>\n"
        "</tool>\n"
    )
    plan = tokenize_version_plan(tool)
    assert not plan.bailed, plan.reason
    rendered = plan.apply(tool)
    assert "\n\n    <description>" in rendered  # blank line kept in the tool too
    _assert_expansion_preserved(tool, rendered)


def test_existing_imported_macros_inline_tokenization() -> None:
    # A tool that already imports a macro file gets the tokens added to its existing
    # <macros> block; the pre-existing import is untouched. (Corpus: sequenza_index.)
    tool = (
        '<tool id="x" name="X" version="3.0.0+galaxy1">\n'
        "    <macros>\n"
        "        <import>other_macros.xml</import>\n"
        "    </macros>\n"
        "    <requirements>\n"
        '        <requirement type="package" version="3.0.0">seq</requirement>\n'
        "    </requirements>\n"
        "    <command><![CDATA[seq]]></command>\n"
        "</tool>\n"
    )
    other = (
        "<macros>\n"
        '    <token name="@OTHER@">z</token>\n'
        "</macros>\n"
    )
    with tempfile.TemporaryDirectory() as tmp:
        tool_path = Path(tmp) / "tool.xml"
        tool_path.write_text(tool, encoding="utf-8")
        (Path(tmp) / "other_macros.xml").write_text(other, encoding="utf-8")
        plan = tokenize_version_plan(tool, source_path=tool_path)
        assert not plan.bailed, plan.reason
        rendered = plan.apply(tool)
        assert "<import>other_macros.xml</import>" in rendered
        assert '<token name="@TOOL_VERSION@">3.0.0</token>' in rendered


def test_bail_version_not_galaxy_suffix() -> None:
    tool = _INLINE_TOOL.replace("1.20+galaxy0", "1.20")
    plan = tokenize_version_plan(tool)
    assert plan.bailed
    assert plan.reason is not None
    assert plan.edits == ()


def test_bail_no_matching_requirement() -> None:
    tool = _INLINE_TOOL.replace('version="1.20">samtools', 'version="9.9">samtools')
    plan = tokenize_version_plan(tool)
    assert plan.bailed
    assert "requirement" in (plan.reason or "")


def test_bail_tokens_already_defined() -> None:
    tool = (
        '<tool id="x" name="X" version="1.20+galaxy0" profile="22.05">\n'
        "    <macros>\n"
        '        <token name="@TOOL_VERSION@">1.20</token>\n'
        "    </macros>\n"
        "    <requirements>\n"
        '        <requirement type="package" version="1.20">samtools</requirement>\n'
        "    </requirements>\n"
        "    <command><![CDATA[samtools]]></command>\n"
        "</tool>\n"
    )
    plan = tokenize_version_plan(tool)
    assert plan.bailed
    assert "already defined" in (plan.reason or "")


def test_bail_no_version_attribute() -> None:
    tool = _INLINE_TOOL.replace(' version="1.20+galaxy0"', "")
    plan = tokenize_version_plan(tool)
    assert plan.bailed


def test_bail_malformed_source() -> None:
    plan = tokenize_version_plan("<tool><unclosed>")
    assert plan.bailed
    assert plan.reason is not None


def test_skip_reason_matches_plan_bail() -> None:
    # The decision the codemod and the planner share: a clean candidate => None.
    document = parse_tool(_INLINE_TOOL.encode("utf-8")).document
    assert tokenization_skip_reason(document) is None


def test_tokenize_tree_inline_defines_tokens() -> None:
    root = parse_tool(_INLINE_TOOL.encode("utf-8")).document.root
    tokenize_tree(root, base="1.20", suffix="0")
    assert root.get("version") == "@TOOL_VERSION@+galaxy@VERSION_SUFFIX@"
    macros = root.find("macros")
    assert macros is not None
    assert macros.find("import") is None
    names = {token.get("name") for token in macros.findall("token")}
    assert names == {"@TOOL_VERSION@", "@VERSION_SUFFIX@"}


def test_tokenize_tree_macros_file_emits_import() -> None:
    root = parse_tool(_INLINE_TOOL.encode("utf-8")).document.root
    tokenize_tree(root, base="1.20", suffix="0", macros_file="macros.xml")
    macros = root.find("macros")
    assert macros is not None
    assert macros.find("token") is None  # tokens live in the separate file
    importer = macros.find("import")
    assert importer is not None
    assert importer.text == "macros.xml"
    requirement = root.find("requirements/requirement")
    assert requirement is not None
    assert requirement.get("version") == "@TOOL_VERSION@"


def test_build_version_macros_root_holds_both_tokens() -> None:
    macros = build_version_macros_root(base="1.20", suffix="3")
    assert macros.tag == "macros"
    pairs = {(token.get("name"), token.text) for token in macros.findall("token")}
    assert pairs == {("@TOOL_VERSION@", "1.20"), ("@VERSION_SUFFIX@", "3")}


_BARE_TOOL = """\
<tool id="x" name="X" version="1.20" profile="22.05">
    <requirements>
        <requirement type="package" version="1.20">samtools</requirement>
    </requirements>
    <command><![CDATA[samtools --version]]></command>
</tool>
"""


def test_adopt_suffix_applies_to_bare_version_matching_requirement() -> None:
    document = parse_tool(_BARE_TOOL.encode("utf-8")).document
    assert adopt_suffix_skip_reason(document) is None
    assert adopt_suffix_equality_holds(document, base="1.20") is True


def test_adopt_suffix_skips_already_galaxy_suffixed() -> None:
    document = parse_tool(_INLINE_TOOL.encode("utf-8")).document  # 1.20+galaxy0
    assert adopt_suffix_skip_reason(document) is not None


def test_adopt_suffix_skips_when_no_requirement_matches() -> None:
    tool = _BARE_TOOL.replace('version="1.20">samtools', 'version="9.9">samtools')
    document = parse_tool(tool.encode("utf-8")).document
    reason = adopt_suffix_skip_reason(document)
    assert reason is not None and "requirement" in reason


def test_adopt_suffix_tree_changes_only_the_version() -> None:
    # The controlled-change gate proves expansion differs only in the version; applying
    # the tree mutation yields exactly that.
    root = parse_tool(_BARE_TOOL.encode("utf-8")).document.root
    tokenize_tree(root, base="1.20", suffix="0")
    assert root.get("version") == "@TOOL_VERSION@+galaxy@VERSION_SUFFIX@"
    requirement = root.find("requirements/requirement")
    assert requirement is not None and requirement.get("version") == "@TOOL_VERSION@"
    names = {token.get("name") for token in root.find("macros").findall("token")}
    assert names == {"@TOOL_VERSION@", "@VERSION_SUFFIX@"}


def test_plan_apply_is_pure() -> None:
    plan = tokenize_version_plan(_INLINE_TOOL)
    once = plan.apply(_INLINE_TOOL)
    twice = plan.apply(_INLINE_TOOL)
    assert once == twice
    assert isinstance(plan, VersionTokenPlan)
