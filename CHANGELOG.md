# Changelog

All notable changes to The Council will be documented in this file.

## [Unreleased]

### Added
- **Knowledge Discovery**: New `learn:prompt` task and automated knowledge discovery script for generating system prompts
- **Context Command Enhancements**: Added output format options (JSON/Markdown) and support for diff-based and phase-specific context extraction
- **Cursor Agent Integration**: New Taskfile tasks for running Cursor Agent with generated context (single file, multiple files, project-wide, diff-based, and phase-specific reviews)
- **Comprehensive Test Suite**: Added extensive test coverage across CLI commands, tools, and core functionality
- **Pre-commit Hooks**: Enhanced security and code quality checks including Bandit, detect-secrets, safety, commit message linting, and code quality validators

### Improved
- **CLI Architecture**: Refactored CLI into modular architecture with better command structure and validation utilities
- **Path Validation**: Enhanced security with path validation to prevent path traversal attacks in cache operations
- **Import Detection**: Improved accuracy using AST parsing for Python imports and better Tree Sitter queries for multi-language support
- **Error Handling**: Better error handling with specific exception types and improved fallback logic for git operations
- **Code Quality**: Fixed Jinja2 XSS vulnerability by enabling autoescape, improved code formatting, and enhanced linting rules

### Fixed
- **Directory Handling**: Fixed issue where knowledge base was empty when reviewing directories (now recursively scans for code files)
- **Test Fixtures**: Fixed test configuration and fixture errors across the test suite
- **Cache Operations**: Optimized lock usage in repomix cache to minimize contention
- **Security**: Fixed security vulnerabilities and improved path validation throughout the codebase

### Changed
- **Model Configuration**: Replaced global MODEL_NAME with lazy evaluation function for better flexibility
- **CLI Commands**: Consolidated commit command functionality and improved command organization
- **Documentation**: Updated README with context command documentation and improved project structure documentation

---

## [Initial Release]

### Added
- Initial project setup with MCP server functionality
- Code review capabilities with deep context analysis
- Knowledge base learning from documentation URLs
- CLI interface for reviews, learning, and housekeeping
- Integration with Repomix for code context extraction
- Jina Reader integration for documentation fetching
- GitHub Actions CI workflow
- Project logo and branding
