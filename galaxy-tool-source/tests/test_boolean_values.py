"""Tests for boolean-value normalization helpers (schema-boolean attributes)."""

from __future__ import annotations

import pytest

from galaxy_tool_source.boolean_values import (
    BooleanNormalization,
    normalize_boolean_token,
    suggest_boolean_normalizations,
)
from galaxy_tool_source.profiles import available_profiles


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        # XSD-invalid Galaxy-boolean spellings → canonical xs:boolean.
        ("True", "true"),
        ("TRUE", "true"),
        ("False", "false"),
        ("FALSE", "false"),
        ("Yes", "true"),
        ("No", "false"),
        ("On", "true"),
        ("Off", "false"),
        ("yes", "true"),
        ("off", "false"),
        # Already valid xs:boolean → left untouched (no spurious change).
        ("true", None),
        ("false", None),
        ("1", None),
        ("0", None),
        # Not a recognized boolean literal → left for typo/other handling.
        ("maybe", None),
        ("ture", None),  # a typo of "true" — FixTypos territory, not ours
        ("t", None),  # Galaxy's string_as_bool does not treat "t" as truthy
        ("", None),
    ],
)
def test_normalize_boolean_token(value: str, expected: str | None) -> None:
    assert normalize_boolean_token(value) == expected


_NEWEST = available_profiles()[-1]


def test_suggests_boolean_attribute_rewrites() -> None:
    xml = (
        f'<tool id="t" name="t" version="1.0" profile="{_NEWEST}"><inputs>'
        '<param name="a" type="boolean" checked="True"/>'
        '<param name="b" type="data" multiple="Yes"/>'
        "</inputs><outputs/></tool>"
    ).encode()
    suggestions = {
        (n.attribute, n.found, n.suggested)
        for n in suggest_boolean_normalizations(xml, profile=_NEWEST)
    }
    assert ("checked", "True", "true") in suggestions
    assert ("multiple", "Yes", "true") in suggestions


def test_does_not_touch_literal_value_attributes() -> None:
    # `value` on <option> is a literal the tool passes through; lowercasing it
    # would corrupt behaviour, so it must never be suggested.
    xml = (
        f'<tool id="t" name="t" version="1.0" profile="{_NEWEST}"><inputs>'
        '<param name="p" type="select"><option value="True">v</option></param>'
        "</inputs><outputs/></tool>"
    ).encode()
    suggestions = suggest_boolean_normalizations(xml, profile=_NEWEST)
    assert all(n.attribute != "value" for n in suggestions)


def test_already_canonical_yields_nothing() -> None:
    xml = (
        f'<tool id="t" name="t" version="1.0" profile="{_NEWEST}"><inputs>'
        '<param name="a" type="boolean" checked="true"/>'
        "</inputs><outputs/></tool>"
    ).encode()
    assert suggest_boolean_normalizations(xml, profile=_NEWEST) == []


def test_str_helps_diagnostics() -> None:
    norm = BooleanNormalization(
        line=3, element="param", attribute="checked", found="True", suggested="true"
    )
    assert "checked='True'" in str(norm)
    assert "'true'" in str(norm)
