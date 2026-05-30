# galaxy-tool-xml-check

The **advisory check** tier (tier 3.5) of the Galaxy tool refactoring framework:
read-only IUC best-practice checks that *report* but never mutate.

Where the codemod (tier 2) and fmt (tier 3) tiers *fix* a tool (their detect
phases report what their fix would change), this tier covers the
[IUC `tool_xml` best-practices][iuc] that are **not** safely auto-fixable — they
need a content or semantic decision (add tests, declare requirements, write
help). Each check is a `RuleMeta`-coded, `detect_only=True` rule that yields the
shared tier-0.5 `Violation`. The findings are **advisory**: the
`galaxy-tool-refactor check` command shows them but, by default, does not fail on
them (use `--strict` to gate on them too).

[iuc]: https://galaxy-iuc-standards.readthedocs.io/en/latest/best_practices/tool_xml.html

## Scope

Depends only on tier 1 (`galaxy-tool-xml`, the parsed `ToolDocument` and
profile helpers) and tier 0.5 (`galaxy-tool-refactor-rules`, `RuleMeta` /
`Violation`). It does **not** depend on the mutating tiers — the app
(`galaxy-tool-refactor-cli`) composes this alongside them.

```python
from galaxy_tool_xml.binding import load_tool
from galaxy_tool_xml_check.detect import detect_violations

for violation in detect_violations(load_tool("my_tool.xml")):
    print(violation.code, violation.message)
```

## Checks

See `galaxy_tool_xml_check.checks` and the IUC coverage map at
`../docs/iuc_best_practices.md`. The two `<command>`-CDATA-text heuristics
(single-quoted Cheetah variables, `&&`-vs-lone-`&` command joining) are
**reserved placeholders** (`IUC011` / `IUC012`) — registered but not yet
implemented, pending careful tuning to avoid noise.
