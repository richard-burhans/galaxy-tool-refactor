"""RST -> CommonMark ``<help>`` conversion behind a render-equivalence gate.

Galaxy renders the two help formats on **opposite sides of the wire**: RST
server-side (``galaxy.util.rst_to_html`` — the docutils html4css1 writer) and
``format="markdown"`` client-side (``ToolHelpMarkdown.vue`` →
``MarkdownIt({html: false}).render``, the markdown-it default preset). Converting
RST to Markdown therefore **swaps the rendering engine** — behaviour-changing by
construction — so a conversion is kept only when a **render-equivalence gate**
proves it: render the RST exactly as Galaxy's server does and the converted
CommonMark exactly as Galaxy's client does (markdown-it-py's ``js-default``
preset, ``html:false``), reduce both renderings to a normalized semantic
skeleton, and accept iff the skeletons are equal.

The converter is a whitelist doctree visitor that **bails on the first node with
no CommonMark form** (definition/field/option lists, tables, line blocks,
interpreted-text roles, …) — never a lossy approximation. Corpus sizing: 72.2 %
of RST ``<help>`` bodies convert and pass the gate (``scripts.measure
help-rst-md-convert``, which consumes this module).

The gate needs ``markdown-it-py`` (the ``galaxy-tool-xml[markdown]`` extra);
``markdown_renderer_available()`` is the LBYL check — conversion without the
gate is unsound, so callers must refuse, not degrade, when it is absent.
"""

from __future__ import annotations

import contextlib
import importlib.util
import io
import re
from typing import Any

import docutils.core
import docutils.writers.html4css1
from lxml import etree
from lxml import html as lxml_html

from galaxy_tool_xml.rst import repair_help_rst, rst_is_invalid

# CommonMark structural ASCII punctuation, backslash-escaped in converted plain text.
_CM_ESCAPE = re.compile(r"([\\`*_{}\[\]()#+\-.!>~|])")


def markdown_renderer_available() -> bool:
    """Whether the markdown-it-py gate renderer (``[markdown]`` extra) is present."""
    return importlib.util.find_spec("markdown_it") is not None


class _CommonMarkBail(Exception):
    """Raised by the doctree visitor on the first non-CommonMark node type."""

    def __init__(self, node_type: str) -> None:
        super().__init__(node_type)
        self.node_type = node_type


def _inline(node: Any) -> str:
    """Render a docutils inline node as CommonMark, or raise ``_CommonMarkBail``."""
    name = type(node).__name__
    if name == "Text":
        return _CM_ESCAPE.sub(r"\\\1", node.astext())
    if name == "emphasis":
        return "*" + "".join(_inline(child) for child in node.children) + "*"
    if name == "strong":
        return "**" + "".join(_inline(child) for child in node.children) + "**"
    if name == "literal":
        return "`" + str(node.astext()) + "`"
    if name == "reference":
        uri = node.get("refuri")
        label = "".join(_inline(child) for child in node.children)
        return f"[{label}]({uri})" if uri else label
    if name == "image":
        return f"![{node.get('alt') or ''}]({node.get('uri') or ''})"
    if name == "problematic":
        return str(node.astext())
    if name == "target":
        return "".join(_inline(child) for child in node.children)
    raise _CommonMarkBail(name)


def _block(node: Any, out: list[str], depth: int) -> None:
    """Render a docutils block node into *out*, or raise ``_CommonMarkBail``."""
    name = type(node).__name__
    if name == "document":
        for child in node.children:
            _block(child, out, depth)
    elif name == "section":
        for child in node.children:
            _block(child, out, depth + 1)
    elif name == "title":
        level = min(max(depth, 1), 6)
        heading = "".join(_inline(child) for child in node.children)
        out.append("#" * level + " " + heading)
    elif name == "paragraph":
        out.append("".join(_inline(child) for child in node.children))
    elif name == "literal_block":
        out.append("```\n" + node.astext() + "\n```")
    elif name == "bullet_list":
        for item in node.children:
            _list_item(item, out, "- ")
    elif name == "enumerated_list":
        for index, item in enumerate(node.children, 1):
            _list_item(item, out, f"{index}. ")
    elif name == "block_quote":
        inner: list[str] = []
        for child in node.children:
            _block(child, inner, depth)
        out.append("\n".join("> " + line for line in "\n\n".join(inner).split("\n")))
    elif name == "transition":
        out.append("---")
    elif name == "image":
        out.append(f"![{node.get('alt') or ''}]({node.get('uri') or ''})")
    elif name in ("comment", "target", "system_message"):
        return  # invisible in the rendering
    else:
        raise _CommonMarkBail(name)


def _list_item(item: Any, out: list[str], marker: str) -> None:
    inner: list[str] = []
    for child in item.children:
        _block(child, inner, 0)
    lines = "\n\n".join(inner).split("\n")
    pad = " " * len(marker)
    rendered = marker + (lines[0] if lines else "")
    for line in lines[1:]:
        rendered += "\n" + (pad + line if line else "")
    out.append(rendered)


def _parse_doctree(text: str) -> Any | None:
    """Parse RST to a docutils doctree; ``None`` on a parse crash.

    docutils exposes no LBYL parse predicate, so the broad ``except`` is the
    sanctioned third-party boundary (mirrors ``rst._serious_messages``).
    """
    overrides = {
        "report_level": 1,
        "halt_level": 5,
        "input_encoding": "unicode",
        "doctitle_xform": False,
        "warning_stream": io.StringIO(),
    }
    try:
        with contextlib.redirect_stderr(io.StringIO()):
            return docutils.core.publish_doctree(text, settings_overrides=overrides)
    except Exception:
        return None


def rst_to_commonmark(text: str, /) -> tuple[str | None, str | None]:
    """Convert RST to CommonMark; ``(markdown, None)`` or ``(None, bail_class)``.

    The bail class is the first doctree node type with no CommonMark form (or
    ``"parse-fail"``). A returned conversion is **not yet proven equivalent** —
    callers must pass it through ``conversion_is_render_equivalent``.
    """
    doctree = _parse_doctree(text)
    if doctree is None:
        return None, "parse-fail"
    out: list[str] = []
    try:
        _block(doctree, out, 0)
    except _CommonMarkBail as bail:
        return None, bail.node_type
    return "\n\n".join(out) + "\n", None


def _rst_html_body(text: str) -> str:
    """Render RST the way Galaxy's server does: the docutils html4css1 body."""
    overrides = {
        "doctitle_xform": False,
        "halt_level": 6,
        "report_level": 6,
        "output_encoding": "unicode",
        "warning_stream": io.StringIO(),
        "embed_stylesheet": False,
    }
    with contextlib.redirect_stderr(io.StringIO()):
        parts = docutils.core.publish_parts(
            text,
            writer=docutils.writers.html4css1.Writer(),
            settings_overrides=overrides,
        )
    return str(parts["body"])


def _markdown_html(text: str) -> str:
    """Render CommonMark the way Galaxy's client does: markdown-it, ``html:false``.

    Requires the ``[markdown]`` extra (``markdown_renderer_available()``).
    """
    from markdown_it import MarkdownIt

    return str(MarkdownIt("js-default", {"html": False}).render(text))


# Canonical tag map for the semantic skeleton: collapse the docutils-vs-markdown-it
# HTML spelling differences (<tt> vs <code>, <h1..6>, <ul>/<ol>) to shared names.
_SKELETON_TAG_CANON = {
    "tt": "code", "code": "code", "pre": "pre",
    "em": "em", "i": "em", "strong": "strong", "b": "strong",
    "h1": "h", "h2": "h", "h3": "h", "h4": "h", "h5": "h", "h6": "h",
    "ul": "list", "ol": "list", "li": "li",
    "p": "p", "blockquote": "quote", "a": "a", "img": "img", "hr": "hr",
    "table": "table", "thead": "_", "tbody": "_",
    "tr": "tr", "th": "cell", "td": "cell",
}
# Structural wrappers both renderers emit freely: unwrap, keep children.
_SKELETON_UNWRAP = frozenset({"div", "span", "body", "html", "document", "root"})
_SKELETON_BLOCK_WS = re.compile(
    r"\s*(</?(?:p|pre|list|li|quote|h|hr|table|tr|cell|_)>)\s*"
)


def _html_skeleton(html_text: str) -> str | None:
    """Reduce rendered HTML to a normalized semantic skeleton string."""
    try:
        fragment = lxml_html.fragment_fromstring(html_text, create_parent="root")
    except etree.ParserError:
        return None
    # A sole <p> inside a list item / cell / blockquote is loose-vs-tight spacing
    # only (markdown-it wraps loose-list items in <p>; docutils "simple" lists
    # don't) — unwrap it so the comparison is content-level.
    for paragraph in fragment.iter("p"):
        parent = paragraph.getparent()
        if parent is not None and parent.tag in ("li", "td", "th", "dd", "blockquote"):
            paragraph.drop_tag()
    # docutils literal block = <pre>…</pre>; markdown-it fenced = <pre><code>…</code>.
    # Unwrap the inner <code> so both reduce to <pre>.
    for code in fragment.iter("code"):
        parent = code.getparent()
        if parent is not None and parent.tag == "pre":
            code.drop_tag()
    parts: list[str] = []
    _skeleton_walk(fragment, parts)
    skeleton = re.sub(r"\s+", " ", "".join(parts)).strip()
    # Whitespace adjacent to a BLOCK tag is insignificant (tight-vs-loose layout);
    # whitespace around INLINE tags (em/strong/code/a) is kept — it is content.
    return _SKELETON_BLOCK_WS.sub(r"\1", skeleton)


def _skeleton_walk(element: Any, parts: list[str]) -> None:
    tag = element.tag if isinstance(element.tag, str) else None
    if tag is None:  # comment / processing instruction
        return
    if tag in _SKELETON_UNWRAP:
        _skeleton_text(element.text, parts)
        for child in element:
            _skeleton_walk(child, parts)
            _skeleton_text(child.tail, parts)
        return
    canon = _SKELETON_TAG_CANON.get(tag, tag)  # unknown -> raw, so a mismatch shows
    if canon == "_":  # thead/tbody: transparent
        _skeleton_text(element.text, parts)
        for child in element:
            _skeleton_walk(child, parts)
            _skeleton_text(child.tail, parts)
        return
    if canon == "a":
        parts.append(f"<a:{(element.get('href') or '').strip()}>")
    elif canon == "img":
        parts.append(f"<img:{(element.get('src') or '').strip()}>")
        return
    else:
        parts.append(f"<{canon}>")
    _skeleton_text(element.text, parts)
    for child in element:
        _skeleton_walk(child, parts)
        _skeleton_text(child.tail, parts)
    parts.append(f"</{canon}>")


def _skeleton_text(text: str | None, parts: list[str]) -> None:
    if text and text.strip():
        parts.append(text)


def conversion_is_render_equivalent(rst_text: str, markdown_text: str, /) -> bool:
    """True iff *markdown_text* renders to the same semantic skeleton as *rst_text*.

    Requires the ``[markdown]`` extra. The broad ``except`` is the third-party
    render boundary (docutils / markdown-it / lxml): a crash on either side means
    equivalence cannot be proven, so the conversion is rejected.
    """
    try:
        rst_skeleton = _html_skeleton(_rst_html_body(rst_text))
        markdown_skeleton = _html_skeleton(_markdown_html(markdown_text))
    except Exception:
        return False
    return rst_skeleton is not None and rst_skeleton == markdown_skeleton


def convert_help_rst(text: str, /) -> str | None:
    """Convert an RST ``<help>`` body to gate-proven-equivalent CommonMark.

    Composes the pipeline: invalid RST is first passed through the GTR089.1
    surgical repair (itself behaviour-gated; an unrepairable body returns
    ``None``), then converted, then kept only if render-equivalent — against the
    repaired text, which is what Galaxy would render. Returns the CommonMark, or
    ``None`` when the body is not *provably* convertible. Requires the
    ``[markdown]`` extra (``markdown_renderer_available()``).
    """
    if rst_is_invalid(text):
        repaired = repair_help_rst(text)
        if repaired is None:
            return None
        text = repaired
    markdown, _bail = rst_to_commonmark(text)
    if markdown is None:
        return None
    if not conversion_is_render_equivalent(text, markdown):
        return None
    return markdown
