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
"you're fine" message, not a change) is omitted.

**Two profile behaviour changes the Galaxy schema docs describe are intentionally
absent**, because Galaxy's ``upgrade_codes.json`` does not catalogue them: the
**19.05** default Python 2→3 interpreter change and the **25.1** ``<credentials>``
migration. Keeping this map a strict mirror of the authoritative catalogue is the
deliberate choice (see ``../../docs/profile_upgrades.md``); add them only if Galaxy
adds upgrade codes for them.

``upgrade_codes_crossed`` answers "which of these does a baseline→target bump
cross", so the ``upgrade`` path can warn (it cannot auto-preserve them). It is a
**range-based** signal (every code whose profile lies in the bumped range), unlike
Galaxy's advisor which *detects* per-tool whether each code actually applies —
porting that detection is future work.
"""

from __future__ import annotations

from dataclasses import dataclass

from packaging.version import InvalidVersion, Version


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
