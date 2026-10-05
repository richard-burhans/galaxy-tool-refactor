"""GTR104/105/108/109: the IUC review standards that survived a red-team pass.

Seven rules were proposed. Two were **withdrawn** after an adversarial review, and the
reasons are recorded here because they are the useful part:

* **GTR103** (a flat ``<test>`` param naming a nested input) claimed Galaxy "silently
  tests the tool default". False: from profile 24.2 ``validate_on_load`` is on and
  ``parameters/case.py`` *raises* ``Invalid parameter name found``, which GTR101
  already reports in this same ruleset. The silent-default window is
  ``24.1 < profile < 24.2``, and no such profile exists. The replacement rule
  considered -- a ``<when>`` inside a ``<test>``, which really does drop its params --
  turned out to be **XSD-invalid** and already reported by the validity layer
  (``Element 'when': This element is not expected``). No gap, no rule.
* **GTR107** (SI-style units in ``label``/``help``) was unit-wrong. Under
  IEC 80000-13 ``B`` is byte and ``b`` is bit, so ``GB`` is *already* correct for
  gigabytes and the rule rewrote it to gigabits -- an 8x meaning change -- while being
  unable to distinguish a memory size from a genomic length. It also mangled
  ``TB-Profiler``, ``BP`` (biological process), ``MBP``, ``NF-KB`` and a ``--MB`` flag
  documented in help text.

What remains, with the attacks that shaped each one pinned below: GTR104 (Cheetah in an
``<xml>`` macro -- a real silent bug), GTR105 (``optional`` + ``value``, interpolated
bare), GTR108 (an untokenized version) and GTR109 (``detect_errors``).
"""

from __future__ import annotations

from pathlib import Path

from galaxy_tool_source.binding import load_tool

from galaxy_tool_lint.detect import detect_violations


def _tool(
    *,
    version: str = "@TOOL_VERSION@+galaxy@VERSION_SUFFIX@",
    profile: str = "24.0",
    command: str = "<command><![CDATA[foo --in '$input']]></command>",
    inputs: str = '<inputs><param name="input" type="data" format="txt"/></inputs>',
    tests: str = (
        '<tests><test expect_num_outputs="1"><param name="input" value="x"/>'
        "</test></tests>"
    ),
    macros: str = "",
) -> bytes:
    return (
        f'<tool id="t" name="T" version="{version}" profile="{profile}">'
        f"{macros}<description>Does a thing.</description>"
        "<edam_topics><edam_topic>topic_0091</edam_topic></edam_topics>"
        '<requirements><requirement type="package" version="1.0">foo</requirement>'
        "</requirements>"
        '<stdio><exit_code range="1:" level="fatal"/></stdio>'
        f"{command}{inputs}"
        '<outputs><data name="out" format="txt"/></outputs>'
        f"{tests}<help><![CDATA[Some help text.]]></help>"
        '<citations><citation type="doi">10.1/x</citation></citations></tool>'
    ).encode()


def _codes(tool_bytes: bytes) -> set[str]:
    return {v.code for v in detect_violations(load_tool(tool_bytes))}


def _codes_at(path: Path) -> set[str]:
    return {v.code for v in detect_violations(load_tool(path))}



# --- GTR104: Cheetah inside an <xml> macro -----------------------------------------


def test_gtr104_cheetah_directive_in_an_inline_xml_macro() -> None:
    codes = _codes(
        _tool(
            macros=(
                '<macros><xml name="cutoff_flag">'
                "#if str($cutoff)\n--cutoff $cutoff\n#end if"
                "</xml></macros>"
            )
        )
    )
    assert "GTR104" in codes


def test_gtr104_silent_when_the_macro_wraps_a_command() -> None:
    """``<xml>`` holding a whole ``<command>`` splices the element; the Cheetah runs."""
    codes = _codes(
        _tool(
            macros=(
                '<macros><xml name="whole_command"><command><![CDATA['
                "#if str($cutoff)\n--cutoff $cutoff\n#end if"
                "]]></command></xml></macros>"
            )
        )
    )
    assert "GTR104" not in codes


def test_gtr104_silent_for_a_plain_param_macro() -> None:
    """A ``$`` in an ``<xml>`` macro is ordinary; only a directive is the defect."""
    codes = _codes(
        _tool(
            macros=(
                '<macros><xml name="cutoff_param">'
                '<param name="cutoff" type="integer" value="5" label="Cutoff"/>'
                "</xml></macros>"
            )
        )
    )
    assert "GTR104" not in codes


def test_gtr104_silent_for_a_cheetah_comment() -> None:
    """``##`` is a comment, not a directive."""
    codes = _codes(
        _tool(macros='<macros><xml name="noted">## just a note</xml></macros>')
    )
    assert "GTR104" not in codes


def test_gtr104_reads_an_imported_macros_file(tmp_path: Path) -> None:
    """The <xml> macros of a suite live in macros.xml, so the rule must follow the
    import -- a check that only read the tool would never fire in practice."""
    (tmp_path / "macros.xml").write_text(
        '<macros><xml name="cutoff_flag">'
        "#if str($cutoff)\n--cutoff $cutoff\n#end if"
        "</xml></macros>"
    )
    path = tmp_path / "tool.xml"
    path.write_bytes(_tool(macros="<macros><import>macros.xml</import></macros>"))
    findings = [v for v in detect_violations(load_tool(path)) if v.code == "GTR104"]
    assert len(findings) == 1
    assert "macros.xml" in findings[0].message
    assert "cutoff_flag" in findings[0].message
    # anchored on the tool's own tree, because a foreign tree has no xpath here
    assert findings[0].xpath.startswith("/tool/macros")


# --- GTR105: the input convention -------------------------------


def test_gtr105_optional_with_a_value_default() -> None:
    assert "GTR105" in _codes(
        _tool(
            inputs=(
                '<inputs><param name="input" type="integer" optional="true" '
                'value="5"/></inputs>'
            )
        )
    )


def test_gtr105_silent_for_an_empty_value() -> None:
    """``value=""`` is the conventional spelling of "no default"."""
    assert "GTR105" not in _codes(
        _tool(
            inputs=(
                '<inputs><param name="input" type="text" optional="true" value=""/>'
                "</inputs>"
            )
        )
    )


def test_gtr105_silent_for_an_optional_data_param() -> None:
    """``optional="true"`` on a dataset is the normal idiom, not a contradiction."""
    assert "GTR105" not in _codes(
        _tool(
            inputs=(
                '<inputs><param name="input" type="data" format="txt" '
                'optional="true"/></inputs>'
            )
        )
    )


# --- GTR108 / GTR109: the tool-level conventions -----------------------------------


def test_gtr108_literal_version() -> None:
    codes = _codes(_tool(version="1.0.0"))
    assert "GTR108" in codes
    assert "GTR024" not in codes  # the partition: GTR024 takes the non-PEP-440 half


def test_gtr108_partitions_with_gtr024() -> None:
    """A literal that is not PEP 440 is GTR024's, and only GTR024's."""
    codes = _codes(_tool(version="not a version"))
    assert "GTR024" in codes
    assert "GTR108" not in codes


def test_gtr108_silent_for_a_tokenized_version() -> None:
    assert "GTR108" not in _codes(_tool())


def test_gtr108_names_the_command_when_it_would_work() -> None:
    """A ``<base>+galaxy<suffix>`` literal pinned by a requirement is automatable."""
    tool = _tool(version="1.0+galaxy0")
    findings = [v for v in detect_violations(load_tool(tool)) if v.code == "GTR108"]
    assert len(findings) == 1
    assert "tokenize-version" in findings[0].message


def test_gtr109_detect_errors_not_aggressive() -> None:
    assert "GTR109" in _codes(
        _tool(command='<command detect_errors="exit_code"><![CDATA[foo]]></command>')
    )


def test_gtr109_silent_for_aggressive_and_for_absent() -> None:
    assert "GTR109" not in _codes(
        _tool(command='<command detect_errors="aggressive"><![CDATA[foo]]></command>')
    )
    # absent is GTR026's condition, and this fixture satisfies it with <stdio>
    assert "GTR109" not in _codes(_tool())


# --- regression pins from the red-team pass ----------------------------------------


def test_gtr104_ignores_the_environment_variable_element(tmp_path: Path) -> None:
    """``<environment_variable>`` IS Cheetah-evaluated, so a macro wrapping one is fine.

    The first version of this rule whitelisted ``env_var`` -- a tag that appears
    nowhere in any vendored schema -- and so reported the canonical
    splice-a-single-child macro. The XSD's own documentation for the real element
    reads "The body should be a Cheetah template block that may reference the tool's
    inputs".
    """
    (tmp_path / "macros.xml").write_text(
        '<macros><xml name="env_block">'
        '<environment_variable name="MY_OPT"><![CDATA[\n#if $flag\nyes\n#end if\n]]>'
        "</environment_variable></xml></macros>"
    )
    path = tmp_path / "tool.xml"
    path.write_bytes(_tool(macros="<macros><import>macros.xml</import></macros>"))
    assert "GTR104" not in _codes_at(path)


def test_gtr104_ignores_code_samples_in_help(tmp_path: Path) -> None:
    """``<help>`` is prose, not a template: a shell or Python sample is not a defect."""
    (tmp_path / "macros.xml").write_text(
        '<macros><xml name="help_block"><help><![CDATA[\nExample::\n\n'
        "    #import numpy\n    #for f in *.fastq; do echo $f; done\n"
        "    #include <stdio.h>\n]]></help></xml></macros>"
    )
    path = tmp_path / "tool.xml"
    path.write_bytes(_tool(macros="<macros><import>macros.xml</import></macros>"))
    assert "GTR104" not in _codes_at(path)


def test_gtr104_catches_both_macro_spellings() -> None:
    """``<macro name=...>`` defaults to ``type="xml"``, so it carries the same bug.

    ``galaxy.util.xml_macros._load_embedded_macros`` sets ``type="xml"`` when the
    attribute is absent; ``<xml>`` is only a shortcut. Scanning ``iter("xml")`` alone
    missed both ``<macro name="x">`` and ``<macro name="x" type="xml">``.
    """
    for spelling in ('<macro name="m">', '<macro name="m" type="xml">'):
        closing = "</macro>"
        codes = _codes(
            _tool(
                macros=(
                    f"<macros>{spelling}#if str($cutoff)\n--cutoff $cutoff\n#end if"
                    f"{closing}</macros>"
                )
            )
        )
        assert "GTR104" in codes, spelling


def test_gtr104_still_ignores_a_token() -> None:
    """A ``<token>`` holding Cheetah is the correct construct, not a finding."""
    codes = _codes(
        _tool(
            macros=(
                '<macros><token name="@FLAG@">#if str($cutoff)\n--cutoff $cutoff\n'
                "#end if</token></macros>"
            )
        )
    )
    assert "GTR104" not in codes


def test_gtr105_is_silent_for_the_guarded_idiom() -> None:
    """Pre-fill the CLI's own default, let the user clear it, gate the flag.

    72% of this rule's original corpus findings were this idiom, 34 of those files in
    the ``iuc/`` namespace. Reporting them would have made every one worse.
    """
    codes = _codes(
        _tool(
            command=(
                "<command><![CDATA[prog\n#if $cutoff\n--cutoff $cutoff\n#end if\n"
                "]]></command>"
            ),
            inputs=(
                '<inputs><param name="cutoff" type="integer" value="80" '
                'optional="true"/></inputs>'
            ),
        )
    )
    assert "GTR105" not in codes


def test_gtr105_fires_when_interpolated_bare() -> None:
    codes = _codes(
        _tool(
            command="<command><![CDATA[prog --cutoff $cutoff]]></command>",
            inputs=(
                '<inputs><param name="cutoff" type="integer" value="80" '
                'optional="true"/></inputs>'
            ),
        )
    )
    assert "GTR105" in codes


def test_gtr105_leaves_a_never_referenced_param_to_gtr034() -> None:
    """An unreferenced param is an orphan, which is GTR034's finding, not this one."""
    codes = _codes(
        _tool(
            command="<command><![CDATA[prog]]></command>",
            inputs=(
                '<inputs><param name="cutoff" type="integer" value="80" '
                'optional="true"/></inputs>'
            ),
        )
    )
    assert "GTR105" not in codes


def test_gtr108_advises_adopt_suffix_for_a_bare_version() -> None:
    """A plain literal has no ``+galaxy`` suffix, so the command differs.

    Passing ``tokenization_skip_reason`` through told 92% of real findings their
    literal version might be "already tokenized" -- unreachable here by construction,
    since the rule only fires when the version contains no ``@``.
    """
    findings = [
        v
        for v in detect_violations(load_tool(_tool(version="1.0.0")))
        if v.code == "GTR108"
    ]
    assert len(findings) == 1
    assert "--adopt-suffix" in findings[0].message
    assert "already tokenized" not in findings[0].message


def test_gtr109_reports_an_illegal_value_as_a_load_failure() -> None:
    """``Aggressive`` is what someone *intending* aggressive types, and it is fatal.

    Galaxy raises ``Unknown detect_errors value encountered``; reporting it as a
    preference between two working modes was actively misleading.
    """
    findings = [
        v
        for v in detect_violations(
            load_tool(
                _tool(
                    command=(
                        '<command detect_errors="Aggressive"><![CDATA[foo]]></command>'
                    )
                )
            )
        )
        if v.code == "GTR109"
    ]
    assert len(findings) == 1
    assert "will not load" in findings[0].message


def test_gtr109_default_without_a_profile_adds_nothing() -> None:
    """Measured against Galaxy's ``parse_stdio()``: 0 exit codes, 0 regexes."""
    tool = _tool(
        command='<command detect_errors="default"><![CDATA[foo]]></command>'
    ).replace(b' profile="24.0"', b"", 1)
    findings = [
        v for v in detect_violations(load_tool(tool)) if v.code == "GTR109"
    ]
    assert len(findings) == 1
    assert "adds NOTHING" in findings[0].message


def test_gtr109_skips_a_tool_with_its_own_stderr_regex() -> None:
    """Galaxy prepends ``<stdio>`` regexes; the author's patterns beat aggressive's."""
    tool = _tool(
        command='<command detect_errors="exit_code"><![CDATA[foo]]></command>'
    ).replace(
        b'<stdio><exit_code range="1:" level="fatal"/></stdio>',
        b'<stdio><exit_code range="1:" level="fatal"/>'
        b'<regex source="stderr" match="\\[ERROR\\]" level="fatal"/></stdio>',
        1,
    )
    assert "GTR109" not in _codes(tool)
