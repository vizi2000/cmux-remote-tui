"""Domain models for cmux structure.

Senior design: immutable dataclasses, rich types matching cmux's real model
(windows > workspaces > panes > surfaces: terminals + browsers).
This enables faithful mirroring + LLM synthesis on top.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Literal, Optional, Union, List, Dict, Any
from enum import Enum

class SurfaceType(str, Enum):
    TERMINAL = "terminal"
    BROWSER = "browser"

@dataclass(frozen=True)
class SurfaceRef:
    """Unique reference to a surface (e.g. 'surface:42')."""
    value: str

    def __str__(self) -> str:
        return self.value

@dataclass(frozen=True)
class ScreenSnapshot:
    """Snapshot of a surface's screen content."""
    ref: SurfaceRef
    content: str
    lines: int
    scrollback: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)

@dataclass(frozen=True)
class Surface:
    """Base for a cmux surface (leaf in the hierarchy)."""
    ref: SurfaceRef
    title: str
    type: SurfaceType
    tty: Optional[str] = None
    url: Optional[str] = None  # for browsers
    selected: bool = False
    active: bool = False

    @property
    def is_browser(self) -> bool:
        return self.type == SurfaceType.BROWSER

    @property
    def is_terminal(self) -> bool:
        return self.type == SurfaceType.TERMINAL

@dataclass(frozen=True)
class Pane:
    """A pane containing one or more surfaces."""
    ref: str
    surfaces: List[Surface] = field(default_factory=list)

@dataclass(frozen=True)
class Workspace:
    """A workspace (tab-like) containing panes."""
    ref: str
    title: str
    pinned: bool = False
    active: bool = False
    selected: bool = False
    panes: List[Pane] = field(default_factory=list)

@dataclass(frozen=True)
class Window:
    """A top-level window containing workspaces."""
    ref: str
    workspaces: List[Workspace] = field(default_factory=list)

@dataclass(frozen=True)
class CmuxTree:
    """Full hierarchical model of a cmux instance."""
    windows: List[Window] = field(default_factory=list)
    active_surface: Optional[SurfaceRef] = None

    def all_surfaces(self) -> List[Surface]:
        """Flatten for convenience (e.g. for LLM synthesis)."""
        surfaces: List[Surface] = []
        for w in self.windows:
            for ws in w.workspaces:
                for p in ws.panes:
                    surfaces.extend(p.surfaces)
        return surfaces

    def find_surface(self, ref: SurfaceRef) -> Optional[Surface]:
        for s in self.all_surfaces():
            if s.ref == ref:
                return s
        return None

# Events for reactive updates (domain events)
@dataclass(frozen=True)
class TreeUpdated:
    tree: CmuxTree

@dataclass(frozen=True)
class SurfaceScreenUpdated:
    ref: SurfaceRef
    snapshot: ScreenSnapshot

@dataclass(frozen=True)
class SynthesisReady:
    result: "SynthesisResult"  # forward ref, defined in application

# Value objects for LLM context
@dataclass(frozen=True)
class SurfaceContext:
    surface: Surface
    snapshot: ScreenSnapshot
    inferred_agent: Optional[str] = None  # e.g. "claude-code", "hermes"

@dataclass(frozen=True)
class SynthesisContext:
    surfaces: List[SurfaceContext]
    global_notes: str = ""  # e.g. from Hermes memory or user GSD context

@dataclass(frozen=True)
class PerSurfaceState:
    ref: SurfaceRef
    agent_type: str
    current_task: str
    state: Literal["working", "stuck", "waiting_input", "done", "error"]
    last_output_summary: str
    priority: int  # 1-5

@dataclass(frozen=True)
class SynthesisResult:
    per_surface: List[PerSurfaceState]
    global_focus_list: List[str]  # prioritized actions
    raw_text: str  # full LLM output for transparency
    timestamp: float
