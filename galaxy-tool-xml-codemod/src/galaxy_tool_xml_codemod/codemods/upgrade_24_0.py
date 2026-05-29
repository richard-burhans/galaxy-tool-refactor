"""Single-step profile upgrade: 24.0 -> 24.1.

Empirically (a 24.0-stuck combined corpus sweep), the 24.1 schema delta a real
tool trips on is ``<filter>`` no longer being allowed inside a ``<collection>``'s
child ``<data>`` — at 24.1 a collection element ``<data>`` admits only
``actions`` / ``change_format``. A top-level output ``<data>`` may still carry a
``<filter>``; only the collection-nested ones are rejected.

When *every* child ``<data>`` of a collection carries the *same* ``<filter>``
condition, that is an all-or-nothing condition on the whole collection: the
collection is produced exactly when the condition holds, with all its elements.
``Upgrade24_0`` hoists one such filter to the ``<collection>`` level and drops
the per-``<data>`` filters — a semantics-preserving restructure (a collection
filter and identical element filters describe the same output).

It deliberately does nothing when the restructure would *not* be equivalent:

- child ``<data>`` filters that differ (genuinely per-element selection);
- a collection where only some children are filtered (hoisting would newly
  filter the rest);
- a collection that already has its own ``<filter>`` (hoisting would AND a
  second condition, changing when elements appear).

Those stay stuck and the discovery sweep reports them. It only does structure;
``UpdateProfile`` (run by the ``UpgradeToLatest`` loop) re-declares ``profile=``
afterwards. See ``docs/decisions.md`` §14.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from galaxy_tool_refactor_rules.meta import RuleMeta
from lxml import etree

from galaxy_tool_xml_codemod.codemod import CodemodCommand
from galaxy_tool_xml_codemod.cursor import Cursor

if TYPE_CHECKING:
    from galaxy_tool_xml_codemod.module import Module


def _child_data(collection: etree._Element, /) -> list[etree._Element]:
    """Return the collection's direct ``<data>`` children.

    A literal-tag comparison already excludes Comment/ProcessingInstruction
    nodes (their ``.tag`` is a callable sentinel, never ``== "data"``).
    """
    return [child for child in collection if child.tag == "data"]


class Upgrade24_0(CodemodCommand):
    """Upgrade a tool stuck at profile 24.0 toward 24.1 (hoist collection filters)."""

    meta: ClassVar[RuleMeta] = RuleMeta(
        code="GTX009",
        summary=(
            "Upgrade a tool stuck at profile 24.0 toward 24.1"
            " (hoist collection filters)."
        ),
        since="0.0.1",
    )

    def apply(self, module: Module, /) -> None:
        for collection in module.document.root.iter("collection"):
            self._hoist_shared_filter(collection)

    @staticmethod
    def _hoist_shared_filter(collection: etree._Element, /) -> None:
        data_children = _child_data(collection)
        if not data_children:
            return
        # A collection that already carries its own filter can't take a hoisted
        # one without changing when its elements appear.
        if collection.find("filter") is not None:
            return
        # Every child must carry exactly one filter; otherwise hoisting either
        # drops a per-element distinction or newly filters an unfiltered element.
        filters = [child.findall("filter") for child in data_children]
        if any(len(found) != 1 for found in filters):
            return
        conditions = {(found[0].text or "").strip() for found in filters}
        if len(conditions) != 1 or not next(iter(conditions)):
            return
        # Hoist: one filter on the collection (text preserved verbatim from the
        # first child), then drop every per-data filter.
        Cursor(collection).add_child("filter", text=filters[0][0].text)
        for found in filters:
            Cursor(found[0]).remove()
