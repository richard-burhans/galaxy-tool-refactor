"""Advisory (detect-only) IUC best-practice checks for Galaxy tool XML (tier 3.5).

Public surface is reached by explicit submodule imports (no re-exports):
``galaxy_tool_xml_check.rules.CheckRule``, ``galaxy_tool_xml_check.detect``
(``all_checks`` / ``detect_violations``), and the concrete rules in
``galaxy_tool_xml_check.checks``.
"""
