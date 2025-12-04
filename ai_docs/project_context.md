# Project Mental Map

## 1. Purpose & Core Logic

The Council is an AI-powered code review agent. It uses Repomix to extract comprehensive code context, Pydantic-AI for structured AI outputs, and Jina Reader to learn from documentation. The agent performs automated code reviews with severity assessments, issue detection, and suggested fixes. It can dynamically learn coding standards from documentation URLs and apply them to future reviews.

## 2. Tech Stack & Key Libraries

- Language: Python >=3.12
- Frameworks:
  - FastMCP (MCP server framework)
  - Pydantic-AI (type-safe AI agent framework)
  - Click (CLI framework)
- Key DB/Services: None (file-based knowledge storage)
- Critical Libs:
  - `repomix` (via uvx) - Code context extraction
  - `httpx` - HTTP client for Jina Reader API
  - `logfire` - Structured logging
  - `jinja2` - Template engine for system prompts
  - `python-dotenv` - Environment variable management

## 3. Architecture & Key Patterns

- **Architecture:** Dual-mode agent review system (CLI + MCP Server)
  - **CLI Layer**: Click commands (review, learn, context, housekeeping) - `cli/main.py`
  - **MCP Server Layer**: FastMCP server exposing tools as MCP endpoints - `main.py`
  - **Logic Layer**: Pydantic-AI agent (`councilor.py`) performs reviews
  - **Context Layer**: Repomix wrapper extracts code context as XML
  - **Knowledge Layer**: Jina Reader fetches docs, stored in `knowledge/` directory
- **State Management:** Stateless agent with lazy initialization (thread-safe singleton pattern)
- **Auth Pattern:** API keys via environment variables (OpenAI, LiteLLM proxy, or direct providers)

## 4. Operational Context

- **Run Locally:**
  - **MCP Server**: `uv run python -m council.main` or `uv run council server` (if command exists)
  - **CLI Review**: `uv run council review <file_path> [options]`
  - **Learn Rules**: `uv run council learn <url> <topic>`
  - **Get Context**: `uv run council context <file_path>` - Output review context for external agents
  - **Housekeeping**: `uv run council housekeeping`
- **Run Tests:** `uv run pytest` (tests in `tests/` directory)
- **Build/Deploy:**
  - Install: `uv sync`
  - Package: Standard Python packaging via `pyproject.toml` (hatchling backend)

## 5. File Structure Map

```
council/
├── pyproject.toml          # Project config, dependencies, Ruff linting config
├── README.md               # User-facing documentation
├── .gitignore              # Git ignore patterns
├── knowledge/              # Dynamic knowledge base (markdown files loaded into prompts)
│   └── .keep
├── ai_docs/                # AI agent context documentation
│   └── project_context.md  # This file
└── src/
    └── council/
        ├── __init__.py     # Package init, version
        ├── main.py         # FastMCP server entry point (MCP tools: review_code, learn_rules)
        ├── cli/
        │   ├── main.py     # Main CLI entry point (Click group)
        │   ├── commands/   # CLI commands (review, learn, context, housekeeping)
        │   ├── core/       # Core review execution and context building
        │   ├── ui/         # UI components (spinner, streaming, output)
        │   └── utils/      # Utility functions (paths, errors)
        ├── config.py       # Settings management, path resolution, env vars
        ├── templates/
        │   └── system_prompt.j2  # Jinja2 template for agent system prompt
        ├── agents/
        │   ├── __init__.py        # Agent exports
        │   └── councilor.py       # Core Pydantic-AI agent, model creation, knowledge loading
        └── tools/
            ├── __init__.py        # Tool exports
            ├── repomix.py         # Repomix integration, path validation, XML security checks
            ├── git_tools.py       # Git integration (diff, history, uncommitted files)
            └── scribe.py          # Jina Reader wrapper, URL validation, SSRF protection
```

## 6. Known Gotchas & Debugging

- **API Key Configuration:** Must set either `OPENAI_API_KEY` for direct providers OR `LITELLM_BASE_URL` + `LITELLM_API_KEY` for proxy. The `COUNCIL_MODEL` environment variable is required and must be set to specify which model to use. No hardcoded defaults - all configuration must come from environment variables.
- **Path Resolution:** Project root is auto-detected from `config.py` location. Can override with `COUNCIL_PROJECT_ROOT` env var if needed. Paths are validated for security (no path traversal, must be within project root or CWD).
- **Knowledge Base:** Markdown files in `knowledge/` are loaded alphabetically and injected into system prompt as "RULESET" sections. Files are loaded dynamically on each agent run.
- **Repomix Integration:** Runs via `uvx repomix` subprocess. Uses temporary XML files for output. Timeout is configurable via `COUNCIL_SUBPROCESS_TIMEOUT` (default 300s).
- **Template Loading:** Templates directory is resolved via `__file__` path or `importlib.resources` fallback. Must exist or runtime error occurs.
- **Security:** Extensive validation for path traversal, SSRF (URL validation), XXE (XML security checks), and command injection prevention in all user inputs.
- **Code Quality:** Project uses Ruff for linting and formatting. Run `uv run ruff check --fix src/` and `uv run ruff format src/` to maintain code quality. All linting issues should be resolved before committing.
- **Configuration Separation:** No user-specific configuration values should be hardcoded in the repository. All model names, API endpoints, and other user-specific settings must come from environment variables.
- **Uncommitted Reviews:** Use `--uncommitted` flag to review only files with uncommitted changes. This is useful for pre-commit reviews.
- **Context Command:** Use `council context <file_path>` to get review context (code, prompt, knowledge) for external agents to perform reviews without Council's LLM.
