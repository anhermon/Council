"""Context builder for review context command."""

from ...agents import CouncilDeps
from ...agents.councilor import detect_language, get_relevant_knowledge
from ...config import get_settings
from ...tools.repomix import extract_code_from_xml

settings = get_settings()


async def build_review_context(
    packed_xml: str,
    deps: CouncilDeps,
) -> dict[str, str | dict]:
    """
    Build review context for external agents.

    Args:
        packed_xml: Packed XML context from Repomix
        deps: Council dependencies

    Returns:
        Dictionary containing extracted_code, system_prompt, knowledge_base, file_path, language, and review_checklist
    """
    # Extract code from XML
    extracted_code = extract_code_from_xml(packed_xml)

    # Load relevant knowledge
    knowledge_base, loaded_filenames = await get_relevant_knowledge([deps.file_path])

    # Detect language
    language = detect_language(deps.file_path)

    # Build system prompt using template logic
    system_prompt = await _build_system_prompt(deps, knowledge_base, language, loaded_filenames)

    # Create review checklist/prompt
    review_checklist = _create_review_checklist(language, deps.review_phases)

    return {
        "extracted_code": extracted_code,
        "system_prompt": system_prompt,
        "knowledge_base": knowledge_base,
        "file_path": deps.file_path,
        "language": language,
        "metadata": {
            "extra_instructions": deps.extra_instructions,
            "review_phases": deps.review_phases,
            "loaded_knowledge_files": list(loaded_filenames),
        },
        "review_checklist": review_checklist,
    }


async def _build_system_prompt(
    deps: CouncilDeps,
    domain_rules: str,
    language: str,
    _loaded_filenames: set[str],  # Unused but kept for API consistency
) -> str:
    """Build system prompt using template logic."""
    from ...agents.councilor import _get_jinja_env, _validate_extra_instructions

    knowledge_dir = settings.knowledge_dir

    # Load and render the Jinja2 template
    jinja_env = _get_jinja_env()
    template = jinja_env.get_template("system_prompt.j2")

    # Validate extra instructions
    validated_extra_instructions = _validate_extra_instructions(deps.extra_instructions)

    # Check for language-specific files
    language_specific_files: list[str] = []
    if language != "unknown" and knowledge_dir.exists():
        language_patterns = [
            f"{language}_best_practices.md",
            f"{language}_patterns.md",
            f"{language}_guidelines.md",
            f"{language}_standards.md",
            f"{language}_rules.md",
        ]

        for pattern in language_patterns:
            lang_file = knowledge_dir / pattern
            if lang_file.exists():
                language_specific_files.append(pattern)

    # Add phase-specific instructions if phases are specified
    phase_instructions = ""
    if deps.review_phases:
        phase_instructions = f"\n\nREVIEW PHASES: Focus on {', '.join(deps.review_phases)}. "

        if "security" in deps.review_phases:
            phase_instructions += (
                "Prioritize security vulnerabilities and security best practices. "
            )

        if "performance" in deps.review_phases:
            phase_instructions += (
                "Focus on performance bottlenecks, optimization opportunities, and efficiency. "
            )

        if "maintainability" in deps.review_phases:
            phase_instructions += (
                "Emphasize code maintainability, readability, and long-term sustainability. "
            )

        if "best_practices" in deps.review_phases:
            phase_instructions += "Apply general best practices and coding standards. "

    prompt = template.render(
        domain_rules=domain_rules,
        extra_instructions=validated_extra_instructions,
        language=language,
        language_specific_files=language_specific_files,
    )

    return prompt + phase_instructions


def _create_review_checklist(language: str, review_phases: list[str] | None) -> str:
    """
    Create a review checklist/prompt for external agents.

    Args:
        language: Detected programming language
        review_phases: Optional list of review phases

    Returns:
        Review checklist as a string
    """
    checklist = """# Code Review Checklist

You are performing a comprehensive code review. Follow this checklist to ensure a thorough review.

## Review Process

1. **Read and Understand**: Carefully read through all the provided code
2. **Analyze**: Check for issues across all categories below
3. **Document**: Report all findings with accurate line numbers and code snippets
4. **Prioritize**: Focus on higher severity issues first, but report all legitimate issues

## What to Check

### Security
- [ ] SQL injection vulnerabilities
- [ ] XSS (Cross-Site Scripting) vulnerabilities
- [ ] Authentication and authorization issues
- [ ] Sensitive data exposure
- [ ] Insecure random number generation
- [ ] Hardcoded secrets or credentials
- [ ] Insecure deserialization
- [ ] Missing input validation
- [ ] Path traversal vulnerabilities
- [ ] CSRF protection

### Performance
- [ ] N+1 query problems
- [ ] Inefficient algorithms or data structures
- [ ] Memory leaks or excessive memory usage
- [ ] Unnecessary database queries
- [ ] Missing indexes
- [ ] Inefficient loops or iterations
- [ ] Blocking operations in async code
- [ ] Large file operations without streaming

### Code Quality & Maintainability
- [ ] Code duplication (DRY violations)
- [ ] Complex functions (high cyclomatic complexity)
- [ ] Poor naming conventions
- [ ] Missing or inadequate error handling
- [ ] Inconsistent code style
- [ ] Magic numbers without constants
- [ ] Long parameter lists
- [ ] God objects or classes with too many responsibilities

### Best Practices
- [ ] Proper use of design patterns
- [ ] SOLID principles adherence
- [ ] Proper separation of concerns
- [ ] Appropriate use of abstractions
- [ ] Testability concerns
- [ ] Documentation quality
- [ ] Logging and monitoring

### Bugs & Edge Cases
- [ ] Null pointer exceptions
- [ ] Off-by-one errors
- [ ] Race conditions
- [ ] Unhandled edge cases
- [ ] Incorrect logic
- [ ] Type mismatches
- [ ] Boundary condition errors

## Expected Output Format

You must return a structured review result with the following format:

```json
{
  "summary": "Overall summary of the code review (2-3 sentences)",
  "issues": [
    {
      "description": "Clear description of the issue",
      "severity": "low|medium|high|critical",
      "category": "security|performance|maintainability|bug|style|documentation",
      "line_number": 42,
      "code_snippet": "exact code showing the issue",
      "related_files": ["file1.py", "file2.py"],
      "suggested_priority": 8,
      "references": ["CVE-2023-1234", "https://example.com/docs"],
      "auto_fixable": false
    }
  ],
  "severity": "low|medium|high|critical",
  "code_fix": "Optional suggested code fix",
  "cross_file_issues": [
    {
      "description": "Issue spanning multiple files",
      "severity": "medium",
      "files": ["file1.py", "file2.py"],
      "category": "maintainability"
    }
  ],
  "dependency_analysis": {
    "external_dependencies": ["package1", "package2"],
    "internal_dependencies": ["module1", "module2"],
    "circular_dependencies": [["file1.py", "file2.py"]],
    "unused_imports": ["unused_module"]
  }
}
```

## Severity Guidelines

- **critical**: Security vulnerabilities, data loss risks, system crashes
- **high**: Serious bugs, significant performance issues, major security concerns
- **medium**: Code quality issues, moderate bugs, maintainability concerns
- **low**: Style issues, minor improvements, documentation gaps

## Important Notes

- **VERIFY BEFORE REPORTING**: Only report issues that actually exist in the code
- **Be Accurate**: Line numbers and code snippets must be exact
- **Be Comprehensive**: Aim to find all significant issues in a single review
- **Be Specific**: Provide clear, actionable feedback
- **Prioritize**: Focus on higher severity issues but don't skip lower severity ones
"""

    if language != "unknown":
        checklist += "\n## Language-Specific Guidelines\n\n"
        checklist += f"You are reviewing **{language}** code. Apply {language}-specific best practices and conventions.\n"

    if review_phases:
        checklist += "\n## Review Focus\n\n"
        checklist += f"Focus on these phases: {', '.join(review_phases)}\n"

    return checklist
