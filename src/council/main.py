"""Main FastMCP server entry point for The Council."""

import asyncio
import os
import time
import uuid
from datetime import datetime

import logfire
from fastmcp import FastMCP
from pydantic import BaseModel, Field

from .agents import CouncilDeps, ReviewResult, get_councilor_agent
from .tools.context import get_packed_context, get_packed_diff
from .tools.metrics_collector import get_metrics_collector
from .tools.persistence import ReviewRecord, get_review_history
from .tools.scribe import fetch_and_summarize, validate_topic, validate_url

# Configuration with environment variable support
MAX_CONTENT_SIZE = int(os.getenv("MAX_CONTENT_SIZE", "10485760"))  # 10MB default
REQUEST_TIMEOUT = float(os.getenv("REQUEST_TIMEOUT", "600.0"))  # 10 minutes default
LOGFIRE_ENABLED = os.getenv("LOGFIRE_ENABLED", "false").lower() == "true"

# Initialize logfire with environment-based configuration
logfire.configure(send_to_logfire=LOGFIRE_ENABLED)

# Create FastMCP server
mcp = FastMCP("The Council")

__all__ = ["mcp", "review_code", "learn_rules", "ReviewCodeResponse", "LearnRulesResponse"]


# Structured output models for MCP tools (MCP 2025-06-18 specification)
class ReviewCodeResponse(BaseModel):
    """Structured response for code review tool."""

    success: bool = Field(description="Whether the review completed successfully")
    summary: str | None = Field(default=None, description="Overall summary of the code review")
    issues: list[dict] = Field(
        default_factory=list, description="List of issues found during review"
    )
    severity: str | None = Field(
        default=None,
        description="Overall severity assessment (low/medium/high/critical)",
    )
    code_fix: str | None = Field(default=None, description="Optional suggested code fix")
    cross_file_issues: list[dict] = Field(
        default_factory=list,
        description="List of issues that span multiple files",
    )
    dependency_analysis: dict | None = Field(
        default=None, description="Analysis of code dependencies"
    )
    error: str | None = Field(default=None, description="Error message if review failed")


class LearnRulesResponse(BaseModel):
    """Structured response for learn rules tool."""

    success: bool = Field(description="Whether the operation completed successfully")
    message: str | None = Field(default=None, description="Success message or error details")
    error: str | None = Field(default=None, description="Error message if operation failed")
    error_code: str | None = Field(
        default=None, description="Error code for programmatic error handling"
    )


@mcp.tool(
    name="review_code",
    description="Review code at the given file path. Extracts context using Repomix, then uses the Councilor agent to perform a comprehensive code review.",
    annotations={
        "title": "Review Code",
        "readOnlyHint": True,
        "destructiveHint": False,
    },
)
async def review_code(file_path: str, base_ref: str | None = None) -> ReviewCodeResponse:
    """
    Review code at the given file path.

    This tool extracts context using Repomix, then uses the Councilor agent
    to perform a comprehensive code review.

    Args:
        file_path: Path to the file or directory to review
        base_ref: Optional git reference for diff-based review (e.g., "HEAD", "main").
                  If provided, only changed code will be reviewed.

    Returns:
        Structured review results with issues, severity, and recommendations
    """
    # Input validation
    if not file_path or not file_path.strip():
        return ReviewCodeResponse(success=False, error="file_path cannot be empty")

    # Generate request ID for correlation
    request_id = str(uuid.uuid4())[:8]

    # Initialize metrics and persistence
    metrics_collector = get_metrics_collector()
    review_history = get_review_history()
    review_metrics = metrics_collector.start_review(request_id, file_path)

    try:
        logfire.info("Starting code review", file_path=file_path, request_id=request_id)

        # Get packed context using Repomix with timeout
        # Use diff-based extraction if base_ref is provided
        context_start = time.time()
        try:
            if base_ref:
                packed_xml = await asyncio.wait_for(
                    get_packed_diff(file_path, base_ref), timeout=REQUEST_TIMEOUT
                )
            else:
                packed_xml = await asyncio.wait_for(
                    get_packed_context(file_path), timeout=REQUEST_TIMEOUT
                )
            context_duration = time.time() - context_start
            metrics_collector.record_tool_execution("repomix", context_duration, success=True)
        except TimeoutError:
            context_duration = time.time() - context_start
            metrics_collector.record_tool_execution(
                "repomix", context_duration, success=False, error_type="TimeoutError"
            )
            error_msg = f"Timeout while processing file: {file_path}"
            logfire.error("Timeout during context packing", error=error_msg, request_id=request_id)
            metrics_collector.finish_review(request_id, success=False, error_type="TimeoutError")
            return ReviewCodeResponse(success=False, error=error_msg)

        # Size check for large content
        if len(packed_xml) > MAX_CONTENT_SIZE:
            error_msg = f"Content too large: {len(packed_xml)} bytes (max: {MAX_CONTENT_SIZE})"
            logfire.warning("Large content rejected", size=len(packed_xml), request_id=request_id)
            return ReviewCodeResponse(success=False, error=error_msg)

        # Create dependencies for the agent
        deps = CouncilDeps(file_path=file_path)

        # Get the councilor agent (lazy initialization)
        agent = get_councilor_agent()

        # Run the councilor agent with error handling and timeout
        try:
            result = await asyncio.wait_for(
                agent.run(
                    f"Please review the following code:\n\n{packed_xml}",
                    deps=deps,
                ),
                timeout=REQUEST_TIMEOUT,
            )
        except TimeoutError:
            error_msg = "Agent execution timed out"
            logfire.error("Agent execution timeout", error=error_msg, request_id=request_id)
            return ReviewCodeResponse(success=False, error=error_msg)
        except ValueError as e:
            # Handle specific validation errors
            error_msg = f"Agent validation failed: {str(e)}"
            logfire.error("Agent validation failed", error=error_msg, request_id=request_id)
            return ReviewCodeResponse(success=False, error=error_msg)
        except Exception as e:
            error_msg = f"Agent execution failed: {str(e)}"
            logfire.error(
                "Agent execution failed", error=error_msg, request_id=request_id, exc_info=True
            )
            return ReviewCodeResponse(success=False, error=error_msg)

        # Validate result structure
        if not hasattr(result, "output") or not isinstance(result.output, ReviewResult):
            error_msg = "Invalid agent response format"
            logfire.error("Invalid agent response", error=error_msg, request_id=request_id)
            return ReviewCodeResponse(success=False, error=error_msg)

        # Extract the structured result
        review_result: ReviewResult = result.output

        # Extract token usage if available
        token_usage: dict[str, int] = {}
        if hasattr(result, "usage") and result.usage:
            if hasattr(result.usage, "input_tokens"):
                token_usage["input_tokens"] = result.usage.input_tokens
            if hasattr(result.usage, "output_tokens"):
                token_usage["output_tokens"] = result.usage.output_tokens
            if hasattr(result.usage, "total_tokens"):
                token_usage["total_tokens"] = result.usage.total_tokens

        # Finish metrics collection
        metrics_collector.finish_review(
            request_id,
            success=True,
            issues_found=len(review_result.issues),
            severity=review_result.severity,
            context_size_bytes=len(packed_xml),
            token_usage=token_usage,
        )

        # Save review to history
        try:
            review_record = ReviewRecord(
                review_id=request_id,
                file_path=file_path,
                timestamp=datetime.now().isoformat(),
                duration_seconds=review_metrics.duration_seconds or 0.0,
                success=True,
                error_type=None,
                issues_found=len(review_result.issues),
                severity=review_result.severity,
                context_size_bytes=len(packed_xml),
                token_usage=token_usage,
                summary=review_result.summary,
                metadata={"base_ref": base_ref} if base_ref else None,
            )
            review_history.save_review(review_record)
        except Exception as e:
            # Don't fail the review if persistence fails
            logfire.warning("Failed to save review history", error=str(e))

        # Return structured response (MCP 2025-06-18 structured output)
        return ReviewCodeResponse(
            success=True,
            summary=review_result.summary,
            issues=[
                {
                    "description": issue.description,
                    "severity": issue.severity,
                    "category": issue.category,
                    "line_number": issue.line_number,
                    "code_snippet": issue.code_snippet,
                    "related_files": issue.related_files,
                    "suggested_priority": issue.suggested_priority,
                    "references": issue.references,
                    "auto_fixable": issue.auto_fixable,
                }
                for issue in review_result.issues
            ],
            severity=review_result.severity,
            code_fix=review_result.code_fix,
            cross_file_issues=[
                {
                    "description": issue.description,
                    "severity": issue.severity,
                    "files": issue.files,
                    "category": issue.category,
                }
                for issue in review_result.cross_file_issues
            ],
            dependency_analysis=(
                {
                    "external_dependencies": review_result.dependency_analysis.external_dependencies,
                    "internal_dependencies": review_result.dependency_analysis.internal_dependencies,
                    "circular_dependencies": review_result.dependency_analysis.circular_dependencies,
                    "unused_imports": review_result.dependency_analysis.unused_imports,
                }
                if review_result.dependency_analysis
                else None
            ),
        )

    except FileNotFoundError as e:
        error_msg = f"File not found: {str(e)}"
        logfire.error("Review failed", error=error_msg, request_id=request_id)
        metrics_collector.finish_review(request_id, success=False, error_type="FileNotFoundError")
        return ReviewCodeResponse(success=False, error=error_msg)
    except PermissionError as e:
        error_msg = f"Permission denied: {str(e)}"
        logfire.error("Review failed", error=error_msg, request_id=request_id)
        metrics_collector.finish_review(request_id, success=False, error_type="PermissionError")
        return ReviewCodeResponse(success=False, error=error_msg)
    except Exception as e:
        error_msg = f"Review failed: {str(e)}"
        error_type = type(e).__name__
        logfire.error("Review failed", error=error_msg, request_id=request_id, exc_info=True)
        metrics_collector.finish_review(request_id, success=False, error_type=error_type)
        return ReviewCodeResponse(success=False, error=error_msg)


@mcp.tool(
    name="learn_rules",
    description="Learn rules from a documentation URL and add to knowledge base. Fetches documentation using Jina Reader and saves it to the knowledge base, which will be automatically included in future reviews.",
    annotations={
        "title": "Learn Rules from Documentation",
        "readOnlyHint": False,
        "destructiveHint": False,
        "openWorldHint": True,
    },
)
async def learn_rules(url: str, topic: str) -> LearnRulesResponse:
    """
    Learn rules from a documentation URL and add to knowledge base.

    This tool fetches documentation using Jina Reader and saves it to the
    knowledge base, which will be automatically included in future reviews.

    Args:
        url: URL to fetch documentation from
        topic: Topic name for the knowledge file

    Returns:
        Structured response with success status and message
    """
    # Input validation
    if not url or not url.strip():
        return LearnRulesResponse(
            success=False, error="URL cannot be empty", error_code="EMPTY_URL"
        )

    # Enhanced topic validation using scribe.validate_topic
    try:
        validated_topic = validate_topic(topic)
        topic = validated_topic  # Use validated topic
    except ValueError as e:
        return LearnRulesResponse(success=False, error=str(e), error_code="INVALID_TOPIC")

    # Enhanced URL validation using scribe.validate_url
    try:
        validate_url(url)
    except ValueError as e:
        return LearnRulesResponse(
            success=False,
            error=str(e),
            error_code="INVALID_URL",
        )

    # Generate request ID for correlation
    request_id = str(uuid.uuid4())[:8]

    try:
        logfire.info("Learning rules", url=url, topic=topic, request_id=request_id)

        # Add timeout for the fetch operation
        try:
            result = await asyncio.wait_for(
                fetch_and_summarize(url, topic), timeout=REQUEST_TIMEOUT
            )
        except TimeoutError:
            error_msg = "Timeout while fetching documentation"
            logfire.error("Learn rules timeout", error=error_msg, request_id=request_id)
            return LearnRulesResponse(success=False, error=error_msg)

        logfire.info("Rules learned successfully", topic=topic, request_id=request_id)
        return LearnRulesResponse(success=True, message=result)

    except Exception as e:
        error_msg = f"Failed to learn rules: {str(e)}"
        logfire.error("Learn rules failed", error=error_msg, request_id=request_id, exc_info=True)
        return LearnRulesResponse(success=False, error=error_msg)


if __name__ == "__main__":
    # Run the MCP server
    mcp.run()
