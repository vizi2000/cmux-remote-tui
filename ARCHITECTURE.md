# cmux-remote-tui Architecture (v0.2+)

**Design Philosophy (Senior Dev, State of the Art 2026)**

- **Clean / Hexagonal Architecture**: Core business logic (cmux model, orchestration, synthesis) is independent of UI framework (Textual), transport (SSH), and LLM providers. UI, infrastructure, and external services are "adapters" that plug into ports (interfaces/protocols).
- **Domain-Driven Design (DDD) lite**: Explicit, rich domain model for cmux's hierarchy that matches the real app as closely as possible. This makes the TUI a faithful remote mirror + intelligence layer.
- **Event-Driven + Reactive**: Remote state changes are events. The UI (Textual) reacts to state. LLM synthesis is a reactive "view" over multiple surfaces.
- **Ports & Adapters (Hexagonal)**: 
  - Domain & Application core (no I/O, no frameworks).
  - Adapters: Textual UI, SSH transport, LLM providers (local CLI or API), cmux CLI on remote.
- **Minimalism on Remote, Power on Client**: The remote `agent.py` stays tiny, stdlib-only, and dumb (just proxy cmux commands + JSON). All intelligence (hierarchy, synthesis, UI, LLM) lives on the client (laptop). This keeps remote footprint zero and makes the TUI *better* than local cmux for orchestration across machines.
- **Extensibility for "Better than Original"**: The architecture deliberately makes it easy to add LLM-driven features that the local GUI can't have (global synthesis across surfaces/machines, smart conductor, cross-surface actions, memory integration with Hermes/Honcho).
- **Performance & Correctness First**: Persistent connections, background workers, diff-based updates, typed models, clear error boundaries.
- **Testability**: Core domain/application logic is pure and unit-testable. Adapters are thin and integration-tested.
- **User-Centric (Wojciech's Workflow)**: Optimized for multi-agent remote work (Hermes, Claude Code, etc.) over Tailscale. The LLM layer turns raw terminal noise into actionable "what's happening where" intelligence.

## High-Level Layers (Hexagonal)

```
┌─────────────────────────────────────────────────────────────┐
│                      Presentation (Textual)                 │
│  - CmuxRemoteApp (root)                                     │
│  - Widgets: HierarchicalTree, SurfacePreview, LlmConductor  │
│  - Screens / Modals for attach, browser control, commands   │
│  - Reactive bindings to Application State                   │
└───────────────────────────────┬─────────────────────────────┘
                                │ (observes / dispatches)
┌───────────────────────────────▼─────────────────────────────┐
│                 Application / Use Cases                     │
│  - CmuxOrchestrator (coordinates tree, attach, synthesis)   │
│  - SynthesisService (LLM layer: read N surfaces → prompt →  │
│                       structured state + prioritized list)  │
│  - CommandService (maps UI actions to cmux + extras)        │
│  - State (reactive domain snapshot, events)                 │
└───────────────────────────────┬─────────────────────────────┘
                                │ (ports)
┌───────────────────────────────▼─────────────────────────────┐
│                      Domain (Pure)                          │
│  - Models: CmuxTree, Window, Workspace, Pane, Surface       │
│    (TerminalSurface, BrowserSurface) + value objects        │
│  - Events: TreeUpdated, SurfaceScreenUpdated, SynthesisReady│
│  - Protocols: CmuxClient (port), LlmProvider (port)         │
└─────────────────────────────────────────────────────────────┘
          ▲                              ▲
          │ (adapters)                   │ (adapters)
┌─────────┴──────────┐         ┌─────────┴──────────┐
│ Infrastructure     │         │ LLM Adapters       │
│ - SshCmxClient     │         │ - LocalCliProvider │
│   (persistent SSH  │         │   (grok/claude/    │
│    + JSON protocol │         │    codex via subp) │
│    to remote agent)│         │ - OpenAiProvider   │
│ - (future) local   │         │   (OpenRouter +    │
│   cmux direct      │         │    any compat)     │
└────────────────────┘         └────────────────────┘

Remote Side (minimal, stays zero-dep):
  agent.py (receives JSON ops over SSH stdin/stdout,
            shells out to local `cmux` CLI, returns JSON.
            Supports tree, read, keys, cmux raw, read_many, etc.)
```

## Key Abstractions (Ports & Domain)

### Domain Models (immutable where possible, rich)
- `CmuxTree`: root with list of `Window`
- `Window` → `Workspace` (title, pinned, active) → `Pane` → `Surface`
  - `Surface` is a sealed union: `TerminalSurface` (tty, title, content) | `BrowserSurface` (url, title, etc.)
- Value objects: `SurfaceRef`, `AgentState` (inferred or from LLM), `ScreenSnapshot`
- This directly mirrors cmux's internal model (from `cmux tree --json` + browser surfaces) so the TUI is a faithful remote "mirror + brain".

### Ports (Protocols – dependency inversion)
```python
class CmuxClient(Protocol):
    async def get_tree(self) -> CmuxTree: ...
    async def read_screen(self, ref: SurfaceRef, lines: int = 200, scrollback: bool = False) -> ScreenSnapshot: ...
    async def send_keys(self, ref: SurfaceRef, events: list[KeyEvent]) -> ScreenSnapshot: ...
    async def execute(self, argv: list[str]) -> CommandResult: ...
    # ... full parity with cmux CLI + extras for browser, batch reads

class LlmProvider(Protocol):
    async def synthesize(self, prompt: str, context: SynthesisContext) -> SynthesisResult: ...
    # SynthesisContext = list of (surface_meta + screen_text)
    # SynthesisResult = structured: per_surface states + global prioritized list + raw text
```

### Application Services (orchestration, not business rules)
- `CmuxOrchestrator`: owns the live `CmuxTree` state, subscribes to updates from transport, exposes high-level methods (`attach(surface)`, `synthesize(selected_refs)`, `broadcast(...)`).
- `SynthesisService`: the "extra intelligence" layer. Fetches screens (via CmuxClient), builds rich prompt (with surface metadata, agent hints from titles/tty, user's GSD/Hermes context if available), calls LlmProvider, caches results, emits events.
- This is what makes the TUI *better than local cmux*: local cmux has no cross-surface LLM view, no remote aggregation, no "what needs my attention right now across all my agents on all machines".

### Transport / Infrastructure
- Persistent SSH + ControlMaster + single JSON pipe to the tiny remote `agent.py`. This is the secret sauce for low latency (1 RTT instead of full ssh+shell).
- The remote agent remains a thin, auditable, stdlib-only proxy. Never put LLM or heavy logic there.
- Future: could add a "local direct" adapter (no SSH) for when running on the same machine.

### Presentation (Textual)
- `CmuxRemoteApp` is a thin coordinator + reactive views.
- Uses Textual's reactive system + workers for background I/O.
- Widgets are "dumb" – they render domain state and emit high-level messages ("AttachRequested", "SynthesizeRequested").
- Multiple "views" or screens: main tree+preview+llm, dedicated browser control, conductor-only mode, etc.
- Styling via Textual CSS (cmux-inspired dark theme + modern TUI aesthetics).

### Data Flow (Live + Intelligent)
1. Background worker (Textual worker or asyncio task) periodically or on events calls `CmuxClient.get_tree()` / `read_screen()`.
2. Domain model updated → events published.
3. Textual UI reacts (tree refreshes, previews update).
4. User actions (attach, send, "synthesize these") go through Application services.
5. For LLM: `SynthesisService` collects N snapshots → builds prompt (template + surface meta + raw text + optional user context from Hermes) → `LlmProvider.synthesize(...)` → structured result → UI + optional export to memory.

### Why This Is Senior / State of the Art
- **Decoupled & Testable**: You can unit-test SynthesisService with fake CmuxClient + fake LlmProvider. UI can be tested with Textual's testing tools.
- **Extensible without Rot**: New cmux command? Add to CmuxClient port + one adapter method. New LLM trick (structured JSON mode, tool use, multi-turn conductor)? New method on LlmProvider. New UI view? New widget/screen that consumes the same domain state.
- **Performance by Design**: Persistent transport + background workers + reactive (only re-render what changed) + virtualized tree (Textual handles large lists well).
- **"Better than Original" Built In**: The architecture makes the LLM layer a first-class citizen that can see *across* the entire cmux topology on one or many machines. Local cmux GUI is great per-machine; this becomes the "god view + AI co-pilot" for the whole fleet of agents.
- **Fidelity + Superpowers**: We map the real cmux object model (not a dumb flat list) so every native feature (browser surfaces, per-surface status, etc.) has a natural home. Then we layer intelligence on top that the original cannot have.
- **Maintainable at Scale**: Small files, clear boundaries, no god classes. The old curses tui.py was already doing some of this (Worker + State separation) – we evolve it cleanly instead of throwing it away.
- **User Workflow Alignment**: Designed around your reality (remote beefy machines + laptop driver, Hermes + GSD + many parallel agents, Tailscale). The LLM synthesis directly attacks context-switching pain.

## Current Implementation Status (Wave Progress)

(See .planning/PHASE-v0.2-SOTA-TUI-LLM.md for the wave breakdown.)

- Wave 1 (Foundation): Done – git + .planning, Textual skeleton, llm.py abstraction with your exact providers (local clis + openrouter + openai-compat), basic integration.
- Wave 2 (Parity + Hierarchy): In progress – textual_app.py already has improved hierarchical Tree building from the flat rows (we should evolve the protocol/agent to return richer nested data for perfect fidelity).
- Wave 3 (LLM): Partially wired – `action_synthesize` now does real `read_many` + calls the pluggable LLM. Prompt is the "orchestrator" one. Next: make it background, add structured output (Pydantic models for per-surface state + global list), caching, "send to surface" actions.
- Later waves: Polish (Textual CSS, mouse, command palette, virtualized views), full browser surface support, performance, verification against real multi-agent usage.

## Remote Agent (agent.py) – Keep It Simple

It remains the thin proxy. We only extend it when we need *new* data from cmux (e.g. richer tree with browser metadata, per-surface agent hints if detectable). Never put synthesis logic here.

## Next Architectural Refinements (as we iterate)

- Introduce explicit `CmuxClient` Protocol + concrete `SshCmuxClient`.
- Richer domain models (dataclasses / Pydantic) instead of dicts – `Surface`, `SynthesisResult`, etc.
- Event bus or Textual's message system for decoupling (TreeUpdated, SynthesisCompleted).
- Configuration object (pydantic-settings or simple dataclass) for hosts, LLM providers, refresh intervals, etc.
- Optional: small persistence for surface history / past syntheses (can tie into your Hermes/Honcho memory).
- Dependency injection for the app (e.g. `CmuxRemoteApp(client=..., llm=...)`) for testability.

This architecture keeps the spirit of the original (tiny, fast, remote-first) while giving us a solid foundation to deliver a TUI that is not just "as good as" local cmux but *noticeably better* for your actual daily work with many agents across machines.

If anything feels off or you want to adjust layers/abstractions before we go deeper into implementation waves, say the word.
