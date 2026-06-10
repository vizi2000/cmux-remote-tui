"""
cmux-remote-tui v0.2+ — State-of-the-art Textual TUI.

Replaces the old curses tui.py with Textual for:
- Modern, beautiful, reactive UI (CSS-like styling, themes)
- Mouse + excellent keyboard support
- Proper hierarchical tree (windows > workspaces > panes > surfaces)
- Live updates, split panes, modals, command palette
- Easy to add LLM Synthesis panel, browser controls, etc.

Keeps the same fast Agent (persistent SSH + zero-dep remote agent).

Run with: cmux-remote-tui  (or python -m cmux_remote_tui.textual_app)
"""

from __future__ import annotations

import asyncio
import os
from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Header, Footer, Tree, RichLog, Static, Input
from textual.binding import Binding
from textual.reactive import reactive

from .client import Agent  # reuse the existing fast client/agent
from .llm import get_llm  # new flexible LLM support (local grok/claude/codex cli + openrouter + any openai-compatible)


class CmuxRemoteApp(App):
    """Main Textual app for cmux remote control.

    Design goals for SOTA UX:
    - Hierarchical Tree on left (full cmux structure)
    - Live preview (RichLog or custom with ANSI) in center
    - LLM Synthesis / Conductor panel on right (the killer feature)
    - Bottom command bar / status
    - Full keyboard + mouse
    - Reactive updates from background worker (like old Worker thread)
    """

    CSS = """
    Screen {
        layout: horizontal;
    }

    #tree-pane {
        width: 40%;
        min-width: 30;
        border: solid $accent;
    }

    #preview-pane {
        width: 35%;
        border: solid $primary;
    }

    #llm-pane {
        width: 25%;
        min-width: 20;
        border: solid $secondary;
        background: $surface;
    }

    Tree {
        padding: 1;
    }

    RichLog {
        padding: 1;
        border: round $accent;
    }

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
    ]

    # Reactive state (Textual magic – auto refreshes UI)
    connected = reactive(False)
    current_surface: reactive[str | None] = reactive(None)

    def __init__(self, host: str | None = None):
        super().__init__()
        self.host = host or os.environ.get("CMUX_REMOTE_HOST") or "desk"
        self.agent = Agent(self.host)  # reuse existing fast persistent client
        self.tree_data: list[dict] = []
        # LLM provider configurable via env (as requested: local grok/claude/codex cli + openrouter + openai-compatible)
        # Examples:
        #   export CMUX_LLM_PROVIDER=local-claude
        #   export CMUX_LLM_MODEL=claude-3-5-sonnet-20241022
        #   export CMUX_LLM_PROVIDER=openrouter
        #   export OPENROUTER_API_KEY=sk-...
        #   export CMUX_LLM_MODEL=anthropic/claude-3.5-sonnet
        #   export CMUX_LLM_PROVIDER=openai-compatible
        #   export OPENAI_BASE_URL=https://llm.borg.tools/v1
        #   export OPENAI_API_KEY=...
        self.llm = get_llm()  # auto from env or defaults to openai-compatible

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Horizontal():
            yield Tree("cmux @ " + self.host, id="tree-pane")
            with Vertical(id="preview-pane"):
                yield Static("Live Preview", id="preview-title")
                yield RichLog(id="preview-log", wrap=True, highlight=True)
            with Vertical(id="llm-pane"):
                yield Static("LLM Conductor / Synthesis", id="llm-title")
                yield RichLog(id="llm-log", wrap=True)
                yield Input(placeholder="Ask about surfaces... (e.g. 'what needs attention?')", id="llm-input")
        yield Footer()

    def on_mount(self) -> None:
        self.title = "cmux-remote-tui v0.2 (Textual)"
        self.sub_title = "State-of-the-art remote control + LLM intelligence"
        self.query_one("#tree-pane", Tree).focus()
        # Start background connection + tree refresh (like old Worker)
        self.run_worker(self._connect_and_refresh_loop, exclusive=True)

    async def _connect_and_refresh_loop(self) -> None:
        """Background loop – mirrors old Worker but in Textual async worker."""
        connected = await asyncio.to_thread(self.agent.start)
        self.connected = connected
        if not connected:
            self.query_one("#llm-log", RichLog).write("[red]Failed to connect to remote agent[/]")
            return

        while True:
            await self._refresh_tree()
            await asyncio.sleep(2.5)  # TREE_INTERVAL like before
            if self.current_surface:
                await self._refresh_preview(self.current_surface)

    async def _refresh_tree(self) -> None:
        data = await asyncio.to_thread(self.agent.call, "tree")
        if data:
            self.tree_data = data.get("rows", [])
            tree = self.query_one("#tree-pane", Tree)
            tree.clear()
            tree.root.label = f"cmux @ {self.host} ({len(self.tree_data)} surfaces)"

            # Build proper hierarchical tree matching cmux structure:
            # window -> workspace -> pane -> surface (terminal or browser)
            # Group by window/ws/pane for full fidelity
            by_window: dict = {}
            for r in self.tree_data:
                win = r.get("window", "win:0")
                ws = r.get("ws", "ws:0")
                pane = r.get("pane", "pane:0")
                by_window.setdefault(win, {}).setdefault(ws, {}).setdefault(pane, []).append(r)

            for win, wss in by_window.items():
                win_node = tree.root.add(f"Window {win}", expand=True)
                for ws, panes in wss.items():
                    ws_title = next((p.get("ws_title","") for p in list(panes.values())[0]), ws)
                    ws_node = win_node.add(f"WS: {ws_title or ws}", expand=True)
                    for pane, surfs in panes.items():
                        pane_node = ws_node.add(f"Pane {pane}", expand=True)
                        for s in surfs:
                            typ = s.get("type", "terminal")
                            icon = "🖥️" if typ == "terminal" else "🌐"
                            label = f"{icon} {s.get('title','')} [{s.get('surface')}] tty={s.get('tty','')}"
                            node = pane_node.add_leaf(label, data=s)
                            if s.get("active"):
                                node.expand()

            self.query_one("#llm-log", RichLog).write(f"[dim]Hierarchical tree refreshed: {len(self.tree_data)} surfaces[/]")

    async def _refresh_preview(self, ref: str) -> None:
        data = await asyncio.to_thread(self.agent.call, "read", {"ref": ref, "lines": 80})
        if data:
            log = self.query_one("#preview-log", RichLog)
            log.clear()
            log.write(data[:2000] if isinstance(data, str) else str(data))  # truncate for demo

    def on_tree_node_selected(self, event: Tree.NodeSelected) -> None:
        if event.node and event.node.data:
            self.current_surface = event.node.data.get("surface")
            self.run_worker(self._refresh_preview, self.current_surface)

    async def action_attach(self) -> None:
        if not self.current_surface:
            return
        # For now: open a simple modal or switch to attach mode
        # In full version: dedicated AttachScreen with live key streaming + higher FPS preview
        self.query_one("#llm-log", RichLog).write(f"[cyan]ATTACH {self.current_surface} (Textual attach screen coming in Wave 2)[/]")
        # TODO: implement real attach using the "keys" + "read" protocol from agent

    def action_synthesize(self) -> None:
        """The killer new feature: LLM layer over multiple surfaces."""
        log = self.query_one("#llm-log", RichLog)
        log.write("[bold yellow]Synthesizing across surfaces with LLM...[/]")

        # In real impl: pick top N surfaces (or user-selected), call agent.read_many,
        # feed the texts + context (titles, agent types if detectable) to LLM.
        # Prompt example:
        # "You are an expert coding agent orchestrator. Here are live screens from multiple terminals.
        #  For each: identify the agent (Claude/Hermes/etc), current task, last significant output or error,
        #  state (working / stuck / waiting for input / done). Then give a prioritized list of what needs attention.
        #  Output as clean markdown list."
        #
        # Use user's stack: e.g. openai.AsyncOpenAI(base_url="https://llm.borg.tools/v1", api_key=...)
        # or call Hermes for long-term memory of surfaces.

        # Demo for now:
        log.write("Demo synthesis (replace with real LLM call + read_many):\n"
                  "- surface:3 (faktury-CC): Claude Code – implementing parser fix, last output looks like tests running\n"
                  "- surface:7 (hermes): Hermes – memory compaction in progress, no errors visible\n"
                  "Prioritized: 1) Check faktury tests (possible hang), 2) Hermes compaction status")

    def action_refresh_tree(self) -> None:
        self.run_worker(self._refresh_tree)

    def action_help(self) -> None:
        self.query_one("#llm-log", RichLog).write(
            "Help: r=refresh, a=attach (WIP), f=focus, Ctrl+S=synthesize with LLM, q=quit. "
            "Full mouse + command palette coming."
        )


def run_app():
    """Entry point for the new SOTA Textual TUI."""
    import os
    host = os.environ.get("CMUX_REMOTE_HOST") or os.environ.get("CMUX_MINI_HOST", "desk")
    app = CmuxRemoteApp(host=host)
    app.run()
