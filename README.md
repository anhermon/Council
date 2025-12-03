# The Council - AI Code Review MCP Server

An autonomous code quality gate that acts as a local MCP Server, providing AI-powered code reviews through FastMCP, Pydantic-AI, Repomix, and Jina Reader.

## Features

- **Deep Context Analysis**: Uses Repomix to extract comprehensive code context (XML format)
- **Dynamic Knowledge Base**: Learn from documentation via Jina Reader and automatically apply standards
- **Structured Output**: Pydantic-AI ensures type-safe, structured review results
- **MCP Integration**: Exposes tools via FastMCP for use in Cursor, VS Code, and other MCP-compatible editors

## Architecture

- **Server Layer**: FastMCP for MCP protocol implementation
- **Logic Layer**: Pydantic-AI for structured, type-safe AI outputs
- **Context Layer**: Repomix wrapper for deep code context extraction
- **Knowledge Layer**: Jina Reader integration for documentation fetching

## Setup

### Prerequisites

- Python 3.12+
- [uv](https://github.com/astral-sh/uv) package manager
- OpenAI API key (or other compatible model provider)

### Installation

1. Clone or navigate to the project directory:
```bash
cd council
```

2. Install dependencies using uv:
```bash
uv sync
```

3. Create a `.env` file with your API keys:

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

When using LiteLLM, the model name should match what's configured in your LiteLLM proxy (e.g., `sonnet-4`, `gpt-4`, `custom/my-model`). The `COUNCIL_MODEL` environment variable is required and must be set.

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

The Council provides a CLI interface for direct code reviews:

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

### First Steps

1. Teach The Council some best practices:
```python
learn_rules("https://docs.anthropic.com/en/docs/build-with-claude/prompt-engineering/system-prompts", "prompt_engineering")
```

2. Review your code:
```python
review_code("path/to/your/file.py")
```

## Project Structure

```
the-council/
├── pyproject.toml          # Dependencies and project config
├── .env                    # API keys (create this)
├── knowledge/              # Dynamic knowledge base (.md files)
│   └── .keep
└── src/
    └── council/
        ├── __init__.py
        ├── main.py         # FastMCP server entry point
        ├── cli.py          # CLI interface
        ├── config.py        # Settings & path constants
        ├── templates/
        │   └── system_prompt.j2  # Jinja2 template for system prompt
        ├── agents/
        │   ├── __init__.py
        │   └── councilor.py # Pydantic-AI reviewer agent
        └── tools/
            ├── __init__.py
            ├── scribe.py    # Jina Reader wrapper
            └── context.py   # Repomix wrapper
```

## Configuration

### Environment Variables

Create a `.env` file and configure your API keys:

- **Direct Provider**: Set `OPENAI_API_KEY` (or `ANTHROPIC_API_KEY`, etc.) and optionally `COUNCIL_MODEL`
- **LiteLLM Proxy**: Set `LITELLM_BASE_URL` and `LITELLM_API_KEY` for custom model routing

The `COUNCIL_MODEL` environment variable is required and must be set. When using LiteLLM, this should match your LiteLLM proxy configuration. When using direct providers, use the format `provider:model-name` (e.g., `openai:gpt-4o`, `anthropic:claude-3-5-sonnet-20241022`).

### Repomix Configuration

Repomix is configured via command-line flags. You can customize which files are included by modifying the `get_packed_context` function in `src/council/tools/context.py` if needed.

### Knowledge Base

The `knowledge/` directory stores markdown files that are automatically loaded into the system prompt. Files are loaded in alphabetical order and injected as "RULESET" sections. Use the `learn_rules` tool to populate this directory automatically.

## Development

### Dependencies

- `fastmcp`: MCP server framework
- `pydantic-ai`: Type-safe AI agent framework
- `httpx`: HTTP client for Jina Reader
- `logfire`: Structured logging
- `devtools`: Development utilities

### Running Tests

(Add test instructions when tests are implemented)

## License

(Add license information)

