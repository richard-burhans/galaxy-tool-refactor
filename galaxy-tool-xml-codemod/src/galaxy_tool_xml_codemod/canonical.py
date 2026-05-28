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

**Order matters.** The tuple runs front-to-back:

1. ``FixTypos`` — repair near-miss spelling typos. A no-op unless the
   tool validates at no profile, so it only acts on broken tools; running
   it first lets the rest of the pipeline see a validatable tree.
2. ``UpdateProfile`` — declare the newest profile the (now possibly
   repaired) tool validates at. After ``FixTypos`` so a repaired tool is
   labelled; before ``ReorderToolAttributes`` so an *added* ``profile=``
   gets positioned.
3. ``ReorderParamAttributes`` / ``ReorderToolAttributes`` — tidy
   attribute order last, once structure and profile are settled.
"""

from __future__ import annotations

from galaxy_tool_xml_codemod.codemod import CodemodCommand
from galaxy_tool_xml_codemod.codemods.fix_typos import FixTypos
from galaxy_tool_xml_codemod.codemods.reorder_param_attributes import (
    ReorderParamAttributes,
)
from galaxy_tool_xml_codemod.codemods.reorder_tool_attributes import (
    ReorderToolAttributes,
)
from galaxy_tool_xml_codemod.codemods.update_profile import UpdateProfile

CANONICAL_CODEMODS: tuple[type[CodemodCommand], ...] = (
    FixTypos,
    UpdateProfile,
    ReorderParamAttributes,
    ReorderToolAttributes,
)
