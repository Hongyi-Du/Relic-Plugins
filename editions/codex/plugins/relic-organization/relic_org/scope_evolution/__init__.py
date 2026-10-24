"""Versioned SCOPE assets and pure contextual admission primitives."""

from .models import SCOPE_KEY
from .registry import PatchRegistry
from .resolver import Truth, evaluate, matches_scope, resolve, trusted_context

__all__ = ["SCOPE_KEY", "PatchRegistry", "Truth", "evaluate", "matches_scope", "resolve", "trusted_context"]
