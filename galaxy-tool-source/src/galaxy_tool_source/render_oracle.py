"""Proof-by-execution that an edit did not change what a tool actually runs.

Every fixable GTR rule ships a proof document asserting it is
*behaviour-preserving*. Until this module the only machine-checked invariants were
**post-edit validity** and **idempotence** (``scripts/corpus_check.py codemod``), and
neither can see the failure that matters: an edit that leaves the XML valid and stable
while changing the **rendered command**. This is the oracle that closes that gap — the
``--certify=render`` seam ``galaxy_tool_codemod.certify`` reserved.

## How it works

A tool's ``<command>`` is a Cheetah template. Rendering it needs parameter values, so
this module **synthesises** them: it reads ``<inputs>`` and builds a deterministic
context, then evaluates the template with **Galaxy's own**
``galaxy.util.template.fill_template`` — the exact function Galaxy uses — rather than a
reimplementation of Cheetah's semantics.

The context is synthesised once, from the **before** tree, and both trees are rendered
against **the same** context. That is what makes the comparison an oracle: any
difference in the output is attributable to the edit, because nothing else differed.

## Why several worlds

One context exercises one path through the template's conditionals. A rule that
rewrites the untaken branch of an ``#if`` would render identically and pass. So the
tool is rendered under a small set of **worlds** (``WORLDS``) chosen to drive the
branches apart: booleans at ``falsevalue`` and at ``truevalue``, numerics at ``0`` and
at their declared default, text empty and non-empty, each ``<conditional>`` on its
lowest- and highest-valued ``<when>``, repeats at zero and one instance.

Worlds are built from **values, sorted** — the lowest and highest ``<option value>``,
the lowest and highest ``<when value>`` — never from document position. A codemod that
*reorders* options or whens (GTR002 and friends do reorder attributes, and a future one
may reorder elements) would otherwise shift which branch each world selects and report
a spurious divergence.

## What it models about Galaxy, deliberately

- A ``boolean`` reaches Cheetah as the **string** ``truevalue``/``falsevalue``, never a
  Python bool, and an absent pair defaults to ``'true'``/``'false'``. So ``#if $flag``
  is true for *both* states unless ``falsevalue=""``. The oracle reproduces this,
  because a rule that "fixes" a boolean test must be checked against the real
  semantics, not the intended ones.
- An ``integer``/``float`` is a real ``int``/``float``, so ``#if $n`` is false at 0 and
  ``$n > 5`` does not raise.
- Every other name resolves **symbolically** to its own dotted path (``$input.ext``
  renders ``input.ext``). Unknown names resolve too, via ``_Namespace.__missing__``, so
  Galaxy's injected specials (``$__tool_directory__``, ``$on_string``, …) never cause a
  spurious failure — and a rule that *renames* a Cheetah reference shows up as a plain
  textual difference rather than as an unrenderable tree.

Fidelity to Galaxy's real *values* is not the goal and would not help: the context is
shared, so only its determinism and its branch coverage matter.

## Failing closed

A template that will not render (Python-2 Cheetah, a construct Cheetah rejects, a
macro that will not expand) yields ``RenderVerdict(equal=None)`` with a reason —
**unknown**, never a false "equal" and never a false "changed". A caller gating on this
must treat ``None`` as "not proven", which is what ``certified`` does.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from lxml import etree

from galaxy_tool_source.macros import expand_from_tree, has_macros
from galaxy_tool_source.shell_oracle import boundary_signature

if TYPE_CHECKING:
    from collections.abc import Iterator, Mapping, Sequence
    from pathlib import Path

#: Elements whose text Galaxy evaluates as a Cheetah template.
_TEMPLATED_TAGS = ("command", "configfile", "version_command")

#: Grouping elements that nest their children under their own name.
_GROUPING_TAGS = frozenset({"section", "conditional", "repeat"})


class _Scalar(str):
    """A parameter value: a ``str`` that also answers any attribute access.

    Attribute access returns its own dotted path, so ``$input.ext`` renders
    ``input.ext`` and ``$x.metadata.columns`` renders ``x.metadata.columns``.
    Normal ``str`` methods still resolve first (``__getattr__`` runs only when
    ordinary lookup fails), so ``str($x).strip()`` behaves as written. Calls answer
    too, so ``$x.is_of_type("bam")`` renders rather than raising.
    """

    __slots__ = ()

    def __getattr__(self, name: str) -> _Scalar:
        if name.startswith("_"):  # never fake a dunder: let Python's protocols work
            raise AttributeError(name)
        return _Scalar(f"{self}.{name}")

    def __call__(self, *args: object, **kwargs: object) -> _Scalar:
        return _Scalar(f"{self}()")


class _Int(int):
    """An ``integer`` param: a real ``int`` so ``#if $n`` is false at 0."""

    __slots__ = ()

    def __getattr__(self, name: str) -> _Scalar:
        if name.startswith("_"):
            raise AttributeError(name)
        return _Scalar(f"{self}.{name}")


class _Float(float):
    """A ``float`` param: a real ``float`` for the same reason as ``_Int``."""

    __slots__ = ()

    def __getattr__(self, name: str) -> _Scalar:
        if name.startswith("_"):
            raise AttributeError(name)
        return _Scalar(f"{self}.{name}")


class _Group:
    """A ``<section>`` / ``<conditional>`` / one ``<repeat>`` instance.

    Declared children are real attributes, so they resolve normally; anything else
    answers symbolically, which keeps a template that reaches past what ``<inputs>``
    declares renderable instead of fatal.
    """

    def __init__(self, path: str, children: Mapping[str, object], /) -> None:
        self.__dict__.update(children)
        self.__dict__["_path"] = path

    def __getattr__(self, name: str) -> _Scalar:
        if name.startswith("_"):
            raise AttributeError(name)
        return _Scalar(f"{self.__dict__['_path']}.{name}")

    def __str__(self) -> str:
        return str(self.__dict__["_path"])


class _Namespace(dict):  # type: ignore[type-arg]
    """The Cheetah search list: every name resolves, declared or not.

    ``__contains__`` answers ``True`` unconditionally because Cheetah's NameMapper
    tests membership before fetching; without it ``__missing__`` is never reached and
    an injected Galaxy special (``$__tool_directory__``) raises ``NotFound``.
    """

    def __missing__(self, key: str) -> _Scalar:
        return _Scalar(str(key))

    def __contains__(self, key: object) -> bool:
        return True

    def __bool__(self) -> bool:
        """⚠ Always truthy, because ``fill_template`` does ``if not context``.

        An **empty** namespace -- a tool with no ``<inputs>``, or whose inputs yield no
        entries -- is falsy as a ``dict``, and ``galaxy.util.template.fill_template``
        then silently replaces it with its own ``kwargs``: a plain ``dict`` with no
        ``__missing__``. Every Galaxy-injected special (``$__tool_directory__``,
        ``$on_string``) then raises ``NotFound`` and the whole render came back
        ``None``, i.e. "not proven", for exactly the simplest tools.
        """
        return True


@dataclass(frozen=True)
class World:
    """One deterministic parameter assignment.

    ``low`` drives a template toward its "off" paths (``falsevalue``, 0, empty text,
    the lowest-valued ``<when>``, no repeat instances); ``high`` toward its "on" paths.
    ``declared`` uses what the tool itself declares (``value=``, ``checked=``,
    ``selected=``), i.e. the assignment a user sees on an untouched form.
    """

    name: str
    #: Which end of each value domain to take.
    edge: str  # "low" | "declared" | "high"


WORLDS: tuple[World, ...] = (
    World("low", "low"),
    World("declared", "declared"),
    World("high", "high"),
)


@dataclass(frozen=True)
class RenderVerdict:
    """What comparing two trees' rendered templates proved, by two instruments.

    **Text equality** (``equal``) is the strong one: the tool runs a byte-identical
    command, so behaviour is preserved whatever the shell would have done with it.

    **Boundary equality** (``boundary_equal``) is the one that makes this oracle usable
    on the quoting rules. GTR020.1 *deliberately* changes the rendered bytes -- adding
    single quotes is the whole point -- so text equality is sufficient but not
    *necessary* for preservation. What such an edit must preserve is the shell's reading
    of the line: the argv word partition and the file-descriptor topology. That is
    exactly ``shell_oracle.boundary_signature`` (bashlex, bash's own grammar), so when
    the text differs the comparison falls through to it.

    ``equal_normalised`` separates "the command changed" from "its layout changed";
    Galaxy flattens command whitespace building the job script, so a
    normalised-equal difference is cosmetic.

    Every field is ``None`` for "not proven" -- the honest answer when a side would not
    render or an instrument is unavailable. ``certified`` is the only thing a gate
    should read.
    """

    equal: bool | None
    equal_normalised: bool | None
    worlds_compared: int
    boundary_equal: bool | None = None
    reason: str | None = None
    #: ``(world, section, before, after)`` for the first world/section that differed.
    divergence: tuple[str, str, str, str] | None = None

    @property
    def certified(self) -> bool:
        """Whether this verdict *proves* preservation, by either instrument.

        ``None`` is not a proof, and a text difference alone is not a refutation --
        only the absence of both proofs is.
        """
        return self.equal is True or self.boundary_equal is True


def _text(element: etree._Element, /) -> str:
    """The template text of one element, including any child element tails."""
    return "".join(element.itertext())


def _option_values(param: etree._Element, /) -> list[str]:
    """Every ``<option value>`` of *param*, sorted — never in document order."""
    values = [
        option.get("value", "")
        for option in param.iter("option")
        if option.get("value") is not None
    ]
    return sorted(set(values))


def _boolean_pair(param: etree._Element, /) -> tuple[str, str]:
    """``(falsevalue, truevalue)`` with Galaxy's defaults for an absent pair.

    An absent pair defaults to the **strings** ``'false'``/``'true'``
    (``galaxy.tool_util.parser.util.boolean_true_and_false_values``), which is why a
    bare ``#if $flag`` is true in both states unless ``falsevalue=""``.
    """
    return param.get("falsevalue", "false"), param.get("truevalue", "true")


def _scalar_for(param: etree._Element, ptype: str, edge: str, name: str, /) -> object:
    """The value one leaf ``<param>`` takes in the world at *edge*."""
    if ptype == "boolean":
        false_value, true_value = _boolean_pair(param)
        if edge == "declared":
            checked = (param.get("checked") or "").lower() in ("true", "yes", "on", "1")
            return _Scalar(true_value if checked else false_value)
        return _Scalar(false_value if edge == "low" else true_value)
    if ptype in ("integer", "float"):
        cast: Any = _Int if ptype == "integer" else _Float
        declared = param.get("value")
        if edge == "low":
            return cast(0)
        if edge == "declared" and declared:
            try:
                return cast(float(declared) if ptype == "float" else int(declared))
            except ValueError:
                return cast(0)
        return cast(1)
    if ptype in ("select", "data_column", "drill_down"):
        values = _option_values(param)
        if not values:
            return _Scalar(f"{name}" if edge != "low" else "")
        if edge == "declared":
            chosen = [
                option.get("value", "")
                for option in param.iter("option")
                if (option.get("selected") or "").lower() in ("true", "yes", "on", "1")
            ]
            return _Scalar(sorted(chosen)[0] if chosen else values[0])
        return _Scalar(values[0] if edge == "low" else values[-1])
    if ptype == "text":
        if edge == "low":
            return _Scalar("")
        return _Scalar(param.get("value") or name)
    # data, data_collection, color, hidden, baseurl, …: symbolic, and empty at the low
    # edge so an `#if str($optional_input)` guard takes its absent path there.
    if edge == "low" and (param.get("optional") or "").lower() in (
        "true",
        "yes",
        "on",
        "1",
    ):
        return _Scalar("")
    return _Scalar(name)


def _when_for(conditional: etree._Element, edge: str, /) -> etree._Element | None:
    """The ``<when>`` a world picks, chosen by **value** so reordering cannot matter."""
    whens = [w for w in conditional.findall("when") if w.get("value") is not None]
    if not whens:
        return None
    whens.sort(key=lambda w: w.get("value") or "")
    if edge == "declared":
        selector = conditional.find("param")
        if selector is not None:
            chosen = [
                option.get("value", "")
                for option in selector.iter("option")
                if (option.get("selected") or "").lower() in ("true", "yes", "on", "1")
            ]
            if chosen:
                target = sorted(chosen)[0]
                for when in whens:
                    if when.get("value") == target:
                        return when
        return whens[0]
    return whens[0] if edge == "low" else whens[-1]


def _children_of(
    container: etree._Element, prefix: str, edge: str, /
) -> dict[str, object]:
    """Build the context entries for every input declared under *container*."""
    values: dict[str, object] = {}
    for child in container:
        if not isinstance(child.tag, str):
            continue
        name = child.get("name")
        if child.tag == "param":
            if not name:
                argument = child.get("argument")
                if not argument:
                    continue
                name = argument.lstrip("-").replace("-", "_")
            path = f"{prefix}{name}"
            values[name] = _scalar_for(child, child.get("type") or "text", edge, path)
        elif child.tag == "section" and name:
            path = f"{prefix}{name}"
            values[name] = _Group(path, _children_of(child, f"{path}.", edge))
        elif child.tag == "conditional" and name:
            path = f"{prefix}{name}"
            branch: dict[str, object] = {}
            selector = child.find("param")
            when = _when_for(child, edge)
            if selector is not None:
                selector_name = selector.get("name") or "unnamed"
                chosen = when.get("value") if when is not None else None
                branch[selector_name] = _Scalar(
                    chosen
                    if chosen is not None
                    else str(
                        _scalar_for(
                            selector, selector.get("type") or "select", edge, path
                        )
                    )
                )
            if when is not None:
                branch.update(_children_of(when, f"{path}.", edge))
            values[name] = _Group(path, branch)
        elif child.tag == "repeat" and name:
            path = f"{prefix}{name}"
            if edge == "low":
                values[name] = []  # zero instances: the #for body never runs
            else:
                values[name] = [
                    _Group(f"{path}_0", _children_of(child, f"{path}_0.", edge))
                ]
    return values


def build_context(root: etree._Element, world: World, /) -> _Namespace:
    """The Cheetah search list for *root* in *world*.

    Synthesised from ``<inputs>``; every undeclared name still resolves, symbolically.
    """
    namespace = _Namespace()
    inputs = root.find("inputs")
    if inputs is not None:
        namespace.update(_children_of(inputs, "", world.edge))
    return namespace


def context_fingerprint(namespace: _Namespace, /) -> tuple[tuple[str, str], ...]:
    """A comparable, order-independent rendering of a synthesised context.

    ⚠ The oracle shares ONE context between the two trees so that a difference in the
    output is attributable to the edit. That is what makes the comparison sound, and on
    its own it also made the oracle **blind to half the edits it needs to judge**: a
    context built from *before* still carries ``before``'s ``truevalue`` and ``value=``,
    so changing a boolean's ``truevalue`` or an integer's default produced an identical
    render and was certified. Measured, on the first run of the probe: "change a
    boolean's truevalue" and "change an integer default" both came back CERTIFIED.

    So the comparison has two halves, and both are necessary: the two trees must
    synthesise the *same* context (the declarations yield the same values -- this
    function), and they must render the same text *under* a shared one. The first
    catches an edit to ``<inputs>``, the second an edit to the template.
    """
    flat: list[tuple[str, str]] = []

    def walk(prefix: str, value: object) -> None:
        if isinstance(value, _Group):
            for key, child in sorted(value.__dict__.items()):
                if key != "_path":
                    walk(f"{prefix}.{key}" if prefix else key, child)
        elif isinstance(value, list):
            for index, item in enumerate(value):
                walk(f"{prefix}[{index}]", item)
        else:
            flat.append((prefix, f"{type(value).__name__}:{value}"))

    for name, value in sorted(namespace.items()):
        walk(name, value)
    return tuple(flat)


def _expanded(
    root: etree._Element, source_dir: Path | None, /
) -> etree._Element | None:
    """*root* with its macros expanded, or ``None`` when expansion fails."""
    if not has_macros(root):
        return root
    expanded, _errors = expand_from_tree(copy.deepcopy(root), source_dir=source_dir)
    return expanded.getroot() if expanded is not None else None


def _sections(root: etree._Element, /) -> Iterator[tuple[str, str]]:
    """Each Cheetah-evaluated text of *root*, as ``(label, template)``."""
    for tag in _TEMPLATED_TAGS:
        for index, element in enumerate(root.iter(tag)):
            label = (
                tag
                if tag != "configfile"
                else f"configfile:{element.get('name', index)}"
            )
            template = _text(element)
            if template.strip():
                yield label, template


def render(
    root: etree._Element,
    world: World,
    /,
    *,
    source_dir: Path | None = None,
    context: _Namespace | None = None,
) -> dict[str, str] | None:
    """Render every templated section of *root* in *world*.

    Returns ``None`` if macros will not expand or any section will not render — the
    caller must treat that as *unknown*, not as a pass.
    """
    from galaxy.util.template import fill_template  # heavy import, kept local

    expanded = _expanded(root, source_dir)
    if expanded is None:
        return None
    search_list = context if context is not None else build_context(expanded, world)
    rendered: dict[str, str] = {}
    for label, template in _sections(expanded):
        try:
            rendered[label] = str(fill_template(template, context=search_list))
        except Exception:  # noqa: BLE001 - any Cheetah failure means "unknown"
            return None
    return rendered


def _collapse(text: str, /) -> str:
    """*text* with every run of whitespace collapsed to one space, trimmed.

    Galaxy flattens the command's whitespace when it builds the job script, so this is
    the comparison that answers "did the command change" as opposed to "did its layout
    change".
    """
    return " ".join(text.split())


def render_equality_holds(
    before: etree._Element,
    after: etree._Element,
    /,
    *,
    source_dir: Path | None = None,
    worlds: Sequence[World] = WORLDS,
) -> RenderVerdict:
    """Whether *before* and *after* render the same command in every world.

    The context is built **once per world from** ``before`` and used for both trees, so
    a difference in the output is attributable to the edit alone. Every world is
    compared -- the loop does not stop at the first difference, because a later world
    may exercise a branch this one did not and the weaker verdicts are accumulated
    across all of them.
    """
    compared = 0
    text_equal = True
    normalised_equal = True
    boundary_equal: bool | None = True
    divergence: tuple[str, str, str, str] | None = None

    for world in worlds:
        before_expanded = _expanded(before, source_dir)
        if before_expanded is None:
            return RenderVerdict(
                None, None, compared, reason="before: macros would not expand"
            )
        context = build_context(before_expanded, world)
        after_expanded = _expanded(after, source_dir)
        if after_expanded is None:
            return RenderVerdict(
                None, None, compared, reason="after: macros would not expand"
            )
        # Half one: do the two <inputs> declarations yield the same values? A shared
        # context cannot see this, and without it an edit to a truevalue or a default
        # renders identically and is wrongly certified.
        fingerprint_before = context_fingerprint(context)
        fingerprint_after = context_fingerprint(build_context(after_expanded, world))
        if fingerprint_before != fingerprint_after:
            changed = sorted(
                {name for name, _ in set(fingerprint_before) ^ set(fingerprint_after)}
            )
            return RenderVerdict(
                False,
                False,
                compared + 1,
                boundary_equal=False,
                reason=(
                    "the inputs declare different values in world "
                    f"{world.name!r}: {', '.join(changed[:4])}"
                ),
            )
        rendered_before = render(before, world, source_dir=source_dir, context=context)
        if rendered_before is None:
            return RenderVerdict(
                None,
                None,
                compared,
                reason=f"before: will not render in world {world.name!r}",
            )
        rendered_after = render(after, world, source_dir=source_dir, context=context)
        if rendered_after is None:
            return RenderVerdict(
                None,
                None,
                compared,
                reason=f"after: will not render in world {world.name!r}",
            )
        compared += 1

        if set(rendered_before) != set(rendered_after):
            only = sorted(set(rendered_before) ^ set(rendered_after))
            return RenderVerdict(
                False,
                False,
                compared,
                boundary_equal=False,
                reason=f"templated sections differ: {', '.join(only)}",
                divergence=(world.name, only[0], "", ""),
            )

        for label, text_before in sorted(rendered_before.items()):
            text_after = rendered_after[label]
            if text_before == text_after:
                continue
            # POSITIVE CONTROL, checked only once a difference shows (so it costs
            # nothing on the ~87% that certify cleanly): does `before` even render
            # the same as ITSELF? A template calling `tempfile.mktemp()` or
            # generating a password emits fresh bytes every pass, so before-vs-after
            # differs for a reason that has nothing to do with the edit. Measured on
            # the first full 16-rule sweep: of 97 not-proven verdicts, the large
            # majority were this -- one tool regenerates a random 90-character key
            # per render. Without the control the oracle blames the codemod for the
            # template's own nondeterminism.
            control = render(before, world, source_dir=source_dir, context=context)
            if control is None or control.get(label) != text_before:
                return RenderVerdict(
                    None,
                    None,
                    compared,
                    reason=(
                        f"{label} renders nondeterministically (it differs from "
                        f"itself in world {world.name!r}), so before-vs-after cannot "
                        f"be attributed to the edit"
                    ),
                )
            text_equal = False
            if divergence is None:
                divergence = (world.name, label, text_before, text_after)
            if _collapse(text_before) != _collapse(text_after):
                normalised_equal = False
            # Tri-state, deliberately: ``False`` (the shell reads the two lines
            # differently) is a refutation and sticks; ``None`` (a side will not parse
            # as bash) is only an absence of proof and must not masquerade as one.
            if boundary_equal is not False:
                this = _boundary_equal(text_before, text_after)
                if this is False:
                    boundary_equal = False
                elif this is None:
                    boundary_equal = None

    if text_equal:
        return RenderVerdict(True, True, compared, boundary_equal=True)
    return RenderVerdict(
        False,
        normalised_equal,
        compared,
        boundary_equal=boundary_equal,
        divergence=divergence,
    )


def dequote(word: str, /) -> str:
    """POSIX quote removal: the bytes the shell actually passes in ``argv``.

    WARNING -- this step is what makes the boundary instrument usable at all. bashlex
    reports a word with its quote characters still in it, so a word that *gains*
    quotes compares unequal even when the shell hands the command identical bytes.
    Measured against real bash on a corpus tool (``bgruening/diff``), whose source
    embeds a Cheetah var between two single-quoted segments inside a sed script: the
    original and the GTR020.1-quoted form both produce the argv word
    ``/@@diffoutput@@/{rdiff_file``, yet their raw bashlex words differ by the added
    quote pair. Without quote removal that read as a refutation -- the instrument
    reporting a bug in the very rule it exists to certify.

    Single quotes take everything literally; inside double quotes a backslash is
    special only before ``$``, a backtick, ``"``, a backslash or a newline; outside
    both, a backslash escapes the next character. A surviving ``$`` expansion is left
    alone: Cheetah has already run, so what remains is the shell's to expand, and it
    expands identically on both sides.

    Differential-tested against real ``bash`` (``tests/test_render_oracle.py``). Three
    deviations are known and pinned there:

    * ``x$y`` and ``"x$y"`` -- bash expands the (unset) variable to nothing; this
      keeps ``$y`` verbatim. Deliberate, per the paragraph above: the comparison is
      between two renderings that carry the *same* expansion.
    * ``$'a\\tb'`` (ANSI-C quoting) -- bash decodes the escape to a real tab; this
      strips the quotes and keeps the text. Both sides are treated the same way, so
      identical input still compares identical; what it costs is precision when a
      codemod edits *inside* ``$'...'``, and there the verdict lands on not-proven,
      which is the conservative side. One corpus tool (``bgruening/autodock_vina``)
      has GTR020.1 quoting inside a ``$'...'`` block, so this is not hypothetical.
    """
    out: list[str] = []
    index = 0
    end = len(word)
    special_after_backslash = set('$`"\\\n')
    while index < end:
        char = word[index]
        if char == "'":
            close = word.find("'", index + 1)
            if close == -1:  # unbalanced: hand the rest back verbatim
                out.append(word[index + 1 :])
                break
            out.append(word[index + 1 : close])
            index = close + 1
        elif char == '"':
            index += 1
            while index < end and word[index] != '"':
                if (
                    word[index] == "\\"
                    and index + 1 < end
                    and word[index + 1] in special_after_backslash
                ):
                    out.append(word[index + 1])
                    index += 2
                    continue
                out.append(word[index])
                index += 1
            index += 1
        elif char == "\\" and index + 1 < end:
            out.append(word[index + 1])
            index += 2
        else:
            out.append(char)
            index += 1
    return "".join(out)


def _boundary_equal(before: str, after: str, /) -> bool | None:
    """Whether two rendered commands read identically to the shell.

    Compares the argv word partition and the fd topology **after quote removal**, so
    a quoting-only edit -- the whole point of GTR020.1 -- compares equal, while a
    change to the words themselves does not.

    ``None`` when either side will not parse as bash or the ``shell-oracle`` extra is
    absent: an absence of proof, which the caller must not conflate with a refutation.
    """
    signature_before = boundary_signature(before)
    signature_after = boundary_signature(after)
    if signature_before is None or signature_after is None:
        return None
    if tuple(dequote(w) for w in signature_before.words) != tuple(
        dequote(w) for w in signature_after.words
    ):
        return False
    return tuple(
        (r.src_fd, r.op, dequote(str(r.target)), r.is_dup)
        for r in signature_before.redirections
    ) == tuple(
        (r.src_fd, r.op, dequote(str(r.target)), r.is_dup)
        for r in signature_after.redirections
    )
