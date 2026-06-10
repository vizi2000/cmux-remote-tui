"""Infrastructure adapter for CmuxClient port.

Wraps the existing persistent SSH Agent to implement the domain protocol.
Keeps the zero-dep remote agent philosophy.
"""

from __future__ import annotations
from typing import List, Any

from ..domain.protocols import CmuxClient
from ..domain.models import CmuxTree, SurfaceRef, ScreenSnapshot, parse_cmux_tree
from ..client import Agent as SshAgent  # the existing transport


class SshCmuxClient(CmuxClient):
    """Adapter: SSH + JSON to remote agent.py implementing CmuxClient."""

    def __init__(self, host: str, agent_path: str | None = None):
        self._agent = SshAgent(host)
        if agent_path:
            # allow override, but Agent hardcodes in env for now; in real we'd pass via env
            pass

    def start(self) -> bool:
        return self._agent.start()

    def stop(self) -> None:
        self._agent.stop()

    @property
    def connected(self) -> bool:
        return self._agent.connected

    @property
    def last_err(self) -> str:
        return self._agent.last_err

    def get_tree(self) -> CmuxTree:
        data = self._agent.call("tree") or {}
        full = data.get("full_tree") or {}
        return parse_cmux_tree(full) if full else CmuxTree()

    def read_screen(self, ref: SurfaceRef, lines: int = 200, scrollback: bool = False) -> ScreenSnapshot:
        data = self._agent.call("read", {"ref": str(ref), "lines": lines, "sb": scrollback})
        content = data if isinstance(data, str) else str(data or "")
        return ScreenSnapshot(ref=ref, content=content, lines=lines, scrollback=scrollback)

    def send_keys(self, ref: SurfaceRef, events: List[Any]) -> ScreenSnapshot:
        data = self._agent.call("keys", {"ref": str(ref), "events": events, "lines": 200})
        content = data if isinstance(data, str) else str(data or "")
        return ScreenSnapshot(ref=ref, content=content, lines=200)

    def execute(self, argv: List[str]) -> dict:
        return self._agent.cmux(argv) or {"rc": 1, "err": "no conn"}

    def read_many(self, refs: List[SurfaceRef], lines: int = 200) -> dict[SurfaceRef, ScreenSnapshot]:
        refs_str = [str(r) for r in refs]
        blocks = self._agent.call("read_many", {"refs": refs_str, "lines": lines}) or {}
        result = {}
        for r, content in blocks.items():
            result[SurfaceRef(r)] = ScreenSnapshot(
                ref=SurfaceRef(r), content=content if isinstance(content, str) else str(content), lines=lines
            )
        return result
