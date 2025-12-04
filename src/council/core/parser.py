"""Tree Sitter parser integration for multi-language support."""

import logfire
import tree_sitter_go
import tree_sitter_java
import tree_sitter_javascript
import tree_sitter_python
import tree_sitter_typescript
from tree_sitter import Language, Parser, Tree

# Map file extensions to Tree Sitter languages
# Note: Typescript has two grammars: typescript and tsx
LANGUAGE_MAP = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "tsx",
    ".java": "java",
    ".go": "go",
}


class CodeParser:
    """Handles parsing of code using Tree Sitter."""

    def __init__(self):
        """Initialize parsers for supported languages."""
        self._languages = {}
        self._parsers = {}
        self._init_languages()

    def _init_languages(self):
        """Initialize Tree Sitter languages."""
        try:
            # Python
            self._languages["python"] = Language(tree_sitter_python.language())

            # JavaScript
            self._languages["javascript"] = Language(tree_sitter_javascript.language())

            # TypeScript
            self._languages["typescript"] = Language(tree_sitter_typescript.language_typescript())
            self._languages["tsx"] = Language(tree_sitter_typescript.language_tsx())

            # Java
            self._languages["java"] = Language(tree_sitter_java.language())

            # Go
            self._languages["go"] = Language(tree_sitter_go.language())

        except Exception as e:
            logfire.error("Failed to initialize Tree Sitter languages", error=str(e))
            # We don't raise here to allow partial initialization or fallback behavior

    def get_parser(self, language_name: str) -> Parser | None:
        """
        Get a parser for the specified language.

        Args:
            language_name: Name of the language (e.g., 'python', 'javascript')

        Returns:
            Parser instance or None if language not supported
        """
        if language_name not in self._languages:
            return None

        if language_name not in self._parsers:
            parser = Parser(self._languages[language_name])
            self._parsers[language_name] = parser

        return self._parsers[language_name]

    def get_language(self, language_name: str) -> Language | None:
        """Get the Language object for a given language name."""
        return self._languages.get(language_name)

    def parse(self, code: str, file_extension: str) -> tuple[Tree | None, str]:
        """
        Parse code based on file extension.

        Args:
            code: Source code to parse
            file_extension: File extension (e.g., '.py', '.ts')

        Returns:
            Tuple of (Tree object or None, language name used)
        """
        language_name = LANGUAGE_MAP.get(file_extension.lower())
        if not language_name:
            return None, "unknown"

        parser = self.get_parser(language_name)
        if not parser:
            return None, language_name

        try:
            # Tree Sitter expects bytes
            tree = parser.parse(bytes(code, "utf8"))
            return tree, language_name
        except Exception as e:
            logfire.error("Tree Sitter parsing failed", extension=file_extension, error=str(e))
            return None, language_name


# Global instance
_parser_instance = None


def get_code_parser() -> CodeParser:
    """Get global CodeParser instance."""
    global _parser_instance
    if _parser_instance is None:
        _parser_instance = CodeParser()
    return _parser_instance
