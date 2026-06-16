"""Unified, code-addressable rule registry + rulesets for the refactor tiers (tier 3.6).

Public surface is reached by explicit submodule imports (no re-exports):

- ``galaxy_tool_refactor_registry.facade`` — the library-first, structured entry
  points: ``run`` / ``upgrade`` / ``detect`` / ``find_references`` /
  ``rename_param`` / ``convert_help`` / ``tokenize_version`` /
  ``reconcile_lint_skip``, the single-source canonical-form primitives
  ``is_canonical`` / ``fired_codes`` (shared with the auto-fix gate and coverage
  tracker), and the introspection ``list_rulesets`` / ``list_rules``.
- ``galaxy_tool_refactor_registry.registry`` — ``registry`` / ``by_code`` /
  ``advisory_codes`` / ``known_codes`` over the unified ``code -> RuleHandle`` map;
  ``galaxy_tool_refactor_registry.resolve`` — ``resolve_codes``.
- ``galaxy_tool_refactor_registry.rulesets`` — the named ruleset code sets (derived).
- ``galaxy_tool_refactor_registry.handle`` / ``.results`` / ``.errors`` — the
  ``RuleHandle`` and structured result / error types.

The package is library-first: no ``click``/``sys.exit`` in the call path, and it
writes to disk only when a caller explicitly passes a ``write_path``. That keeps
it the shared core both the ``galaxy-tool-refactor`` CLI and the MCP server
sit on top of (see ``galaxy-tool-refactor-mcp/docs/vision.md``).
"""
