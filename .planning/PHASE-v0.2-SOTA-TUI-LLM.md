# PHASE v0.2: State-of-the-Art TUI + LLM Synthesis + Full cmux Parity

**Goal**: Transform cmux-remote-tui from a functional curses MVP into the best way to work with cmux remotely — more powerful, more insightful, and more pleasant than using the native cmux GUI locally.

**Why this phase**:
- Current curses TUI is impressive for zero-deps but hits UX limits (flicker, limited layout, no mouse, hard to extend).
- cmux has rich structure (windows/workspaces/panes/surfaces + first-class browser) + agent hooks + notifications that are under-mapped.
- Unique opportunity: as a *remote* tool, we can add an LLM layer that aggregates understanding across all surfaces — something impossible or awkward in the single-machine GUI.

**Success criteria** (verification):
- Hierarchical, accurate view of full cmux object model
- Every major cmux capability (including browser automation, status/progress/logs, workspace mgmt) has first-class beautiful UI
- LLM "Conductor/Synthesis" panel that can read N surfaces, produce useful structured output (status per agent, stuck points, suggested next actions, synthesized todo list)
- Measurably better workflow for multi-agent orchestration than local cmux (user can articulate 3+ concrete advantages)
- No major regressions in speed/simplicity of the remote agent
- Clean, modern, interactive UI that feels "state of the art" (Textual + rich components)
- Bugs from v0.1 fixed (attach robustness, key coverage, connection handling, preview accuracy)

**Non-goals for this phase**:
- Web UI
- Full plugin system (postpone to v0.3)
- Changing the zero-dep agent philosophy on the remote side (we can add small optional things locally)

**Tech choices**:
- TUI framework: **Textual** (reactive, CSS, widgets, mouse, async workers, excellent for complex live UIs, perfect for "state of art" in Python 2026)
- Keep agent.py / protocol mostly as-is (or small extensions for browser + more metadata)
- LLM access: reuse user's existing stack (llm.borg.tools via OpenAI compat, or local via whatever Hermes/Honcho uses, configurable). Start with simple "summarize N surfaces" then iterate to structured extraction.
- Styling: dark theme inspired by cmux + modern TUI aesthetics (high contrast, good typography via Rich)

**High-level architecture changes**:
- New `textual_tui.py` (or replace tui.py) — Textual App with multiple views/screens:
  - Main: Tree (hierarchical cmux model) + Live Preview pane + optional LLM Summary pane
  - Conductor / Synthesis screen: LLM-powered overview + prioritized actions
  - Browser Control screen/panel: dedicated widgets for browser verbs
  - Command palette + full keyboard + mouse
- Enhanced State / reactive model
- New `llm.py` module: surface reader + prompt templates + LLM client (structured output where possible)
- Extend agent protocol minimally for richer metadata (agent type detection, surface kinds including browser)
- Keep client.py for CLI compatibility + add new subcommands (e.g. `cmux-remote synthesize`)

**Milestones / waves (use execute in parallel where possible)**:

Wave 1 — Foundation & Structure
- Proper project hygiene (git + .planning already started)
- Add textual + rich to dependencies (optional or required for TUI; keep pure curses as fallback for now or drop)
- Research full cmux object model and command surface (done via skill + README)
- Create data model for hierarchical surfaces (Window > Workspace > Pane > Surface + BrowserSurface)
- Basic Textual app skeleton that can connect via existing Agent and show a tree + preview

Wave 2 — Parity + Hierarchy
- Full tree view matching cmux `tree --all` structure
- Live updating preview (ANSI preserved via Rich)
- All existing actions (attach, focus, rename, new, close, move, send, pin, flash, refresh) reimplemented in nice UI
- Expose more cmux commands: notifications, status, progress, logs, list panes/panels, workspace actions
- Browser parity: special handling/surface type + panel with common verbs (open, goto, fill, click, get text/html/snapshot, eval, etc.)

Wave 3 — LLM Synthesis Layer (the "better than original" killer feature)
- Surface reader that can fetch current (or scrollback) content from one or many surfaces via the agent
- LLM client (configurable endpoint/model, support for the user's llm.borg.tools + local fallbacks)
- Prompt engineering + structured output for:
  - Per-surface status summary (what agent, current task, last output, state: working/stuck/waiting/error/done)
  - Global synthesis: "Current active work across machines", prioritized "needs attention" list
- UI: "Synthesis" panel or dedicated screen that can be refreshed on demand or periodically
- "Smart" features: "Ask LLM: where is the failing test?", "Synthesize todo from all open agents", one-click "send this summary as instruction to surface X"
- Integration hooks with user's other tools (Hermes memory, GSD, etc.) — at minimum allow exporting syntheses

Wave 4 — Polish, Interaction, Performance
- State-of-the-art design: beautiful Textual CSS, themes, icons (via textual or rich), smooth animations where appropriate, excellent keyboard navigation + mouse
- Advanced interactive modes beyond basic attach (e.g. "overlay commands", multi-surface command mode)
- Performance: virtualized tree, diff-based updates, background workers for everything heavy (including LLM calls)
- Bug fixes: robust attach (better key translation, higher effective FPS where possible), connection recovery, error surfaces, edge cases from real cmux (many windows, browser surfaces, agent hibernation, etc.)
- UX sugar: command palette, fuzzy everything, persistent layout prefs, session restore for the TUI itself, toasts, undo where sensible
- Documentation + examples updated (especially how the LLM layer makes daily agent orchestration better)

Wave 5 — Verification & Hardening
- Manual UAT against real cmux usage (multiple agents, browser work, long sessions)
- Add basic tests (at least for agent protocol, LLM prompt rendering, tree flattening)
- Performance benchmarks (latency of tree/read/attach vs raw ssh+cmux)
- Update README, add screenshots/GIFs of new UI + LLM features
- Ensure it remains "better for work" — collect 3-5 concrete workflows where the new TUI wins over local cmux + plain SSH

**Verification checklist** (for gsd-verify-work):
- Can I see and navigate the exact same hierarchy as `cmux tree`?
- Can I do everything I can do in local cmux (including browser automation) from the remote TUI?
- Does the LLM layer produce actionable, accurate-enough synthesis that saves me context switching?
- Is the UI pleasant and fast? (subjective + measured FPS/latency)
- No breakage of existing CLI / agent for power users who don't want the full TUI

**Risks & mitigations**
- Textual learning curve / perf on very large number of surfaces → start with reasonable scale (user's typical 10-30 surfaces), virtualize, profile
- LLM cost/latency/hallucination → make it optional, cache, use fast local models where possible, show raw + summary, user can edit prompts
- Scope creep → strict waves, ship v0.2 with core LLM "summarize selected surfaces" even if not perfect

**Dependencies added**
- textual (main TUI)
- rich (already powerful with Textual)
- (optional) openai or litellm / httpx for LLM (configurable, not hard dep if possible)

**Definition of Done for this phase**
- Working Textual-based TUI with hierarchical view + full current feature set + browser basics + initial LLM synthesis panel
- Updated docs + demo
- The TUI feels clearly superior for the user's multi-agent remote workflow
- Project is properly structured (this PLAN + verification)

**Next actions (after this plan is reviewed/accepted)**
1. Add textual to pyproject, basic "hello Textual" app that reuses the Agent class
2. Implement hierarchical data model + Tree widget
3. Port/ enhance existing actions
4. Add first LLM synthesis (simple "read N surfaces + prompt" )
5. Iterate on design and LLM prompts with real usage

Phase owner: User (with AI assistance)
Target: Make this the daily driver remote interface for cmux.
