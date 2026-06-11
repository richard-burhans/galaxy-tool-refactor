# galaxy-tool-refactor

Front-door metapackage for the **galaxy-tool-refactor** toolkit — parse, lint,
format, and structurally upgrade [Galaxy](https://galaxyproject.org/) tool XML.

```bash
pip install galaxy-tool-refactor          # the galaxy-tool-refactor CLI
pip install "galaxy-tool-refactor[mcp]"   # + the agent-facing MCP server
```

This package installs no code of its own; it depends on
[`galaxy-tool-refactor-cli`](https://pypi.org/project/galaxy-tool-refactor-cli/)
(which provides the `galaxy-tool-refactor` command) and, via the `[mcp]` extra,
[`galaxy-tool-refactor-mcp`](https://pypi.org/project/galaxy-tool-refactor-mcp/).

For a minimal install of a single layer, depend on that package directly (e.g.
`galaxy-tool-source` for parsing/validation). See the
[project README](https://github.com/richard-burhans/galaxy-tool-refactor) for the
full package map and architecture.
