"""Top-level CLI app for the Galaxy tool refactoring framework.

Tier 4 (the app layer): a thin front-end over the registry facade. Orchestration
lives in the tier-3.6 facade (``galaxy-tool-refactor-registry``), which composes
the lower tiers; this package depends on that facade plus fmt's ``cli_support``
file-walking engine (tier 3) and tier-1 parsing — **not** on the codemod tier
directly (cli `docs/decisions.md` D4). It exposes the ``galaxy-tool-refactor`` CLI
with seven commands:

- ``format`` — structural canonicalisation + cosmetic formatting (safe,
  idempotent; never changes ``profile=``).
- ``upgrade`` — opt-in repair + profile upgrade to the latest reachable profile.
- ``check`` — report-only linter over the selected rules' detect phases.
- ``find-references`` — read-only query: a parameter's Cheetah ``$var`` reference
  sites across a tool's templated sections (cli §D8).
- ``presets`` / ``rules`` — introspect the baked-in presets and rules.
- ``normalize-macros`` — opt-in, repo-scoped: lowercase literal ``format``/``ftype``
  in ``<macros>``-root files (never part of ``format``/``upgrade``; cli §D7).

Per dignified-python there are no re-exports; import from
``galaxy_tool_refactor_cli.cli`` directly.
"""
