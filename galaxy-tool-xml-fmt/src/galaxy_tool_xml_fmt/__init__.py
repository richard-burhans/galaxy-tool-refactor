"""Opinionated formatter for Galaxy tool XML.

Tier 3 of the Galaxy tool refactoring architecture (see ``README.md``).
The package follows the dignified-python rule against re-exports: the
public surface is the modules themselves, not symbols hoisted to the
top level. Callers import ``format_tool_document`` from
``galaxy_tool_xml_fmt.format`` directly.
"""
