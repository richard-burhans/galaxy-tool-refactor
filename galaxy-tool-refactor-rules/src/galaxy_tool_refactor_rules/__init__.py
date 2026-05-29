"""Shared rule-metadata vocabulary for the galaxy-tool-refactor tiers.

Tier 0.5 of the refactoring framework: a dependency-free home for the
``RuleMeta`` descriptor shared by the formatter (tier 3) and the codemod
framework (tier 2), plus a pure markdown render helper for rule glossaries.

Following the project's dignified-python conventions there are no re-exports;
callers import ``RuleMeta`` from ``galaxy_tool_refactor_rules.meta`` and
``render_rule_reference_table`` from ``galaxy_tool_refactor_rules.reference``
directly.
"""
