"""Domain layer: pure models and business concepts for cmux hierarchy.

No I/O, no frameworks. Senior DDD-lite for fidelity to cmux app.
"""
from .models import (
    CmuxTree, Window, Workspace, Pane, Surface, SurfaceType, SurfaceRef,
    ScreenSnapshot, SurfaceContext, SynthesisContext, PerSurfaceState, SynthesisResult,
    TreeUpdated, SurfaceScreenUpdated, SynthesisReady,
)
from .parser import parse_cmux_tree, parse_from_json_string

__all__ = [
    "CmuxTree", "Window", "Workspace", "Pane", "Surface", "SurfaceType", "SurfaceRef",
    "ScreenSnapshot", "SurfaceContext", "SynthesisContext", "PerSurfaceState", "SynthesisResult",
    "TreeUpdated", "SurfaceScreenUpdated", "SynthesisReady",
    "parse_cmux_tree", "parse_from_json_string",
]
