"""Classify a ``<command>`` Cheetah ``$var`` by whether single-quoting it is safe.

The IUC ``single-quote your Cheetah variables`` practice is only *unconditionally*
safe for references whose rendered value can never contain whitespace (or a glob)
— quoting one of those is a strict no-op for any tool that currently works, while
quoting a deliberately word-splitting reference (``$adv_opts`` that splats into
several arguments, an ``$on_string`` carrying a user dataset label) changes the
command Galaxy runs. This module resolves each ``unquoted_cheetah_vars`` reference
against the tool's ``<inputs>`` and buckets it, so two callers can share one notion
of "provably quotable":

- the **GTX020 codemod** (tier 2) auto-quotes exactly the provable subset
  (``provably_quotable``);
- ``scripts.measure iuc011-fixability`` sizes that subset across the corpus.

Living in tier 1 keeps the codemod (tier 2) from importing the advisory-check tier
(tier 3.5) upward and keeps the measure and the codemod on one source of truth.
Heuristic: root-name resolution against ``<inputs>``, no full param-model walk.

The provable set is ``{safe, attr_safe, builtin_path}``:

- ``safe`` — a bare ``$param`` of an intrinsically single-token type (a number, a
  Galaxy-controlled dataset path, an author-fixed ``select`` value);
- ``attr_safe`` — a ``$param.attr`` whose attribute is space-free regardless of the
  run (``.ext`` is a charset-restricted datatype extension; ``.file_name`` / paths
  are Galaxy-controlled server paths);
- ``builtin_path`` — a ``$__…__`` Galaxy built-in (tool/working directories, ids,
  charset-restricted user names): deployment-fixed, space-free in any working
  install.

Everything else is *not* provably safe: ``text`` / ``multi`` params, ``attr_unsafe``
(``.name`` / ``.element_identifier`` carry user dataset labels), ``builtin_label``
(``$on_string``), ``structured`` (unresolved ``$cond.x``), and ``non_input``
(``#set``-assembled / loop / unknown roots).
"""

from __future__ import annotations

import re

from lxml import etree

# Param types whose value is intrinsically a single shell token — quoting one can
# never break word-splitting (it was always one argument). ``text`` is excluded: a
# single value, but commonly a free-form "extra options" field meant to splat.
SAFE_SINGLE_TYPES = frozenset(
    {
        "data",
        "integer",
        "float",
        "boolean",
        "color",
        "hidden",
        "baseurl",
        "genomebuild",
        "select",
        "drill_down",
        "data_column",
    }
)

# ``$param.attr`` metadata accessors whose value is space-free for any run: a
# datatype extension (charset-restricted), a Galaxy-controlled server path, or an
# integer id. Excludes user-facing labels (``name`` / ``element_identifier`` /
# ``value`` / ``display_name``) which carry dataset names and can contain spaces.
SAFE_ATTRS = frozenset(
    {
        "ext",
        "file_name",
        "path",
        "extra_files_path",
        "id",
        "hid",
        "dataset_id",
    }
)

# Non-dunder Galaxy built-ins that are run-varying *labels* (assembled from user
# dataset names) rather than deployment-fixed paths — unsafe to auto-quote.
BUILTIN_LABEL_ROOTS = frozenset({"on_string"})

# The reference classes ``classify_var`` returns. The provably-quotable subset is
# ``{safe, attr_safe, builtin_path}`` (see ``provably_quotable``).
VAR_CLASSES = (
    "safe",  # bare $param, single-token type -> safe to single-quote
    "text",  # bare $param of type text -> single value but maybe free-form options
    "multi",  # param is multiple= / data_collection -> unsafe (deliberate splat)
    "attr_safe",  # $param.attr, space-free attr (.ext / path / id) -> safe
    "attr_unsafe",  # $param.attr, label attr (.name / .element_identifier) -> unsafe
    "structured",  # root is a conditional/section/repeat, leaf unresolved
    "builtin_path",  # $__tool_directory__ etc. -> deployment-fixed path, safe
    "builtin_label",  # $on_string etc. -> run-varying label, unsafe
    "non_input",  # root resolves to no input -> #set-assembled / loop var / unknown
)

_PROVABLE_CLASSES = frozenset({"safe", "attr_safe", "builtin_path"})


def input_param_info(root: etree._Element, /) -> tuple[dict[str, str], set[str]]:
    """``(param-name -> kind, structural-names)`` for a tool root's ``<inputs>``.

    ``kind`` is ``"multi"`` / ``"text"`` / ``"safe"`` (most-unsafe wins when a name
    recurs across conditional branches: multi > text > safe). ``structural-names``
    are ``<conditional>`` / ``<section>`` / ``<repeat>`` names, the roots of a
    qualified ``$cond.sub`` access. Pure (element in, data out) for unit testing.
    """
    rank = {"safe": 0, "text": 1, "multi": 2}
    kinds: dict[str, str] = {}
    structural: set[str] = set()
    inputs = root.find("inputs")
    if inputs is None:
        return kinds, structural
    for param in inputs.iter("param"):
        name = param.get("name")
        if not name:
            continue
        ptype = param.get("type", "")
        multiple = param.get("multiple") in ("true", "True", "1")
        if ptype == "data_collection" or multiple:
            kind = "multi"
        elif ptype == "text":
            kind = "text"
        elif ptype in SAFE_SINGLE_TYPES:
            kind = "safe"
        else:
            kind = "text"  # unknown/other single type -> treat as judgment, not safe
        existing = kinds.get(name)
        if existing is None or rank[kind] > rank[existing]:
            kinds[name] = kind  # most-unsafe kind wins across conditional branches
    for tag in ("conditional", "section", "repeat"):
        for element in inputs.iter(tag):
            structural_name = element.get("name")
            if structural_name:
                structural.add(structural_name)
    return kinds, structural


def classify_var(var_name: str, kinds: dict[str, str], structural: set[str], /) -> str:
    """Bucket one ``unquoted_cheetah_vars`` reference (e.g. ``"$input"``).

    A bare ``$param`` resolves to its kind. A qualified ``$cond.subparam`` whose
    root is a structure (conditional/section/repeat) resolves to the **leaf**
    param's kind — the leaf is a real ``<param>`` so its single/multi-ness governs
    quoting safety just as a bare param does. ``$param.attr`` (root is a param, the
    trailing segment is a metadata attribute) splits into ``attr_safe`` /
    ``attr_unsafe`` by whether the attribute is space-free. Built-ins (``$__x__`` →
    ``builtin_path``, ``$on_string`` → ``builtin_label``) and unresolved roots
    (``#set`` / loop vars → ``non_input``) get their own buckets.
    """
    ref = var_name.translate({ord("$"): None, ord("{"): None, ord("}"): None})
    segments = re.split(r"[.\[]", ref)
    root = segments[0]
    attr_segments = [segment.rstrip("]") for segment in segments[1:]]
    has_attr = bool(attr_segments)
    if root in structural:
        leaf = attr_segments[-1] if attr_segments else root
        return kinds.get(leaf, "structured")
    if root in kinds:
        if has_attr:
            return "attr_safe" if _is_safe_attr(attr_segments) else "attr_unsafe"
        return kinds[root]
    if root.startswith("__"):
        return "builtin_path"
    if root in BUILTIN_LABEL_ROOTS:
        return "builtin_label"
    return "non_input"


def provably_quotable(
    var_name: str, kinds: dict[str, str], structural: set[str], /
) -> bool:
    """Whether single-quoting *var_name* is provably behaviour-preserving.

    True only for the ``{safe, attr_safe, builtin_path}`` classes — references
    whose value can never contain whitespace for a tool that currently works. The
    GTX020 codemod auto-quotes exactly this subset.
    """
    return classify_var(var_name, kinds, structural) in _PROVABLE_CLASSES


def _is_safe_attr(attr_segments: list[str], /) -> bool:
    """Whether a ``$param.attr`` access reads a space-free metadatum.

    Conservative: only a single known-safe attribute segment qualifies. A nested
    access (``$input.metadata.foo``) is treated as unsafe — its value is not
    provably space-free.
    """
    return len(attr_segments) == 1 and attr_segments[0] in SAFE_ATTRS
