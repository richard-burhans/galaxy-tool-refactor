"""Tests for GTR100/GTR101 — the opt-in test-validation bindings."""

from __future__ import annotations

from pathlib import Path

import pytest
from galaxy_tool_source.binding import load_tool

from galaxy_tool_lint.checks.test_validation import (
    TestsAssertionValidation,
    TestsCaseValidation,
)

# A tool whose <test> references a parameter that is not in <inputs>: Galaxy's
# TestsCaseValidation flags it as won't-run on a modern profile.
_BAD_TEST_PARAM = b"""<tool id="t" name="t" version="1.0" profile="24.0">
    <command><![CDATA[echo "$in1"]]></command>
    <inputs>
        <param name="in1" type="data" format="txt"/>
    </inputs>
    <outputs>
        <data name="out1" format="txt"/>
    </outputs>
    <tests>
        <test>
            <param name="not_a_real_param" value="x"/>
            <output name="out1">
                <assert_contents><has_text text="x"/></assert_contents>
            </output>
        </test>
    </tests>
    <help>help</help>
</tool>
"""


def _meta_pairs() -> list[tuple[str, type]]:
    return [("GTR100", TestsAssertionValidation), ("GTR101", TestsCaseValidation)]


def test_meta_shape() -> None:
    for code, rule in _meta_pairs():
        meta = rule.meta
        assert meta.code == code
        assert meta.detect_only is True
        assert meta.rulesets == frozenset({"strict"})
        assert meta.cite  # the overarching-goal contract: advisory rules cite docs
    assert TestsAssertionValidation.meta.planemo_linters == frozenset(
        {"TestsAssertionValidation"}
    )
    assert TestsCaseValidation.meta.planemo_linters == frozenset(
        {"TestsCaseValidation"}
    )


def test_in_memory_document_without_path_yields_nothing() -> None:
    # loading from bytes (no path) -> source_path is None -> the binding cannot
    # resolve macros faithfully, so it skips (mirrors DatatypesCustomConf).
    document = load_tool(_BAD_TEST_PARAM)
    assert document.source_path is None
    assert list(TestsCaseValidation().detect(document)) == []
    assert list(TestsAssertionValidation().detect(document)) == []


def test_extra_absent_yields_nothing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # Simulate the [test-validation] extra being absent: the lazy Galaxy import
    # raises ImportError, so the helper returns [] and the rules are silent.
    import builtins

    real_import = builtins.__import__

    def fake_import(name: str, *args: object, **kwargs: object):  # type: ignore[no-untyped-def]
        if name.startswith("galaxy.tool_util"):
            raise ImportError("simulated: [test-validation] extra not installed")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    path = tmp_path / "tool.xml"
    path.write_bytes(_BAD_TEST_PARAM)
    document = load_tool(path)
    assert list(TestsCaseValidation().detect(document)) == []


def test_case_validation_fires_on_bad_test_param(tmp_path: Path) -> None:
    pytest.importorskip("galaxy.tool_util.lint")
    path = tmp_path / "tool.xml"
    path.write_bytes(_BAD_TEST_PARAM)
    document = load_tool(path)
    violations = list(TestsCaseValidation().detect(document))
    assert violations, "expected GTR101 to flag the invalid test parameters"
    assert all(v.code == "GTR101" for v in violations)
    # Galaxy's own message is surfaced verbatim (faithful binding).
    assert any("failed to validate test parameters" in v.message for v in violations)


def test_clean_tool_has_no_test_validation_findings(tmp_path: Path) -> None:
    pytest.importorskip("galaxy.tool_util.lint")
    clean = _BAD_TEST_PARAM.replace(b'name="not_a_real_param"', b'name="in1"')
    path = tmp_path / "tool.xml"
    path.write_bytes(clean)
    document = load_tool(path)
    assert list(TestsCaseValidation().detect(document)) == []
    assert list(TestsAssertionValidation().detect(document)) == []
