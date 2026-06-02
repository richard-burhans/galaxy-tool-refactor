"""The full set of GTX-coded codemods, for documentation and registry use.

Distinct from ``CANONICAL_CODEMODS`` (``canonical.py``): that tuple is the
*ordered pipeline* fmt's CLI runs, and it omits the single-step ``upgrade_vN``
codemods because ``UpgradeToLatest`` drives them internally. This catalog lists
*every* codemod that carries a ``RuleMeta`` GTX code, so a cross-tier rule
registry (such as the corpus-format stat page) can enumerate them alongside the
formatter tier's ``all_rules()``.
"""

from __future__ import annotations

from galaxy_tool_xml_codemod.codemod import CodemodCommand
from galaxy_tool_xml_codemod.codemods.fix_from_work_dir_whitespace import (
    FixFromWorkDirWhitespace,
)
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
from galaxy_tool_xml_codemod.codemods.update_profile import UpdateProfile
from galaxy_tool_xml_codemod.codemods.upgrade_19_01 import Upgrade19_01
from galaxy_tool_xml_codemod.codemods.upgrade_24_0 import Upgrade24_0
from galaxy_tool_xml_codemod.codemods.upgrade_24_1 import Upgrade24_1
from galaxy_tool_xml_codemod.codemods.upgrade_25_1 import Upgrade25_1
from galaxy_tool_xml_codemod.upgrades import UpgradeToLatest


def coded_codemods() -> tuple[type[CodemodCommand], ...]:
    """Return every GTX-coded codemod class, sorted by ``meta.code``."""
    classes: list[type[CodemodCommand]] = [
        FixTypos,
        ReorderParamAttributes,
        ReorderToolAttributes,
        ReorderToolChildren,
        UpdateProfile,
        Upgrade19_01,
        Upgrade24_0,
        Upgrade24_1,
        Upgrade25_1,
        UpgradeToLatest,
        FixFromWorkDirWhitespace,
        FixOutputFormatInput,
        NormalizeBooleanValues,
    ]
    return tuple(sorted(classes, key=lambda cls: cls.meta.code))
