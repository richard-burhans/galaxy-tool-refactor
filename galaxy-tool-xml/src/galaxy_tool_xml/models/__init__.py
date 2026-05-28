"""Per-version xsdata-generated typed models of the Galaxy tool schema.

Each vendored XSD version has its own generated package here (``v16_10`` …
``v26_0``), produced at build time by ``galaxy_tool_xml._codegen`` and not
committed. Resolve a version to its model package or ``Tool`` class through
``galaxy_tool_xml.models.registry``; the ``AnyTool`` union over every version
lives in ``galaxy_tool_xml.models.any_tool``.

This package intentionally exposes no re-exports here.
"""
