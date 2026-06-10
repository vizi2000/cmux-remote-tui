"""Application layer: CmuxOrchestrator coordinates the system.

Senior design: owns live state, handles use cases like attach, synthesize.
Decouples UI from domain/infra.
"""

from __future__ import annotations
from typing import Optional, List, Callable
import time

from ..domain.models import (
    CmuxTree, SurfaceRef, SynthesisContext, SynthesisResult,
    TreeUpdated, SurfaceScreenUpdated, SynthesisReady, SurfaceContext,
)
from ..domain.protocols import CmuxClient, LlmProvider


class CmuxOrchestrator:
    """Main application service for cmux remote control.

    - Maintains current CmuxTree state.
    - Coordinates background refreshes via client.
    - Triggers LLM synthesis.
    - Emits events for UI (or direct callbacks for simplicity in v0.2).
    """

    def __init__(
        self,
        client: CmuxClient,
        llm: LlmProvider,
        on_tree_updated: Optional[Callable[[TreeUpdated], None]] = None,
        on_screen_updated: Optional[Callable[[SurfaceScreenUpdated], None]] = None,
        on_synthesis_ready: Optional[Callable[[SynthesisReady], None]] = None,
    ):
        self._client = client
        self._llm = llm
        self._tree: Optional[CmuxTree] = None
        self._on_tree_updated = on_tree_updated
        self._on_screen_updated = on_screen_updated
        self._on_synthesis_ready = on_synthesis_ready
        self._last_synthesis: Optional[SynthesisResult] = None

    @property
    def tree(self) -> Optional[CmuxTree]:
        return self._tree

    @property
    def connected(self) -> bool:
        return self._client.connected

    def start(self) -> bool:
        ok = self._client.start()
        if ok:
            self._refresh_tree()
        return ok

    def stop(self) -> None:
        self._client.stop()

    def refresh_tree(self) -> None:
        self._refresh_tree()

    def _refresh_tree(self) -> None:
        raw_tree = self._client.get_full_tree()  # uses the enhanced client
        self._tree = self._parse_tree(raw_tree) if raw_tree else None
        if self._tree and self._on_tree_updated:
            self._on_tree_updated(TreeUpdated(self._tree))

    def _parse_tree(self, raw: dict) -> CmuxTree:
        # Use the parser; in real would be injected or from domain
        from ..domain.parser import parse_cmux_tree
        # Note: if raw has 'full_tree' use it, else raw
        tree_json = raw.get("full_tree", raw)
        return parse_cmux_tree(tree_json)

    def get_screen(self, ref: SurfaceRef, lines: int = 120, scrollback: bool = False) -> Optional[str]:
        snap = self._client.read_screen(ref, lines, scrollback)
        return snap.content if snap else None

    def attach(self, ref: SurfaceRef) -> None:
        # For attach, the UI will handle the interactive loop using send_keys + read
        # Here we can prime the preview
        snap = self._client.read_screen(ref, lines=200)
        if snap and self._on_screen_updated:
            self._on_screen_updated(SurfaceScreenUpdated(ref, snap))

    def send_to_surface(self, ref: SurfaceRef, text: str) -> None:
        # Simple send; for interactive attach, UI batches
        self._client.send_keys(ref, [("text", text), ("key", "enter")])
        # Refresh preview after
        snap = self._client.read_screen(ref, lines=100)
        if snap and self._on_screen_updated:
            self._on_screen_updated(SurfaceScreenUpdated(ref, snap))

    def synthesize(self, refs: List[SurfaceRef], context_notes: str = "") -> Optional[SynthesisResult]:
        """Core 'better than original' feature.

        Reads multiple surfaces, builds context, calls LLM, returns structured result.
        """
        contexts: List[SurfaceContext] = []
        for ref in refs:
            snap = self._client.read_screen(ref, lines=150)
            if not snap:
                continue
            surface = self._tree.find_surface(ref) if self._tree else None
            if not surface:
                # fallback minimal surface
                from ..domain.models import Surface, SurfaceType, SurfaceRef
                surface = Surface(ref=ref, title=str(ref), type=SurfaceType.TERMINAL)
            ctx = SurfaceContext(surface=surface, snapshot=snap)
            contexts.append(ctx)

        if not contexts:
            return None

        synth_context = SynthesisContext(surfaces=contexts, global_notes=context_notes)
        # Build prompt inside or delegate to service; here simple for v0.2
        prompt = self._build_synthesis_prompt(synth_context)
        result = self._llm.synthesize(prompt, synth_context)

        self._last_synthesis = result
        if self._on_synthesis_ready:
            self._on_synthesis_ready(SynthesisReady(result))
        return result

    def _build_synthesis_prompt(self, ctx: SynthesisContext) -> str:
        parts = ["You are an expert multi-agent coding orchestrator for cmux (advanced terminal for AI agents like Claude, Hermes, etc.).\n"]
        parts.append("Analyze these live screens from remote surfaces. For each provide:\n")
        parts.append("- ref, agent_type (guess from content/title), current_task, state (working/stuck/waiting/done/error), last_output_summary (1 sentence), priority 1-5\n\n")
        for sc in ctx.surfaces:
            parts.append(f"[{sc.surface.ref}] title={sc.surface.title} type={sc.surface.type} tty={sc.surface.tty or ''}\n")
            parts.append("---SCREEN---\n")
            parts.append(sc.snapshot.content[:1200] + "\n")
            parts.append("---END---\n\n")
        if ctx.global_notes:
            parts.append(f"Additional context: {ctx.global_notes}\n")
        parts.append("Output a clean **Prioritized Focus List** (3-5 items max) with concrete actions like 'attach to ref X and run tests'.\n")
        parts.append("Be concise, actionable. Use exact refs.")
        return "".join(parts)
