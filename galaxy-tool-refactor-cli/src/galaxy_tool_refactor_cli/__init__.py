"""Top-level CLI app for the Galaxy tool refactoring framework.

Tier 4 (the app layer): a thin front-end over the registry facade. Orchestration
lives in the tier-3.6 facade (``galaxy-tool-refactor-registry``), which composes
the lower tiers; this package depends on that facade plus fmt's ``cli_support``
file-walking engine (tier 3) and tier-1 parsing — **not** on the codemod tier
directly (cli `docs/decisions.md` D4). It exposes the ``galaxy-tool-refactor`` CLI
with eleven author-facing commands (plus one hidden CI helper, ``gate-suggest`` —
cli §D20):

- ``format`` — structural canonicalisation + cosmetic formatting (safe,
  idempotent; never changes ``profile=``).
- ``upgrade`` — opt-in repair + profile upgrade to the latest reachable profile.
- ``check`` — report-only linter over the selected rules' detect phases.
- ``find-references`` — read-only query: a parameter's Cheetah ``$var`` reference
  sites across a tool's templated sections (cli §D8).
- ``rename-param`` — mutating sibling of ``find-references``: rename a parameter
  across the tool and its imported macro bundle (cli §D9–§D11).
- ``rulesets`` / ``rules`` — introspect the baked-in rulesets and rules.
- ``normalize-macros`` — opt-in, repo-scoped: lowercase literal ``format``/``ftype``
  in ``<macros>``-root files (never part of ``format``/``upgrade``; cli §D7).
- ``convert-help`` — opt-in: convert an RST ``<help>`` to Markdown when provable
  (GTR092; cli §D12).
- ``tokenize-version`` — opt-in: factor a literal version into
  ``@TOOL_VERSION@``/``@VERSION_SUFFIX@`` tokens when provable (GTR094; cli §D13).
- ``lint-skip`` — opt-in: prune a planemo ``.lint_skip`` sidecar's suppression lines
  only when the toolchain can prove each resolved (cli §D19).

Per dignified-python there are no re-exports; import from
``galaxy_tool_refactor_cli.cli`` directly.
"""
