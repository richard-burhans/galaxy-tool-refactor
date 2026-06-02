"""Schema-boolean attribute knowledge and value normalization.

Galaxy tool authors sometimes write Python-style ``True``/``False`` (or
``Yes``/``No``/``On``/``Off``) for boolean attributes. The Galaxy XSD types those
attributes ``xs:boolean``, which accepts only ``true``/``false``/``1``/``0`` — so
the capitalized forms fail validation even though Galaxy's runtime
``string_as_bool`` reads them case-insensitively. Normalizing them to the
canonical lowercase form is therefore *behaviour-preserving* and restores
validity.

``suggest_boolean_normalizations`` reports the rewrites: it descends the tree and
the generated model classes in lockstep (the same technique ``corrections.py``
uses, because the same tag means different things under different parents, and an
attribute can be ``xs:boolean`` under one element/profile and a free string under
another). Only attributes the model types as boolean *at the element they appear
on* are reported, so a literal-string attribute (``value`` on ``<option>``) is
never rewritten. Like ``corrections.py`` this module only *suggests* — it never
mutates a tool (mutation is the tier-2 codemod's job).
"""

from __future__ import annotations

import dataclasses
import enum
import types
import typing
from dataclasses import dataclass
from functools import cache

from lxml import etree

from galaxy_tool_xml.binding import Source, parse_tool
from galaxy_tool_xml.document import ToolDocument
from galaxy_tool_xml.models.registry import tool_class
from galaxy_tool_xml.profiles import resolve_profile

# Macro constructs are not part of the post-expansion schema vocabulary; an
# un-expanded tool legitimately contains them, so they are never descended into.
_MACRO_ELEMENTS = frozenset({"expand", "macros", "import", "token", "macro", "xml"})

# Galaxy's ``string_as_bool`` reads these (case-insensitively) as ``True``; the
# conventional falsy literals map to ``False``. Anything else is not a recognized
# boolean spelling and is left alone (it may be a typo or a non-boolean value).
_RECOGNIZED_TRUE = frozenset({"true", "yes", "on", "1"})
_RECOGNIZED_FALSE = frozenset({"false", "no", "off", "0"})
# Already valid for ``xs:boolean`` — normalizing these would be a spurious edit.
_ALREADY_CANONICAL = frozenset({"true", "false", "1", "0"})


@dataclass
class BooleanNormalization:
    """One boolean attribute value to rewrite to its canonical ``xs:boolean`` form."""

    line: int
    element: str
    attribute: str
    found: str
    suggested: str

    def __str__(self) -> str:
        return (
            f"line {self.line}, <{self.element}>: non-canonical boolean "
            f"{self.attribute}='{self.found}' — normalize to '{self.suggested}'"
        )


def normalize_boolean_token(value: str, /) -> str | None:
    """Canonical ``true``/``false`` for a recognized boolean spelling, else ``None``.

    Returns ``None`` when *value* is already a valid ``xs:boolean`` literal
    (``true``/``false``/``1``/``0`` — no change needed) or is not a recognized
    boolean spelling at all (left for typo handling). The mapping mirrors
    Galaxy's ``string_as_bool`` so the rewrite never changes runtime behaviour.
    """
    if value in _ALREADY_CANONICAL:
        return None
    lowered = value.lower()
    if lowered in _RECOGNIZED_TRUE:
        return "true"
    if lowered in _RECOGNIZED_FALSE:
        return "false"
    return None


def _enum_values(resolved: object) -> tuple[str, ...] | None:
    """The string values of *resolved* if it is an ``enum.Enum`` subclass."""
    if isinstance(resolved, type) and issubclass(resolved, enum.Enum):
        return tuple(str(member.value) for member in resolved)
    return None


def _field_is_boolean(hint: object) -> bool:
    """Whether a model field's type hint denotes a boolean attribute.

    True when the union includes ``bool`` (xsdata's strict boolean) or an enum
    whose every value is a recognized boolean literal (xsdata's permissive
    boolean enum, e.g. ``{"true", "false", "True", "False", "yes", ...}``).
    """
    args = (
        typing.get_args(hint)
        if typing.get_origin(hint) in (types.UnionType, typing.Union)
        else (hint,)
    )
    for arg in args:
        if arg is bool:
            return True
        values = _enum_values(arg)
        if values is not None and all(
            v.lower() in (_RECOGNIZED_TRUE | _RECOGNIZED_FALSE) for v in values
        ):
            return True
    return False


def _dataclass_or_none(resolved: object) -> type | None:
    """Return *resolved* if it is a dataclass type, else ``None``."""
    if isinstance(resolved, type) and dataclasses.is_dataclass(resolved):
        return resolved
    return None


@dataclass(frozen=True)
class _ClassVocabulary:
    """The boolean attribute names and child-element classes of one model class."""

    boolean_attributes: frozenset[str]
    elements: dict[str, type | None]


@cache
def _class_vocabulary(model_class: type) -> _ClassVocabulary:
    """Introspect a model class for its boolean attributes and children (cached)."""
    hints = typing.get_type_hints(model_class)
    boolean: set[str] = set()
    elements: dict[str, type | None] = {}
    for model_field in dataclasses.fields(model_class):
        kind = model_field.metadata.get("type")
        xml_name = model_field.metadata.get("name") or model_field.name
        if kind == "Attribute":
            if _field_is_boolean(hints.get(model_field.name)):
                boolean.add(xml_name)
        elif kind == "Element":
            origin = typing.get_origin(hints.get(model_field.name))
            args = typing.get_args(hints.get(model_field.name))
            candidates = args if origin is not None else (hints.get(model_field.name),)
            elements[xml_name] = next(
                (cls for arg in candidates if (cls := _dataclass_or_none(arg))), None
            )
    return _ClassVocabulary(boolean_attributes=frozenset(boolean), elements=elements)


def _walk(
    element: etree._Element,
    model_class: type,
    normalizations: list[BooleanNormalization],
) -> None:
    """Descend the tree and model classes together, collecting normalizations."""
    vocabulary = _class_vocabulary(model_class)
    for name in vocabulary.boolean_attributes:
        value = element.get(name)
        if value is None:
            continue
        suggested = normalize_boolean_token(value)
        if suggested is not None:
            normalizations.append(
                BooleanNormalization(
                    line=element.sourceline or 0,
                    element=str(element.tag),
                    attribute=name,
                    found=value,
                    suggested=suggested,
                )
            )
    for child in element:
        if not isinstance(child.tag, str) or child.tag in _MACRO_ELEMENTS:
            continue
        child_class = vocabulary.elements.get(child.tag)
        if child_class is not None:
            _walk(child, child_class, normalizations)


def suggest_boolean_normalizations(
    target: Source | ToolDocument, *, profile: str | None = None
) -> list[BooleanNormalization]:
    """Return the boolean-attribute value rewrites that would canonicalize a tool.

    ``target`` is a source (path, ``bytes``, or binary stream) or a parsed
    ``ToolDocument``. ``profile`` overrides the schema vocabulary used for the
    lockstep walk — a repair tool probing each release passes the target version
    here (an attribute is ``xs:boolean`` only under some profiles). Returns an
    empty list when the source cannot be parsed.
    """
    document = (
        target if isinstance(target, ToolDocument) else parse_tool(target).document
    )
    if document is None:
        return []
    chosen = profile if profile is not None else document.profile
    normalizations: list[BooleanNormalization] = []
    _walk(document.root, tool_class(resolve_profile(chosen)), normalizations)
    return normalizations
