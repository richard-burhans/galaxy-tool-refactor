"""Advisory (detect-only) IUC best-practice checks for Galaxy tool XML (tier 3.5).

Public surface is reached by explicit submodule imports (no re-exports):
``galaxy_tool_lint.rules.CheckRule``, ``galaxy_tool_lint.detect``
(``all_checks`` / ``detect_violations`` / ``sort_violations`` — the last a shared
``(sourceline, code)`` sort the tier-3.6 facade reuses), and the concrete rules in
``galaxy_tool_lint.checks``.
"""
