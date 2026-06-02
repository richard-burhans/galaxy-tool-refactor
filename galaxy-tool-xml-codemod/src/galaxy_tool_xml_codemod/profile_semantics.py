"""Galaxy's tool-profile upgrade codes — the changes a profile bump opts a tool into.

A profile upgrade is **structurally** sound but **not** behaviour-preserving
(codemod ``docs/decisions.md`` §22): Galaxy's ``profile`` is a runtime-compatibility
contract, so bumps change runtime defaults (error detection, ``set -e``, optional
templating, …) the XSD cannot see.

``PROFILE_UPGRADE_CODES`` is a **faithful mirror of Galaxy's own catalogue**,
``lib/galaxy/tool_util/upgrade/upgrade_codes.json`` (galaxyproject/galaxy @
``b45c58a2``, vendored 2026-06-01) — the authoritative source of truth, keyed by
Galaxy's code names. We mirror the ``must_fix`` and ``consider`` codes (the changes
a bump introduces); Galaxy's single ``ready`` note (``16_04_ready_interpreter`` — a
"you're fine" message, not a change) is omitted. (Re-verified 2026-06-01 against
``dev`` @ ``c6e0ee3``: the catalogue is unchanged — our 17 codes == that file's 18
minus the omitted ``ready`` note — and the three buggy detectors below still
exhibit their documented faults.)

**Two profile behaviour changes the Galaxy schema docs describe are intentionally
absent**, because Galaxy's ``upgrade_codes.json`` does not catalogue them: the
**19.05** default Python 2→3 interpreter change and the **25.1** ``<credentials>``
migration. Keeping this map a strict mirror of the authoritative catalogue is the
deliberate choice (see ``../../docs/profile_upgrades.md``); add them only if Galaxy
adds upgrade codes for them.

``upgrade_codes_crossed`` answers "which of these does a baseline→target bump
*cross*" (range-based: every code whose profile lies in the bumped range).
``upgrade_codes_applicable`` narrows that to the codes that actually *apply* to a
given tool, by running a per-code detector — a port of Galaxy's own advisor
(``lib/galaxy/tool_util/upgrade/__init__.py`` @ ``b45c58a2``). The ``upgrade``
path warns on the *applicable* set, so a tool that trips none stays quiet.

**We port Galaxy's documented intent, not its literal b45c58a2 code**, which has
several transcription bugs that make some predicates non-functional upstream
(recorded here so the deviation is deliberate, see ``docs/decisions.md`` §23):

- ``17_09``: Galaxy queries an attribute literally named ```provided_metadata_style```
  (backticks included) — never matches; we use the bare attribute name.
- ``21_09``: Galaxy calls ``advice_collection.add("")`` (empty code) instead of
  ``21_09_fix_from_work_dir_whitespace``; we add the intended code.
- ``23_0``: Galaxy scans ``.//input[@type='text']`` via a ``_find_all`` helper that
  ignores its argument and always returns ``.//data[@from_work_dir]``; we scan the
  real text parameters (``<param type="text">``) for a missing ``optional``.

Two codes can't be a literal mirror regardless: ``24_2_fix_test_case_validation``
needs Galaxy's parameter-model test-case validator (we have no port), so we
**approximate** with the necessary condition "the tool ships a ``<test>``" (no
tests ⇒ the code cannot trip); and ``16_04_consider_implicit_extra_file_collection``
Galaxy emits **unconditionally**, so its detector is always-true.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from packaging.version import InvalidVersion, Version

if TYPE_CHECKING:
    from collections.abc import Callable

    from galaxy_tool_xml.document import ToolDocument
    from lxml import etree


@dataclass(frozen=True)
class ProfileUpgradeCode:
    """One Galaxy tool-profile upgrade code (mirrors an ``upgrade_codes.json`` entry).

    Attributes:
        code: Galaxy's code name, e.g. ``"16_04_exit_code"`` — the source-of-truth key.
        profile: The profile version the change takes effect at, e.g. ``"16.04"``.
        level: ``"must_fix"`` (the tool breaks / needs a change) or ``"consider"``
            (a runtime-behaviour change to review).
        niche: Galaxy's flag for codes that apply to a small slice of tools.
        message: Galaxy's verbatim description (often includes a legacy-restore recipe).
        url: The Galaxy PR that introduced the change, or ``None``.
    """

    code: str
    profile: str
    level: str
    niche: bool
    message: str
    url: str | None


# Vendored verbatim from galaxyproject/galaxy
# lib/galaxy/tool_util/upgrade/upgrade_codes.json @ b45c58a2 (2026-06-01).
# Order: by profile version, then catalogue order. `16_04_ready_interpreter`
# (level "ready") is omitted — it is a no-change "best practice" note.
PROFILE_UPGRADE_CODES: tuple[ProfileUpgradeCode, ...] = (
    ProfileUpgradeCode(
        code="16_04_fix_interpreter",
        profile="16.04",
        level="must_fix",
        niche=False,
        message=(
            "This tool uses an interpreter on the command block, this was disabled"
            " with 16.04. The command line needs to be rewritten to call the"
            " language runtime with a full path to the target script using"
            " `$tool_directory` to refer to the path to the tool and its script."
        ),
        url="https://github.com/galaxyproject/galaxy/pull/1688",
    ),
    ProfileUpgradeCode(
        code="16_04_consider_implicit_extra_file_collection",
        profile="16.04",
        level="consider",
        niche=True,
        message=(
            "Starting with profile 16.04 tools, Galaxy no longer attempts to just"
            " find tool outputs keyed on the output ID in the working directory."
            " Tool outputs need to be explicitly declared and dynamic outputs need"
            " to be specified in a 'galaxy.json' file or with a 'discover_datasets'"
            " block."
        ),
        url="https://github.com/galaxyproject/galaxy/pull/1688",
    ),
    ProfileUpgradeCode(
        code="16_04_fix_output_format",
        profile="16.04",
        level="must_fix",
        niche=False,
        message=(
            "Starting with 16.04 tools, having format='input' on a tool output is"
            " disabled. The behavior was not well defined for these outputs. Please"
            ' add format_source="a_specific_input_name" for a specific input to'
            " inherit the format from."
        ),
        url="https://github.com/galaxyproject/galaxy/pull/1688",
    ),
    ProfileUpgradeCode(
        code="16_04_exit_code",
        profile="16.04",
        level="consider",
        niche=False,
        message=(
            "Starting with 16.04 tools the exit code of the command executed will be"
            " used to detect errors by default. This tool previously would have"
            " discovered errors by checking if any content is written to standard"
            ' error. Add \'<stdio><regex match=".*" source="stderr" level="fatal"'
            ' description="Unknown error encountered" /></stdio>\' to your tool to'
            " restore the legacy behavior or restructure your command block to rely"
            " on the exit code."
        ),
        url="https://github.com/galaxyproject/galaxy/pull/1688",
    ),
    ProfileUpgradeCode(
        code="17_09_consider_provided_metadata_style",
        profile="17.09",
        level="consider",
        niche=True,
        message=(
            "Starting with 17.09 tools, the format of 'galaxy.json' (a rarely used"
            " file that can be used to dynamically collect datasets or metadata about"
            " datasets produced by the tool) changed - the original behavior can be"
            " restored by adding 'provided_metadata_style=\"legacy\"' to the tool's"
            " outputs tag."
        ),
        url="https://github.com/galaxyproject/galaxy/pull/4437",
    ),
    ProfileUpgradeCode(
        code="18_01_consider_structured_like",
        profile="18.01",
        level="consider",
        niche=False,
        message=(
            "Starting with 18.01 tools, the 'structured_like` attribute must"
            " reference inputs in a fully qualified manner - using '|' to describe"
            " parent conditionals for instance."
        ),
        url="https://github.com/galaxyproject/galaxy/pull/6162",
    ),
    ProfileUpgradeCode(
        code="18_01_consider_home_directory",
        profile="18.01",
        level="consider",
        niche=True,
        message=(
            "Starting with profile 18.01 tools, each job is given its own home"
            " directory. Most tools should not depend on global state in a home"
            " directory, if this is required though set 'use_shared_home=\"true\"' on"
            " the command tag of the tool."
        ),
        url="https://github.com/galaxyproject/galaxy/pull/5193",
    ),
    ProfileUpgradeCode(
        code="18_09_consider_python_environment",
        profile="18.09",
        level="consider",
        niche=False,
        message=(
            "Starting with profile 18.09 tools, data managers run without Galaxy's"
            " virtual environment. Be sure your requirements reflect all the data"
            " manager's dependencies."
        ),
        url="https://github.com/galaxyproject/galaxy/pull/6466",
    ),
    ProfileUpgradeCode(
        code="20_05_consider_inputs_as_json_changes",
        profile="20.05",
        level="consider",
        niche=False,
        message=(
            "Starting with 20.05, the format of data in 'inputs' config files changed"
            " slightly. Unselected optional `select` and `data_column` parameters get"
            " json null values instead of the string 'None' and multiple `select` and"
            " `data_column` parameters are lists (instead of comma separated strings)."
        ),
        url="https://github.com/galaxyproject/galaxy/pull/9776/files",
    ),
    ProfileUpgradeCode(
        code="20_09_consider_output_collection_order",
        profile="20.09",
        level="consider",
        niche=False,
        message=(
            "Starting in profile 20.09 tools, the order elements defined in tool test"
            " became relevant in order to verify collections are properly sorted."
            " This may cause tool tests to fail after the upgrade, rearrange the"
            " elements defined in output collections if this occurs."
        ),
        url="https://github.com/galaxyproject/galaxy/pull/10434",
    ),
    ProfileUpgradeCode(
        code="20_09_consider_set_e",
        profile="20.09",
        level="consider",
        niche=False,
        message=(
            "Starting with profile 20.09 tools, tool scripts are executed with the"
            " 'set -e' instruction. The 'set -e' option instructs the shell to"
            " immediately exit if any command has a non-zero exit status. If your"
            " command uses multiple sub-commands and you'd like to allow them to"
            " execute with non-zero exit codes add 'strict=\"false\"' to the command"
            " tag to restore the tool's legacy behavior."
        ),
        url="https://github.com/galaxyproject/galaxy/pull/9962",
    ),
    ProfileUpgradeCode(
        code="21_09_fix_from_work_dir_whitespace",
        profile="21.09",
        level="must_fix",
        niche=False,
        message=(
            "Starting with 21.09 tools, from_work_dir output file names are quoted so"
            " white space needs to be stripped out of attribute."
        ),
        url="https://github.com/galaxyproject/galaxy/pull/12536",
    ),
    ProfileUpgradeCode(
        code="21_09_consider_python_environment",
        profile="21.09",
        level="consider",
        niche=False,
        message=(
            "Starting with 21.09 data source tools, Galaxy's virtual environment is no"
            " longer included in the tool's runtime environment. Tools that require"
            " it, should include the galaxy-util package in their requirements."
        ),
        url="https://github.com/galaxyproject/galaxy/pull/12515",
    ),
    ProfileUpgradeCode(
        code="23_0_consider_optional_text",
        profile="23.0",
        level="consider",
        niche=False,
        message=(
            "Text parameters that are inferred to be optional (i.e the `optional` tag"
            " is not set, but the tool parameter accepts an empty string) are set to"
            " `None` for templating in Cheetah. Previous to this version tools would"
            ' receive the empty string "" as the templated value.'
        ),
        url="https://github.com/galaxyproject/galaxy/pull/15491/files",
    ),
    ProfileUpgradeCode(
        code="24_0_consider_python_environment",
        profile="24.0",
        level="consider",
        niche=False,
        message=(
            "Starting with 24.0 async data source tools, Galaxy's virtual environment"
            " is no longer included in the tool's runtime environment. Tools that"
            " require it, should include the galaxy-util package in their"
            " requirements."
        ),
        url="https://github.com/galaxyproject/galaxy/pull/17422",
    ),
    ProfileUpgradeCode(
        code="24_0_request_cleaning",
        profile="24.0",
        level="consider",
        niche=False,
        message=(
            "Starting with 24.0 data source tools, Galaxy requires explicit"
            " `request_param_translation` for each parameter sent to the tool. If"
            " this tools depends on unspecified parameters - new xml elements will"
            " need to be added for these parameters."
        ),
        url=None,
    ),
    ProfileUpgradeCode(
        code="24_2_fix_test_case_validation",
        profile="24.2",
        level="must_fix",
        niche=False,
        message=(
            "Starting with 24.2 tools, test cases must validate against a more"
            " stringent schema. Unknown parameters are disallowed (prevents"
            " misspellings), select parameters must be specified by value (to prevent"
            " ambiguity and match the API), column parameters must be specified as"
            " integers, and parameters must be full qualified ('|' separation to"
            " include parent repeat, cond, and sections)."
        ),
        url="https://github.com/galaxyproject/galaxy/pull/18679",
    ),
)


def _version_or_none(value: str, /) -> Version | None:
    """Parse *value* as a version, or ``None`` if it is not one.

    ``packaging`` exposes no validity predicate, so the ``try``/``except`` is the
    sanctioned boundary (mirrors ``codemods/update_profile.py``).
    """
    try:
        return Version(value)
    except InvalidVersion:
        return None


def upgrade_codes_crossed(
    *, from_profile: str, to_profile: str
) -> list[ProfileUpgradeCode]:
    """Return the Galaxy upgrade codes a ``from_profile`` → ``to_profile`` bump crosses.

    A code at version ``V`` is crossed when ``from_profile < V <= to_profile``
    (declaring ``V`` opts the tool into ``V``'s changes). The result preserves
    catalogue order. Returns ``[]`` when either profile is unparseable (e.g. a
    macro token) or the bump is not upward. This is range-based: it does not
    check whether the tool actually trips each code (Galaxy's advisor does that).
    """
    low = _version_or_none(from_profile)
    high = _version_or_none(to_profile)
    if low is None or high is None:
        return []
    return [
        change
        for change in PROFILE_UPGRADE_CODES
        if low < Version(change.profile) <= high
    ]


# --- per-tool detection (a port of Galaxy's upgrade advisor) --------------------
#
# Each predicate is a read-only LBYL query over the tool's lxml root, mirroring
# the corresponding `ProfileMigration.advise` branch in Galaxy's
# `lib/galaxy/tool_util/upgrade/__init__.py` @ b45c58a2. The deviations from that
# commit's literal code (its transcription bugs, and the two non-mirrorable codes)
# are documented in the module docstring.


def _command(root: etree._Element, /) -> etree._Element | None:
    """The tool's top-level ``<command>`` (Galaxy's ``_command_el``)."""
    return root.find("command")


def _detects_interpreter(root: etree._Element, /) -> bool:
    command = _command(root)
    return command is not None and bool(command.get("interpreter"))


def _detects_output_format_input(root: etree._Element, /) -> bool:
    return root.find(".//data[@format='input']") is not None


def _detects_no_error_handling(root: etree._Element, /) -> bool:
    return (
        root.find(".//stdio") is None
        and root.find(".//command[@detect_errors]") is None
    )


def _detects_provided_metadata_style(root: etree._Element, /) -> bool:
    outputs = root.find("outputs")
    return outputs is not None and outputs.get("provided_metadata_style") is not None


def _detects_structured_like(root: etree._Element, /) -> bool:
    return root.find(".//outputs/collection[@structured_like]") is not None


def _detects_no_shared_home(root: etree._Element, /) -> bool:
    command = _command(root)
    return command is not None and command.get("use_shared_home") is None


def _detects_inputs_config(root: etree._Element, /) -> bool:
    return root.find(".//configfiles/inputs") is not None


def _detects_output_collection_order(root: etree._Element, /) -> bool:
    # Galaxy flags a test ``<output_collection>`` whose parsed form carries
    # ``element_tests`` — i.e. it asserts on individual elements. In the XML that
    # is an ``<output_collection>`` (only ever a test construct) with an
    # ``<element>`` descendant.
    return any(
        output_collection.find(".//element") is not None
        for output_collection in root.iter("output_collection")
    )


def _detects_no_strict(root: etree._Element, /) -> bool:
    command = _command(root)
    return command is not None and command.get("strict") is None


def _detects_from_work_dir_whitespace(root: etree._Element, /) -> bool:
    for data in root.findall(".//data[@from_work_dir]"):
        value = data.get("from_work_dir") or ""
        if value != value.strip():
            return True
    return False


def _detects_non_optional_text(root: etree._Element, /) -> bool:
    return any(
        param.get("optional") is None
        for param in root.findall(".//param[@type='text']")
    )


def _detects_has_test(root: etree._Element, /) -> bool:
    # Approximation of Galaxy's run-the-test-case-validator check: a tool with no
    # ``<test>`` cannot produce a test-case validation error.
    return root.find("tests/test") is not None


def _tool_type_is(*tool_types: str) -> Callable[[etree._Element], bool]:
    """A detector that fires when the root ``tool_type`` is one of *tool_types*."""

    def detector(root: etree._Element, /) -> bool:
        return root.get("tool_type") in tool_types

    return detector


# code name -> per-tool detector. Keys are kept in sync with PROFILE_UPGRADE_CODES
# by ``test_every_code_has_a_detector``.
_DETECTORS: dict[str, Callable[[etree._Element], bool]] = {
    "16_04_fix_interpreter": _detects_interpreter,
    # Galaxy emits this one unconditionally within the 16.04 migration.
    "16_04_consider_implicit_extra_file_collection": lambda _root: True,
    "16_04_fix_output_format": _detects_output_format_input,
    "16_04_exit_code": _detects_no_error_handling,
    "17_09_consider_provided_metadata_style": _detects_provided_metadata_style,
    "18_01_consider_structured_like": _detects_structured_like,
    "18_01_consider_home_directory": _detects_no_shared_home,
    "18_09_consider_python_environment": _tool_type_is("manage_data"),
    "20_05_consider_inputs_as_json_changes": _detects_inputs_config,
    "20_09_consider_output_collection_order": _detects_output_collection_order,
    "20_09_consider_set_e": _detects_no_strict,
    "21_09_fix_from_work_dir_whitespace": _detects_from_work_dir_whitespace,
    "21_09_consider_python_environment": _tool_type_is("data_source"),
    "23_0_consider_optional_text": _detects_non_optional_text,
    "24_0_consider_python_environment": _tool_type_is("data_source_async"),
    "24_0_request_cleaning": _tool_type_is("data_source_async", "data_source"),
    "24_2_fix_test_case_validation": _detects_has_test,
}


def tripped_upgrade_codes(document: ToolDocument, /) -> frozenset[str]:
    """The codes whose per-tool detector fires for *document* (range-independent).

    Detection reads the lxml tree as-is, so capture this against the
    **pre-upgrade** tool: the ``upgrade`` codemods (GTX014/GTX015) mutate the very
    features some detectors look for, so detecting after they run would
    under-report. Intersect the result with ``upgrade_codes_crossed`` for the
    range-aware applicable set (``upgrade_codes_applicable`` does exactly that).

    The tree is read **un-expanded**, so a construct supplied only by a macro is
    invisible here: a macro-supplied ``<stdio>`` over-flags ``16_04_exit_code``,
    and a macro-supplied trigger under-reports other codes. The divergence is
    sized by the ``macro-expansion-detection-gap`` measure (codemod
    ``docs/decisions.md`` §25); it is cosmetic for this report-only note, but any
    *fix* gated on a detector must reckon with it (e.g. never inject ``<stdio>``
    off the raw tree).
    """
    root = document.root
    return frozenset(
        code for code, detector in _DETECTORS.items() if detector(root)
    )


def upgrade_codes_applicable(
    *, document: ToolDocument, from_profile: str, to_profile: str
) -> list[ProfileUpgradeCode]:
    """The crossed upgrade codes that actually *apply* to *document*.

    Narrows ``upgrade_codes_crossed`` to the codes whose per-tool detector fires
    for *document*, mirroring Galaxy's advisor (which detects rather than just
    ranging over the bumped interval). Result preserves catalogue order; ``[]``
    when no code is both crossed and applicable.
    """
    tripped = tripped_upgrade_codes(document)
    return [
        change
        for change in upgrade_codes_crossed(
            from_profile=from_profile, to_profile=to_profile
        )
        if change.code in tripped
    ]
