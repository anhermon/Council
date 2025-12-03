"""Context extraction using Repomix.

This module provides a backward-compatible interface to the refactored
Repomix execution module. New code should import directly from repomix.py.
"""

from .repomix import get_packed_context, get_packed_diff

__all__ = ["get_packed_context", "get_packed_diff"]
