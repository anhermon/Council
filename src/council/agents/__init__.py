"""Agents for The Council.

This module provides the core agent implementations for code review and analysis.
The main agent is the Councilor, which performs comprehensive code reviews using
AI models and various analysis tools.

Exports:
    ReviewResult: Result type for code review operations
    CouncilDeps: Dependencies container for the Councilor agent
    get_councilor_agent: Factory function to create a configured Councilor agent
"""

from .councilor import CouncilDeps, ReviewResult, get_councilor_agent

__all__ = ["ReviewResult", "CouncilDeps", "get_councilor_agent"]
