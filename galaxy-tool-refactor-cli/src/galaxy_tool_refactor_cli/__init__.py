"""Top-level CLI app for the Galaxy tool refactoring framework.

Tier 4 (the app layer): the only package that composes all the lower tiers
into a user-facing workflow. It depends on the codemod tier (tier 2) for
structural transforms and the fmt tier (tier 3) for cosmetic formatting and
serialization, and exposes the ``galaxy-tool-refactor`` CLI with five commands:

- ``format`` — structural canonicalisation + cosmetic formatting (safe,
  idempotent; never changes ``profile=``).
- ``upgrade`` — opt-in repair + profile upgrade to the latest reachable profile.
- ``check`` — report-only linter over the selected rules' detect phases.
- ``presets`` / ``rules`` — introspect the baked-in presets and rules.

Per dignified-python there are no re-exports; import from
``galaxy_tool_refactor_cli.cli`` directly.
"""
