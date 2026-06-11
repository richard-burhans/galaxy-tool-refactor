"""Tests for the shared ``format`` / ``ftype`` normalization helper.

The helper backs both ``Upgrade24_1`` (the tool tree) and the imported-macro-file
normalization pass; these pin its value-level coercion and the element-level
mutation (including the ``skip_tokens`` guard the macro pass relies on).
"""

from __future__ import annotations

from lxml import etree

from galaxy_tool_codemod.datatype_format import (
    DATATYPE_ATTRIBUTES,
    normalize_datatype_attributes,
    normalize_datatype_value,
)


def test_value_lowercases_and_strips_tokens() -> None:
    assert normalize_datatype_value("BAM") == "bam"
    assert normalize_datatype_value("fa, fasta") == "fa,fasta"
    assert normalize_datatype_value("FASTA,FASTQ") == "fasta,fastq"


def test_value_empty_when_no_real_token() -> None:
    assert normalize_datatype_value("") == ""
    assert normalize_datatype_value("   ") == ""
    assert normalize_datatype_value(",,") == ""


def test_attribute_covers_both_format_and_ftype() -> None:
    assert DATATYPE_ATTRIBUTES == ("format", "ftype")


def test_attributes_changed_and_dropped() -> None:
    el = etree.fromstring('<data format="GTiff" ftype=""/>')
    changed = normalize_datatype_attributes(el)
    assert changed is True
    assert el.get("format") == "gtiff"
    assert "ftype" not in el.attrib  # empty value -> attribute dropped


def test_no_change_returns_false() -> None:
    el = etree.fromstring('<data format="bam"/>')
    assert normalize_datatype_attributes(el) is False
    assert el.get("format") == "bam"


def test_skip_tokens_leaves_placeholders_untouched() -> None:
    el = etree.fromstring('<data format="@FORMAT@"/>')
    # Default (Upgrade24_1 behaviour) would lowercase the placeholder...
    plain = etree.fromstring('<data format="@FORMAT@"/>')
    assert normalize_datatype_attributes(plain) is True
    assert plain.get("format") == "@format@"
    # ...but skip_tokens (the macro pass) leaves it alone.
    assert normalize_datatype_attributes(el, skip_tokens=True) is False
    assert el.get("format") == "@FORMAT@"
