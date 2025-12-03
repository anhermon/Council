# Project Tasks & Improvement Plan

Generated from self-review on 2025-12-04.

## 🚨 Critical Priority (Fix Immediately)

- [ ] **Fix Infinite Loop in `path_utils.py`**
    - **Issue:** The recursive search in `resolve_file_path` breaks the inner loop (glob match) but not the outer loop (`range(MAX_SEARCH_DEPTH)`), causing unnecessary iterations or potential hangs.
    - **Action:** Refactor the loop logic to exit immediately upon finding a valid match.

- [ ] **Fix Subprocess Resource Leaks**
    - **Issue:** `static_analysis.py` and `testing.py` do not explicitly kill processes on `TimeoutError`, leading to potential zombie processes.
    - **Action:** Create a shared `run_command_safely` utility (e.g., in `src/council/tools/utils.py`) that handles timeouts and ensures process termination (`proc.kill()`) in a `finally` block.

## 🟠 High Priority (Reliability & Correctness)

- [ ] **Refactor Broad Exception Handling**
    - **Issue:** Tools like `testing.py` and `context.py` often catch generic `Exception` and return fallback values or log generic errors, masking root causes (like permission denied vs missing file).
    - **Action:** Catch specific exceptions (`OSError`, `ValueError`, `TimeoutError`, `subprocess.CalledProcessError`) and propagate or handle them distinctly.

- [ ] **Input Validation in `static_analysis.py`**
    - **Issue:** `run_static_analysis` does not validate if `file_path` is empty or None. The `base_path` argument is documented but unused.
    - **Action:** Add input validation assertions and remove or implement `base_path`.

- [ ] **Centralize Configuration**
    - **Issue:** `main.py` parses environment variables (e.g., `MAX_CONTENT_SIZE`) inline, duplicating logic found elsewhere or creating inconsistencies. Tool files also contain hardcoded limits.
    - **Action:** Move all configuration logic to `src/council/config.py` and update `main.py` and tools to import from there.

## 🟡 Medium Priority (Maintainability & Ops)

- [ ] **Setup CI/CD Pipeline**
    - **Issue:** No automated testing or linting exists (missing `.github/workflows`).
    - **Action:** Create a GitHub Action workflow to run `uv run pytest` and `uv run ruff check` on push/PR.

- [ ] **Refactor `path_utils.py` Complexity**
    - **Issue:** `resolve_file_path` has high cyclomatic complexity (31), making it hard to test and maintain.
    - **Action:** Extract logic into helper functions like `_try_resolve_relative`, `_search_project_recursive`, etc.

- [ ] **Improve Template Robustness (`system_prompt.j2`)**
    - **Issue:** The Jinja2 template lacks type checks for inputs and has potentially confusing XML encoding examples.
    - **Action:** Add `is mapping` checks and clarify XML documentation.

- [ ] **Graceful Server Shutdown**
    - **Issue:** `main.py` lacks explicit signal handling for graceful shutdown, risking temporary file leftovers.
    - **Action:** Implement signal handlers or context managers to ensure `tempfile` cleanups happen on exit.

## 🟢 Low Priority (Polish)

- [ ] **Documentation Updates**
    - **Issue:** `src/council/agents/__init__.py` lacks descriptive docstrings. `testing.py` misses timeout documentation.
    - **Action:** Add comprehensive docstrings.

- [ ] **Expand Test Coverage**
    - **Issue:** Critical paths in `path_utils.py` and `static_analysis.py` are untested.
    - **Action:** Create `tests/test_tools_path_utils.py` and `tests/test_tools_static_analysis.py`.

- [ ] **Pre-commit Hooks**
    - **Issue:** No pre-commit configuration to catch issues locally before push.
    - **Action:** Add `.pre-commit-config.yaml` for `ruff` and `mypy`.

## 🚀 Structural Improvements

- [ ] **Unified Subprocess Utility**: Abstract the repeated `asyncio.create_subprocess_exec` patterns found in `context.py`, `git_tools.py`, `static_analysis.py`, and `testing.py` into a single robust utility to enforce timeout/cleanup policies globally.
