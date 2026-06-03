"""MCP server exposing the Galaxy tool refactoring facade to AI agents.

``service`` is the protocol-agnostic adapter (facade → JSON-serialisable dicts);
``server`` binds it to FastMCP. See ``docs/decisions.md`` D1.
"""
