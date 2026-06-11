from __future__ import annotations

import sys
from collections import defaultdict
from collections.abc import Mapping
from pathlib import Path
import importlib.metadata

import click
from galaxy_tool_fmt.cli_support import (
    Action,
    RunOptions,
    TransformOutcome,
    is_macros_root,
    is_tool_root,
    iter_targets,
    make_backup,
    run,
)
from galaxy_tool_fmt.detect import detect_macro_document
from galaxy_tool_fmt.format import fo

@click.group()
@click.version_option(version=importlib.metadata.version("galaxy-tool-refactor-cli"))
def main():
    """The ``galaxy-tool-refactor`` command-line interface.

    Ten subcommands (including the two opt-in conversions, ``convert-help`` and
    ``tokenize-version``). ``format`` and ``upgrade`` share fmt's file-walking /
    drift-detection engine (``galaxy_tool_fmt.cli_support``) and differ only in
    which rules run before serialisation; ``check`` is a report-only linter that
    mutates nothing; ``find-references`` is a read-only query for a parameter's Cheetah
    ``$var`` reference sites and ``rename-param`` is its mutating sibling (rename a
    parameter across those sites); ``rules`` / ``rulesets`` print the available baked-in
    rules and rulesets; ``normalize-macros`` is a separate, opt-in pass over macro-library
    files. All rule orchestration is delegated to the tier-3.6 registry facade
    (``galaxy_tool_refactor_registry``); this module only does CLI plumbing.

    - ``format`` — apply a ruleset's (or a ``--select``/``--ignore`` selection's)
      fixable rules then cosmetic formatting. Safe and idempotent; never changes
      ``profile=``. Default ruleset ``default`` reproduces the historical behaviour.
      Macro-library files (``<macros>`` root) are also cosmetically formatted
      (kind-applicable rules only — no codemods).
    - ``upgrade`` — repair, then iteratively upgrade ``profile=`` toward the latest
      (applying the registered migration each step), then format. Opt-in and
      semantic; rulesets do not apply (``--select``/``--ignore`` adjust its rule set).
      Also bumps an imported ``@PROFILE@`` token in place when every profile-using
      importer in the run agrees on the target (else reports and skips); a
      ``profile="@TOKEN@"`` whose token is inline is handled per-file by GTR007.
    - ``check`` — report where tools deviate from the selection, one
      ``file:line  CODE  message`` per finding, without changing anything. Fixable
      findings fail the run; advisory (``detect_only``) findings are informational
      unless ``--strict``. Macro files are checked for cosmetic (fixable) drift too.
    - ``find-references`` — read-only query: print every Cheetah ``$NAME`` reference site
      (``file:line  [section]  $ref``) across a tool's templated sections. Mutates nothing,
      not a rule (no selection); the first read-only consumer of the Cheetah reference model
      (``galaxy_tool_source.cheetah_refs``). See ``docs/decisions.md`` §D8.
    - ``rename-param`` — the mutating sibling of ``find-references``: rename a parameter
      OLD to NEW across every Cheetah section, by-name cross-reference attribute, and
      ``<tests>`` mirror, plus the definition. Atomic per file (rewrites everything or skips
      with a reason); ``--check`` previews. Built on the faithful CDM lexer (M5.3); see
      ``docs/decisions.md`` §D9.
    - ``rules`` / ``rulesets`` — introspection: the baked-in rules and the rulesets.
    - ``normalize-macros`` — opt-in, repo-scoped: lowercase literal ``format`` /
      ``ftype`` in ``<macros>``-root files (the macro-library analog of the 24.2
      normalization the per-tool ``upgrade`` cannot reach — a value defined in an
      imported macro file). It rewrites files other than the one named (a shared
      macro file affects every importer), so it is never folded into ``format`` /
      ``upgrade``; see ``galaxy-tool-codemod/docs/macro-aware-normalization.md``.

    Selection (``--ruleset`` / ``--select`` / ``--ignore``) is shared by ``format``,
    ``upgrade`` (no ``--ruleset``), and ``check``; precedence is ruff-style
    (``--ignore`` ▸ ``--select`` ▸ ``--ruleset``, where ``--ruleset`` unions the named
    sets and ``--select`` replaces them).
    """