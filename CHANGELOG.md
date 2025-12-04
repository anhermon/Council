# Changelog

All notable changes to The Council will be documented in this file.

## [Unreleased]

### Core Features

#### Code Review Engine
- **Initial Release** (Dec 4, 2025): Core code review capabilities with deep context analysis using Repomix
- **Multi-language Support** (Dec 4, 2025): Enhanced import detection for JavaScript, TypeScript, and Java using improved Tree Sitter queries
- **Directory Reviews** (Dec 4, 2025): Fixed directory handling to recursively scan code files and extract language topics from file extensions
- **Diff-based Reviews** (Dec 4, 2025): Added support for reviewing only changed code compared to git references
- **Phase-specific Reviews** (Dec 4, 2025): Added ability to run specific review phases (security, performance, maintainability, best_practices)
- **Uncommitted Changes Review** (Dec 4, 2025): Added support for reviewing uncommitted changes

#### Knowledge Base & Learning
- **Documentation Learning** (Dec 4, 2025): Initial knowledge base learning from documentation URLs via Jina Reader
- **Knowledge Discovery** (Dec 4, 2025): Added `learn:prompt` task and automated knowledge discovery script for generating system prompts
- **Knowledge Files** (Dec 4, 2025): Added knowledge files for Ruff linting, Pytest testing, and Python 3.12 features

#### CLI Interface
- **Initial CLI** (Dec 4, 2025): Basic CLI interface for reviews, learning, and housekeeping
- **Modular CLI Architecture** (Dec 4, 2025): Refactored CLI into modular structure with separate commands, core, UI, and utils modules
- **Context Command** (Dec 4, 2025): Added context command with output format options (JSON/Markdown) for external agent integration
- **Output Formats** (Dec 4, 2025): Added multiple output formats (JSON, Markdown, Pretty) for review results
- **Validation Utilities** (Dec 4, 2025): Extracted constants and validation utilities for better code organization

#### Tool Modules
- **Core Tools** (Dec 4, 2025): Added tool modules for exceptions, metrics, persistence, repomix, and validation
- **Repomix Integration** (Dec 4, 2025): Integrated Repomix module for comprehensive code context extraction
- **Git Tools** (Dec 4, 2025): Added git integration tools for diff extraction and commit operations
- **Debug Tools** (Dec 4, 2025): Added debugging support tools

#### Security & Quality
- **Path Validation** (Dec 4, 2025): Added path validation to prevent path traversal attacks in cache operations
- **Security Hooks** (Dec 4, 2025): Enhanced pre-commit hooks with Bandit, detect-secrets, and safety checks
- **XSS Protection** (Dec 4, 2025): Fixed Jinja2 XSS vulnerability by enabling autoescape
- **Code Quality Hooks** (Dec 4, 2025): Added check-ast, check-docstring-first, and commit message linting

#### Testing & Coverage
- **Initial Test Suite** (Dec 4, 2025): Added comprehensive test suite with integration tests for review flow
- **Test Coverage Expansion** (Dec 4, 2025): Expanded test coverage across CLI commands, tools, and core functionality (reached 74% coverage)
- **Multi-language Test Support** (Dec 4, 2025): Added tests for code analysis and git tools with multi-language support

#### Developer Experience
- **Taskfile Integration** (Dec 4, 2025): Added comprehensive Taskfile.yaml with project lifecycle commands
- **Cursor Agent Integration** (Dec 4, 2025): Added Taskfile tasks for running Cursor Agent with generated context (single file, multiple files, project-wide, diff-based, and phase-specific reviews)
- **CI/CD Workflow** (Dec 4, 2025): Added GitHub Actions CI workflow
- **Pre-commit Hooks** (Dec 4, 2025): Set up pre-commit hooks with ruff for code quality

#### Performance & Reliability
- **Cache Optimization** (Dec 4, 2025): Optimized lock usage in repomix cache to minimize contention
- **Error Handling** (Dec 4, 2025): Improved error handling with specific exception types and fallback logic for git operations
- **Import Detection** (Dec 4, 2025): Improved accuracy using AST parsing for Python imports

#### Documentation
- **Project Documentation** (Dec 4, 2025): Added README with comprehensive usage documentation
- **Context Command Docs** (Dec 4, 2025): Updated README with context command documentation
- **Project Structure** (Dec 4, 2025): Updated project context documentation with accurate file structure
- **Changelog** (Dec 4, 2025): Added this changelog for tracking project changes

---

## Feature Timeline

### December 4, 2025

**Morning (00:31 - 01:35)**
- Initial project setup with MCP server functionality
- Core tool modules (exceptions, metrics, persistence, repomix, validation)
- Repomix integration for code context extraction
- Integration tests for review flow
- GitHub Actions CI workflow
- Basic pre-commit hooks setup

**Mid-Morning (01:59 - 02:16)**
- Comprehensive test suite expansion
- Tests for code analysis and git tools
- Test coverage improvements

**Afternoon (12:25 - 13:25)**
- CLI modular architecture refactoring
- Context command with output formats
- Path validation and security enhancements
- Enhanced pre-commit hooks (security and quality checks)
- Multi-language analysis improvements
- Test coverage expansion (reached 72-74%)

**Late Afternoon (13:26 - 14:03)**
- Cursor Agent integration tasks
- Context command enhancements
- Directory handling fixes
- Knowledge discovery script
- Changelog documentation
