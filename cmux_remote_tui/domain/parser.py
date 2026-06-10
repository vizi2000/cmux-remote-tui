"""Parser to convert raw cmux tree JSON into our rich domain CmuxTree.

This ensures 1:1 fidelity to cmux's internal model (from `cmux tree --json`).
"""

from __future__ import annotations
import json
from typing import Any, Dict, List

from .models import (
    CmuxTree, Window, Workspace, Pane, Surface, SurfaceType, SurfaceRef
)


def parse_cmux_tree(raw: Dict[str, Any]) -> CmuxTree:
    """Parse the full hierarchical JSON from cmux into domain model."""
    windows: List[Window] = []
    for w in raw.get("windows", []):
        workspaces: List[Workspace] = []
        for ws in w.get("workspaces", []):
            panes: List[Pane] = []
            for p in ws.get("panes", []):
                surfaces: List[Surface] = []
                for s in p.get("surfaces", []):
                    surf_type = SurfaceType(s.get("type", "terminal"))
                    surfaces.append(Surface(
                        ref=SurfaceRef(s.get("ref", "")),
                        title=s.get("title", ""),
                        type=surf_type,
                        tty=s.get("tty"),
                        url=s.get("url"),
                        selected=s.get("selected", False),
                        active=s.get("active", False),
                    ))
                panes.append(Pane(ref=p.get("ref", ""), surfaces=surfaces))
            workspaces.append(Workspace(
                ref=ws.get("ref", ""),
                title=ws.get("title", ""),
                pinned=ws.get("pinned", False),
                active=ws.get("active", False),
                selected=ws.get("selected", False),
                panes=panes,
            ))
        windows.append(Window(ref=w.get("ref", ""), workspaces=workspaces))

    active = None
    if raw.get("active"):
        active = SurfaceRef(raw["active"])

    return CmuxTree(windows=windows, active_surface=active)


def parse_from_json_string(raw_json: str) -> CmuxTree:
    return parse_cmux_tree(json.loads(raw_json))
