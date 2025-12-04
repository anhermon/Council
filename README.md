# The Council - AI Code Review MCP Server

![The Council](Council.png)

## What is The Council?

**The Council** is an autonomous AI-powered code review system that acts as a local MCP (Model Context Protocol) server. It provides intelligent, context-aware code reviews by analyzing your entire codebase, learning from documentation, and applying coding standards automatically.

### What it does:

- **Reviews your code** with deep context analysis using Repomix to understand your entire codebase
- **Learns coding standards** from documentation URLs and applies them to future reviews
- **Provides structured feedback** with severity assessments, issue detection, and suggested fixes
- **Integrates seamlessly** with Cursor, VS Code, and other MCP-compatible editors
- **Maintains code quality** through automated housekeeping and standardization

Think of it as your AI code reviewer that never sleeps, continuously learns, and understands your project's full context.

## Quickstart

### Installation

1. **Install dependencies:**
```bash
cd council
uv sync
```

2. **Configure your API keys** by creating a `.env` file:

**Option A: Direct OpenAI/Anthropic/etc. (default)**
```bash
OPENAI_API_KEY=your_openai_api_key_here
COUNCIL_MODEL=openai:gpt-4o  # or anthropic:claude-3-5-sonnet-20241022
```

**Option B: LiteLLM Proxy (recommended for custom models)**
```bash
LITELLM_BASE_URL=http://localhost:4000  # Your LiteLLM proxy URL
LITELLM_API_KEY=your_litellm_api_key
COUNCIL_MODEL=your-model-name  # Model name as configured in LiteLLM
```

> **Note:** The `COUNCIL_MODEL` environment variable is required. When using LiteLLM, match your proxy configuration. For direct providers, use format `provider:model-name` (e.g., `openai:gpt-4o`).

### Prerequisites

- Python 3.12+
- [uv](https://github.com/astral-sh/uv) package manager
- OpenAI API key (or other compatible model provider)

### Basic Usage

1. **Teach The Council some best practices:**
```bash
uv run council learn "https://docs.anthropic.com/en/docs/build-with-claude/prompt-engineering/system-prompts" prompt_engineering
```

2. **Review your code:**
```bash
uv run council review src/council/main.py
```

3. **Run housekeeping to maintain code quality:**
```bash
uv run council housekeeping
```

## Features

- **Deep Context Analysis**: Uses Repomix to extract comprehensive code context (XML format)
- **Dynamic Knowledge Base**: Learn from documentation via Jina Reader and automatically apply standards
- **Structured Output**: Pydantic-AI ensures type-safe, structured review results
- **MCP Integration**: Exposes tools via FastMCP for use in Cursor, VS Code, and other MCP-compatible editors

## Usage

### Running the MCP Server

Run the server directly:
```bash
uv run python -m src.council.main
```

Or use the CLI:
```bash
uv run council server
```

### CLI Commands

The Council provides a comprehensive CLI interface for code reviews and maintenance:

#### Review Code
```bash
uv run council review <file_path> [--output json|markdown|pretty] [--extra-instructions "instructions"]
```

**Examples:**
```bash
# Review a file with pretty output (default)
uv run council review src/council/main.py

# Get JSON output
uv run council review src/council/main.py --output json

# Review with extra instructions
uv run council review src/council/main.py --extra-instructions "Focus on security issues"

# Review multiple files or directories
uv run council review src/ tests/ config.py

# Review only uncommitted changes
uv run council review --uncommitted

# Review changes compared to a git reference
uv run council review --diff main src/
```

#### Learn Rules
```bash
uv run council learn <url> <topic>
```

**Example:**
```bash
uv run council learn "https://docs.anthropic.com/en/docs/build-with-claude/prompt-engineering/system-prompts" prompt_engineering
```

#### Run MCP Server
```bash
uv run council server
```

#### Housekeeping
Execute comprehensive codebase maintenance and cleanup:
```bash
uv run council housekeeping
```

This command runs a structured 4-phase protocol:
- **Phase 1**: Hygiene & Safety (gitignore audit, cleanup, dead code removal)
- **Phase 2**: Standardization & Quality (linting, formatting, DRY analysis)
- **Phase 3**: Documentation Alignment (docstring audit, README updates)
- **Phase 4**: Mental Map (project context documentation)

### MCP Tools

The server exposes two tools:

#### 1. `review_code(file_path: str)`

Reviews code at the given file path using Repomix for context extraction.

**Example:**
```python
review_code("src/council/main.py")
```

Returns a JSON object with:
- `summary`: Overall review summary
- `issues`: List of issues found (description, severity, line_number, code_snippet)
- `severity`: Overall severity assessment (low/medium/high/critical)
- `code_fix`: Optional suggested code fix

#### 2. `learn_rules(url: str, topic: str)`

Fetches documentation from a URL using Jina Reader and adds it to the knowledge base.

**Example:**
```python
learn_rules(
    "https://docs.anthropic.com/en/docs/build-with-claude/prompt-engineering/system-prompts",
    "prompt_engineering"
)
```

The knowledge is automatically loaded into future reviews.

## Architecture

- **Server Layer**: FastMCP for MCP protocol implementation
- **Logic Layer**: Pydantic-AI for structured, type-safe AI outputs
- **Context Layer**: Repomix wrapper for deep code context extraction
- **Knowledge Layer**: Jina Reader integration for documentation fetching

## Configuration

### Environment Variables

Create a `.env` file and configure your API keys:

- **Direct Provider**: Set `OPENAI_API_KEY` (or `ANTHROPIC_API_KEY`, etc.) and optionally `COUNCIL_MODEL`
- **LiteLLM Proxy**: Set `LITELLM_BASE_URL` and `LITELLM_API_KEY` for custom model routing

The `COUNCIL_MODEL` environment variable is required and must be set. When using LiteLLM, this should match your LiteLLM proxy configuration. When using direct providers, use the format `provider:model-name` (e.g., `openai:gpt-4o`, `anthropic:claude-3-5-sonnet-20241022`).

### Repomix Configuration

Repomix is configured via command-line flags. You can customize which files are included by modifying the `get_packed_context` function in `src/council/tools/repomix.py` if needed.

### Knowledge Base

The `knowledge/` directory stores markdown files that are automatically loaded into the system prompt. Files are loaded in alphabetical order and injected as "RULESET" sections. Use the `learn_rules` tool to populate this directory automatically.

## Project Structure

```
the-council/
├── pyproject.toml          # Dependencies and project config
├── .env                    # API keys (create this)
├── knowledge/              # Dynamic knowledge base (.md files)
│   └── .keep
├── ai_docs/                # AI agent context documentation
│   └── project_context.md  # Project mental map
└── src/
    └── council/
        ├── __init__.py
        ├── main.py         # FastMCP server entry point
        ├── cli.py          # CLI interface
        ├── config.py       # Settings & path constants
        ├── templates/
        │   └── system_prompt.j2  # Jinja2 template for system prompt
        ├── agents/
        │   ├── __init__.py
        │   └── councilor.py # Pydantic-AI reviewer agent
        └── tools/
            ├── __init__.py
            ├── scribe.py    # Jina Reader wrapper
            ├── context.py   # Repomix wrapper
            └── git_tools.py # Git integration tools
```

## Development

### Dependencies

- `fastmcp`: MCP server framework
- `pydantic-ai`: Type-safe AI agent framework
- `httpx`: HTTP client for Jina Reader
- `logfire`: Structured logging
- `devtools`: Development utilities

### Code Quality

The project uses Ruff for linting and formatting:

```bash
# Check and fix issues
uv run ruff check --fix src/

# Format code
uv run ruff format src/
```

### Running Tests

Tests are located in the `tests/` directory. Run them with:

```bash
# Run all tests
uv run pytest

# Run with verbose output
uv run pytest -v

# Run specific test file
uv run pytest tests/test_tools_path_utils.py

# Run integration tests (may require external tools)
uv run pytest tests/integration/ -m integration
```

## License

(Add license information)
