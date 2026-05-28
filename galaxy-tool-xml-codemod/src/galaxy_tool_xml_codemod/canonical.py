"""The canonical codemod set — the structural transforms required for
fully-conformant Galaxy tool XML output.

Tier 2 (this package) and Tier 3 (``galaxy-tool-xml-fmt``) are
independent siblings of Tier 1 (``galaxy-tool-xml``). fmt's library is
cosmetic-only and does not import codemod. The end-user "format my
tool" workflow — exposed by ``galaxy-tool-xml-fmt``'s CLI — runs this
``CANONICAL_CODEMODS`` tuple before fmt's cosmetic rules when the
codemod package is installed (declared as the ``canonical`` extra on
fmt). Without codemod installed, fmt still works but produces
cosmetic-only output.

Future opt-in codemods (e.g. profile-version upgrades) live in their
own module, not here.
"""

from __future__ import annotations

from galaxy_tool_xml_codemod.codemod import CodemodCommand
from galaxy_tool_xml_codemod.codemods.reorder_param_attributes import (
    ReorderParamAttributes,
)
from galaxy_tool_xml_codemod.codemods.reorder_tool_attributes import (
    ReorderToolAttributes,
)

CANONICAL_CODEMODS: tuple[type[CodemodCommand], ...] = (
    ReorderParamAttributes,
    ReorderToolAttributes,
)
