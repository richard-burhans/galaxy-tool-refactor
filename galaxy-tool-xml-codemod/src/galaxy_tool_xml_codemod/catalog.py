"""The full set of GTR-coded codemods, for documentation and registry use.

Distinct from ``canonical_codemods()`` (``canonical.py``): that tuple is the
*ordered pipeline* fmt's CLI runs, and it omits the single-step ``upgrade_vN``
codemods because ``UpgradeToLatest`` drives them internally. This catalog lists
*every* codemod that carries a ``RuleMeta`` GTR code, so a cross-tier rule
registry (such as the corpus-format stat page) can enumerate them alongside the
formatter tier's ``all_rules()``.
"""

from __future__ import annotations

from galaxy_tool_xml_codemod.codemod import CodemodCommand
from galaxy_tool_xml_codemod.codemods.convert_help_markdown import (
    ConvertHelpToMarkdown,
)
from galaxy_tool_xml_codemod.codemods.drop_redundant_param_name import (
    DropRedundantParamName,
)
from galaxy_tool_xml_codemod.codemods.fix_from_work_dir_whitespace import (
    FixFromWorkDirWhitespace,
)
from galaxy_tool_xml_codemod.codemods.fix_interpreter import FixInterpreter
from galaxy_tool_xml_codemod.codemods.fix_output_format_input import (
    FixOutputFormatInput,
)
from galaxy_tool_xml_codemod.codemods.fix_typos import FixTypos
from galaxy_tool_xml_codemod.codemods.normalize_boolean_values import (
    NormalizeBooleanValues,
)
from galaxy_tool_xml_codemod.codemods.reorder_param_attributes import (
    ReorderParamAttributes,
)
from galaxy_tool_xml_codemod.codemods.reorder_tool_attributes import (
    ReorderToolAttributes,
)
from galaxy_tool_xml_codemod.codemods.reorder_tool_children import (
    ReorderToolChildren,
)
from galaxy_tool_xml_codemod.codemods.repair_help_rst import RepairHelpRst
from galaxy_tool_xml_codemod.codemods.replace_output_element import (
    ReplaceOutputElement,
)
from galaxy_tool_xml_codemod.codemods.single_quote_command_vars import (
    SingleQuoteCommandVars,
)
from galaxy_tool_xml_codemod.codemods.tokenize_version import TokenizeVersion
from galaxy_tool_xml_codemod.codemods.trim_attribute_whitespace import (
    TrimAttributeWhitespace,
)
from galaxy_tool_xml_codemod.codemods.update_profile import UpdateProfile
from galaxy_tool_xml_codemod.codemods.upgrade_19_01 import Upgrade19_01
from galaxy_tool_xml_codemod.codemods.upgrade_21_09 import Upgrade21_09
from galaxy_tool_xml_codemod.codemods.upgrade_24_0 import Upgrade24_0
from galaxy_tool_xml_codemod.codemods.upgrade_24_1 import Upgrade24_1
from galaxy_tool_xml_codemod.codemods.upgrade_25_1 import Upgrade25_1
from galaxy_tool_xml_codemod.codemods.wrap_command_cdata import WrapCommandCdata
from galaxy_tool_xml_codemod.codemods.wrap_help_cdata import WrapHelpCdata
from galaxy_tool_xml_codemod.upgrades import UpgradeToLatest


def coded_codemods() -> tuple[type[CodemodCommand], ...]:
    """Return every GTR-coded codemod class, sorted by ``meta.code``."""
    classes: list[type[CodemodCommand]] = [
        FixTypos,
        ReorderParamAttributes,
        ReorderToolAttributes,
        ReorderToolChildren,
        UpdateProfile,
        Upgrade19_01,
        Upgrade21_09,
        Upgrade24_0,
        Upgrade24_1,
        Upgrade25_1,
        UpgradeToLatest,
        FixFromWorkDirWhitespace,
        FixOutputFormatInput,
        FixInterpreter,
        NormalizeBooleanValues,
        RepairHelpRst,
        WrapCommandCdata,
        WrapHelpCdata,
        SingleQuoteCommandVars,
        TrimAttributeWhitespace,
        ReplaceOutputElement,
        DropRedundantParamName,
        ConvertHelpToMarkdown,
        TokenizeVersion,
    ]
    return tuple(sorted(classes, key=lambda cls: cls.meta.code))
