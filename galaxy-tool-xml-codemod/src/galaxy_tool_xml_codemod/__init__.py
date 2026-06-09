"""LibCST-shaped framework for structural refactors of Galaxy tool XML.

Tier 2 of the Galaxy tool refactoring architecture (see ``README.md``).
Per dignified-python this package does not re-export from its
submodules — import the symbols you need directly:

    from galaxy_tool_xml_codemod.parse import parse_module
    from galaxy_tool_xml_codemod.canonical import canonical_codemods
    from galaxy_tool_xml_codemod.module import Module
    from galaxy_tool_xml_codemod.cursor import Cursor
    from galaxy_tool_xml_codemod.codemod import CodemodCommand
"""
