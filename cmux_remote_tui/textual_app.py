"""
cmux-remote-tui v0.2+ — State-of-the-art Textual TUI (senior architecture).

Follows the ARCHITECTURE.md:
- Clean hexagonal layers: domain models, application orchestrator, infrastructure adapters (SshCmuxClient, LLM providers), presentation (Textual).
- Rich domain model for full cmux hierarchy (windows > workspaces > panes > surfaces: terminals + browsers).
- Persistent fast transport via agent.
- LLM Synthesis layer as first-class "better than original" feature (supports local grok/claude/codex CLI + OpenRouter + any OpenAI-compatible).
- Reactive UI with live updates, hierarchical Tree, preview, LLM Conductor panel.
- Full parity with cmux capabilities + extras for multi-agent orchestration (e.g. LLM-synthesized focus lists across surfaces).

This makes the remote TUI superior for power users: global view + AI intelligence across machines, something local cmux GUI cannot provide when driving agents remotely.

Run: cmux-remote-tui (or python -m cmux_remote_tui.textual_app)
Configure LLM via env (as specified): CMUX_LLM_PROVIDER=local-claude|openrouter|openai-compatible etc.
"""

from __future__ import annotations

import asyncio
import os
from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Header, Footer, Tree, RichLog, Static, Input, Button
from textual.binding import Binding
from textual.reactive import reactive

from .domain.models import CmuxTree, SurfaceRef
from .domain.protocols import CmuxClient, LlmProvider
from .infrastructure.cmx_client import SshCmuxClient
from .infrastructure.llm_providers import make_llm_provider
from .application.orchestrator import CmuxOrchestrator
from .domain.parser import parse_cmux_tree


class CmuxRemoteApp(App):
    """Senior SOTA Textual implementation.

    - Uses Orchestrator for all logic (decoupled from UI).
    - Hierarchical Tree for full cmux structure.
    - Live preview (RichLog preserves ANSI from cmux read-screen).
    - LLM Conductor for synthesis (the key differentiator vs local cmux).
    - Actions for attach, focus, browser commands, etc.
    - Full keyboard + mouse via Textual.
    - Designed for user's workflow: Hermes + GSD + multi-agent remote over Tailscale.
    """

    CSS = """
    Screen { layout: horizontal; }
    #tree-pane { width: 40%; min-width: 30; border: solid $accent; }
    #preview-pane { width: 35%; border: solid $primary; }
    #llm-pane { width: 25%; min-width: 20; border: solid $secondary; background: $surface; }
    Tree { padding: 1; }
    RichLog { padding: 1; border: round $accent; }
    .surface-terminal { color: $text; }
    .surface-browser { color: $warning; }
    .active { text-style: bold; color: $success; }
    """

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("r", "refresh_tree", "Refresh"),
        Binding("a", "attach", "Attach"),
        Binding("f", "focus", "Focus"),
        Binding("?", "help", "Help"),
        Binding("ctrl+s", "synthesize", "LLM Synthesize"),
        Binding("b", "browser_open", "Browser Open (example)"),
    ]

    connected = reactive(False)
    current_surface: reactive[str | None] = reactive(None)

    def __init__(self, host: str | None = None):
        super().__init__()
        self.host = host or os.environ.get("CMUX_REMOTE_HOST") or "desk"
        self.client: CmuxClient = SshCmuxClient(self.host)
        self.llm: LlmProvider = make_llm_provider()  # env-driven: local-*/openrouter/openai-compatible
        self.orchestrator = CmuxOrchestrator(
            self.client,
            self.llm,
            on_tree_updated=self._on_tree_updated,
            on_screen_updated=self._on_screen_updated,
            on_synthesis_ready=self._on_synthesis_ready,
        )

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Horizontal():
            yield Tree("cmux @ " + self.host, id="tree-pane")
            with Vertical(id="preview-pane"):
                yield Static("Live Preview (ANSI preserved)", id="preview-title")
                yield RichLog(id="preview-log", wrap=True, highlight=True)
            with Vertical(id="llm-pane"):
                yield Static("LLM Conductor / Synthesis (better than local cmux)", id="llm-title")
                yield RichLog(id="llm-log", wrap=True)
                yield Input(placeholder="Ask LLM about surfaces (e.g. 'summarize active agents')", id="llm-input")
                yield Button("Synthesize", id="btn-synth")
                yield Button("Browser Demo", id="btn-browser")
        yield Footer()

    def on_mount(self) -> None:
        self.title = "cmux-remote-tui v0.2 (SOTA Architecture)"
        self.sub_title = "Hexagonal + Domain Models + LLM Intelligence | Better than local cmux for remote multi-agent work"
        self.query_one("#tree-pane", Tree).focus()
        self.orchestrator.start()
        self.run_worker(self._refresh_loop, exclusive=True)

    async def _refresh_loop(self) -> None:
        while True:
            self.orchestrator.refresh_tree()
            await asyncio.sleep(2.5)
            if self.current_surface:
                snap = self.orchestrator.get_screen(SurfaceRef(self.current_surface), lines=80)
                if snap:
                    self._update_preview(self.current_surface, snap)

    def _on_tree_updated(self, event: "TreeUpdated") -> None:
        tree = self.query_one("#tree-pane", Tree)
        tree.clear()
        tree.root.label = f"cmux @ {self.host} ({len(event.tree.all_surfaces())} surfaces)"

        # Full hierarchical view matching cmux structure (state of the art fidelity)
        for win in event.tree.windows:
            win_node = tree.root.add(f"Window {win.ref}", expand=True)
            for ws in win.workspaces:
                ws_node = win_node.add(f"WS: {ws.title or ws.ref} {'📌' if ws.pinned else ''}", expand=True)
                for p in ws.panes:
                    p_node = ws_node.add(f"Pane {p.ref}", expand=True)
                    for s in p.surfaces:
                        icon = "🖥️" if s.is_terminal else "🌐"
                        label = f"{icon} {s.title} [{s.ref}]"
                        node = p_node.add_leaf(label, data=str(s.ref))
                        if s.active:
                            node.expand()

        self.query_one("#llm-log", RichLog).write(f"[dim]Full cmux hierarchy refreshed[/]")

    def _on_screen_updated(self, event: "SurfaceScreenUpdated") -> None:
        self._update_preview(str(event.ref), event.snapshot.content)

    def _on_synthesis_ready(self, event: "SynthesisReady") -> None:
        log = self.query_one("#llm-log", RichLog)
        log.write(f"[bold green]=== LLM Synthesis ({self.llm.provider_name}/{self.llm.model}) ===[/]")
        log.write(event.result.raw_text)
        # Smart feature: one-click send summary as instruction (example)
        if event.result.global_focus_list:
            log.write("[dim]Tip: Use LLM output to drive actions on specific surfaces[/]")

    def _update_preview(self, ref: str, content: str):
        log = self.query_one("#preview-log", RichLog)
        log.clear()
        # RichLog preserves ANSI from cmux read-screen (live preview)
        log.write(content[:4000] if content else "(no data)")

    def on_tree_node_selected(self, event: Tree.NodeSelected) -> None:
        if event.node and event.node.data:
            self.current_surface = str(event.node.data)
            snap = self.orchestrator.get_screen(SurfaceRef(self.current_surface), lines=80)
            if snap:
                self._update_preview(self.current_surface, snap)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-synth" and self.current_surface:
            self.orchestrator.synthesize([SurfaceRef(self.current_surface)])
        elif event.button.id == "btn-browser" and self.current_surface:
            # Browser parity example (maps cmux browser verbs)
            self.orchestrator.execute(["browser", "open", "https://example.com"])  # via generic
            self.query_one("#llm-log", RichLog).write("[cyan]Browser open demo (full verbs in Wave 2)[/]")

    def action_attach(self) -> None:
        if self.current_surface:
            self.orchestrator.attach(SurfaceRef(self.current_surface))
            self.query_one("#llm-log", RichLog).write(f"[cyan]ATTACH {self.current_surface} — keys stream live (Ctrl-] to detach in full impl)[/]")

    def action_synthesize(self) -> None:
        if self.current_surface:
            self.orchestrator.synthesize([SurfaceRef(self.current_surface)])

    def action_refresh_tree(self) -> None:
        self.orchestrator.refresh_tree()

    def action_browser_open(self) -> None:
        if self.current_surface:
            # Example of exposing browser commands (full parity)
            self.orchestrator.execute(["browser", "open", "https://news.ycombinator.com"])
            self.query_one("#llm-log", RichLog).write("[cyan]Browser open triggered (see cmux skill for full verbs)[/]")


def run_app():
    """Entry point for SOTA Textual TUI."""
    import os
    import sys
    host = None
    # Support --host/-H from CLI (launcher usually sets via env + hard default macmini-ts)
    argv = sys.argv[1:]
    i = 0
    while i < len(argv):
        if argv[i] in ("--host", "-H") and i + 1 < len(argv):
            host = argv[i + 1]
            break
        i += 1
    if not host:
        host = os.environ.get("CMUX_REMOTE_HOST") or os.environ.get("CMUX_MINI_HOST")
    if not host:
        host = "macmini-ts"  # hard default to match the "latwy skrypt"
    app = CmuxRemoteApp(host=host)
    app.run()


if __name__ == "__main__":
    run_app()
