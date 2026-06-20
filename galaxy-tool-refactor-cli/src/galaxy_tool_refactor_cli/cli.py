"""The ``galaxy-tool-refactor`` command-line interface (the ``main`` group).

Eleven author-facing subcommands (including the two opt-in conversions,
``convert-help`` and ``tokenize-version``), plus one hidden CI helper,
``gate-suggest`` (the forward gate's suggest mode — see ``docs/forward_gate.md``;
the published Action calls it, so it ships in the package rather than as bundled
CI shell). Each command lives in its own module under the ``commands`` sub-package
(``commands/<x>.py``, each a standalone ``@click.command`` plus that command's
private helpers); this module only defines the ``main`` group and registers them.
Their shared option/argument decorators and the selection helpers live in
``galaxy_tool_refactor_cli.options``. All rule orchestration is delegated to the
tier-3.6 registry facade (``galaxy_tool_refactor_registry``); this package only
does CLI plumbing.

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

from __future__ import annotations

import click

from galaxy_tool_refactor_cli.commands.check import check_command
from galaxy_tool_refactor_cli.commands.convert_help import convert_help_command
from galaxy_tool_refactor_cli.commands.format import format_command
from galaxy_tool_refactor_cli.commands.gate_suggest import gate_suggest_command
from galaxy_tool_refactor_cli.commands.introspect import (
    rules_command,
    rulesets_command,
)
from galaxy_tool_refactor_cli.commands.lint_skip import lint_skip_command
from galaxy_tool_refactor_cli.commands.normalize_macros import (
    normalize_macros_command,
)
from galaxy_tool_refactor_cli.commands.references import find_references_command
from galaxy_tool_refactor_cli.commands.rename import rename_param_command
from galaxy_tool_refactor_cli.commands.tokenize_version import (
    tokenize_version_command,
)
from galaxy_tool_refactor_cli.commands.upgrade import upgrade_command


@click.group(context_settings={"help_option_names": ["-h", "--help"]})
@click.version_option(
    package_name="galaxy-tool-refactor-cli", prog_name="galaxy-tool-refactor"
)
def main() -> None:
    """Refactor Galaxy tool XML: structural codemods plus cosmetic formatting."""


main.add_command(format_command)
main.add_command(upgrade_command)
main.add_command(check_command)
main.add_command(find_references_command)
main.add_command(rename_param_command)
main.add_command(rulesets_command)
main.add_command(rules_command)
main.add_command(normalize_macros_command)
main.add_command(convert_help_command)
main.add_command(lint_skip_command)
main.add_command(tokenize_version_command)
main.add_command(gate_suggest_command)


if __name__ == "__main__":
    main()
