# galaxy-tool-source

A Python library and small CLI for parsing, profile-aware validation, and typed
inspection of [Galaxy](https://galaxyproject.org/) tool definition XML — the
`<tool>` wrapper files that define Galaxy bioinformatics tools.

This package is the **foundation** for a separate, `black`-like program for
Galaxy tool XML (conformance checking, autofixing, reformatting). It provides
only the foundation — no rules, no formatter, no serializer:

1. **Parse** tool XML into a mutable representation that faithfully preserves
   CDATA, comments, attribute data and order, and significant element text.
2. A **typed read-only view** of a parsed tool — bound to the model for the
   tool's own schema profile — for convenient rule-checking.
3. **Profile-aware XSD validation**, with configurable macro handling so
   validation is accurate on real-world tools that use Galaxy macros.
4. **Near-miss typo suggestions** against the schema vocabulary (suggest only).

## Install

```sh
uv sync
```

## Usage

```python
from galaxy_tool_source.binding import load_tool, validate_tool

document = load_tool("my_tool.xml")
print(document.profile)

result = validate_tool("my_tool.xml")
if not result.valid:
    for error in result.errors:
        print(error)
```

From the command line:

```sh
uv run galaxy-tool-source validate my_tool.xml
uv run galaxy-tool-source suggest my_tool.xml
uv run galaxy-tool-source profiles
```

## Public API

The downstream formatter project may rely on exactly these symbols. Everything
else is private and may change without notice.

```python
from galaxy_tool_source.binding import load_tool, parse_tool, validate_tool, newest_valid_profile
from galaxy_tool_source.binding import load_macros
from galaxy_tool_source.binding import ParseResult, ValidationResult, XmlError, ToolXmlSyntaxError
from galaxy_tool_source.document import ToolDocument, MacroDocument
from galaxy_tool_source.macros import MacroError, imported_macro_paths, token_definitions, TokenDefinition, expanded_detection_root
from galaxy_tool_source.corrections import suggest_corrections, Correction
from galaxy_tool_source.boolean_values import suggest_boolean_normalizations, normalize_boolean_token, BooleanNormalization
from galaxy_tool_source.cheetah_refs import tool_cheetah_references, CheetahRef
from galaxy_tool_source.cheetah_rename import rename_param, rename_param_plan, RenameOutcome, RenameEdit, RenamePlan
from galaxy_tool_source.bundle import ToolBundle, load_bundle, rename_param_in_bundle, BundleRenameOutcome
from galaxy_tool_source.profiles import available_profiles, latest_profile, UnknownProfileError
from galaxy_tool_source.schema_content import text_bearing_tags
from galaxy_tool_source.models.registry import model_module, tool_class
from galaxy_tool_source.models.any_tool import AnyTool
```

## Architecture

`ToolDocument` (`document.py`) wraps a mutable lxml tree — the source of truth,
faithfully preserving CDATA, comments, and attribute order. `binding.py` parses
and validates; `profiles.py` resolves the per-release vendored XSD; `macros.py`
handles Galaxy macros (the sole `galaxy-util` adapter); `corrections.py` suggests
near-miss typo fixes; `boolean_values.py` reports schema-boolean attribute value
normalizations (`True` → `true`); `cheetah_refs.py` / `cheetah_rename.py` find and
rename a parameter across a tool's Cheetah sections (the latter renders the rename
either as a tree mutation, `rename_param`, or as minimal source offsets,
`rename_param_plan`, for editor / LSP use); `bundle.py` extends the rename across a
tool *and its imported macro files* (`ToolBundle` / `load_bundle` /
`rename_param_in_bundle`); `rst.py` / `rst_markdown.py` own the `<help>`
reStructuredText subsystem — validity + surgical repair (the GTR089 partition seam)
and the render-equivalence-gated RST → Markdown conversion (GTR092; needs the
`[markdown]` extra); `models/` holds an xsdata-generated
read-only typed model for every vendored schema version, reached via
`ToolDocument.model()`.

## License

MIT — see [LICENSE](LICENSE).
