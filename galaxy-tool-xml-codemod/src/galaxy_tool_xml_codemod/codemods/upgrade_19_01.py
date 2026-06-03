"""Single-step profile upgrade: 19.01 -> 19.05.

Empirically (a 19.01-stuck combined corpus sweep), the only 19.05 schema delta
real tools trip on is ``name`` becoming required on output ``<data>`` elements.
In 19.01 an output could be declared as a bare ``<data from_work_dir="…"/>``;
19.05 makes ``name`` mandatory.

``Upgrade19_01`` synthesizes a deterministic, collision-free ``name`` (``output``,
then ``output2``, ``output3``, … for further unnamed outputs) on every unnamed
output ``<data>``. The corpus tools that need this never reference the output
name — not in the command line, not in a ``<test>`` — so the synthesized name is
an unreferenced placeholder identity: it breaks nothing and lets the tool
validate at the latest profile. It is a deliberate synthesis rather than a
recovery of author intent, which is why it is a one-step upgrade codemod and not
a cosmetic rule.

It names only **direct** ``<outputs>`` children. An unnamed ``<data>`` nested
inside an output ``<collection>`` is also ``OutputData`` (so also ``name``-required
at 19.05), but collection-element naming has different semantics and no corpus
tool needs it — the discovery sweep would report any that did. The synthesised
names also avoid colliding with an existing ``<collection name=…>``, not just
sibling ``<data>`` names (output identifiers share one namespace).

It only does structure; ``UpdateProfile`` (run by the ``UpgradeToLatest`` loop)
re-declares ``profile=`` afterwards. See ``docs/decisions.md`` §14.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from galaxy_tool_refactor_rules.meta import RuleMeta

from galaxy_tool_xml_codemod.codemod import CodemodCommand
from galaxy_tool_xml_codemod.codemods._coarse_detect import coarse_detect
from galaxy_tool_xml_codemod.cursor import Cursor

if TYPE_CHECKING:
    from collections.abc import Iterator

    from galaxy_tool_xml_codemod.change import Change
    from galaxy_tool_xml_codemod.module import Module


def _unused_output_name(used: set[str], /) -> str:
    """Return the first free name in the sequence ``output``, ``output2``, …."""
    if "output" not in used:
        return "output"
    index = 2
    while f"output{index}" in used:
        index += 1
    return f"output{index}"


class Upgrade19_01(CodemodCommand):
    """Upgrade a tool stuck at profile 19.01 toward 19.05 (name output ``<data>``)."""

    meta: ClassVar[RuleMeta] = RuleMeta(
        code="GTR008",
        summary=(
            "Upgrade a tool stuck at profile 19.01 toward 19.05"
            " (name output <data>)."
        ),
        since="0.0.1",
    )

    def detect(self, module: Module, /) -> Iterator[Change]:
        return coarse_detect(
            self, module, message="tool would be upgraded one step past profile 19.01"
        )

    def apply(self, module: Module, /) -> None:
        outputs = module.document.root.find("outputs")
        if outputs is None:
            return
        data_elements = outputs.findall("data")
        # Output identifiers share one namespace, so seed the collision set with
        # every already-named direct output child (``<data>`` AND ``<collection>``,
        # …) — synthesising "output" next to <collection name="output"> would mint
        # a duplicate output name.
        used = {
            name
            for child in outputs
            if isinstance(child.tag, str) and (name := child.get("name"))
        }
        for element in data_elements:
            if element.get("name") is not None:
                continue
            name = _unused_output_name(used)
            Cursor(element).set_attribute("name", name)
            used.add(name)
