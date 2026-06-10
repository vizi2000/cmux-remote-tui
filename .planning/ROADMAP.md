# cmux-remote-tui Roadmap

## Vision
A state-of-the-art, interactive remote TUI that not only mirrors every capability of the local cmux app but surpasses it for power users running many AI agents across machines. It provides perfect fidelity to cmux's window/workspace/pane/surface/browser model + unique superpowers (LLM synthesis layer, cross-surface intelligence, better workflows than the native GUI).

## Current (v0.1 - raw MVP)
- Curses-based TUI (tui.py)
- Persistent SSH + minimal agent (agent.py)
- Basic flat list + live preview + attach
- CLI helpers (client.py)
- Zero deps, fast on LAN/Tailscale

## v0.2 - SOTA TUI + Full Parity + LLM Layer (current phase)
- Switch to Textual for modern, beautiful, interactive, mouse+keyboard, reactive UI
- Hierarchical tree view matching exact cmux structure (windows > workspaces > panes > surfaces)
- Full feature parity: all tree/read/send/send-key/workspace/browser/notification/status/progress/log commands exposed beautifully in the TUI
- Dedicated browser control surface/panel (map all `cmux browser` verbs)
- LLM Synthesis Layer: background or on-demand LLM that reads multiple surfaces, understands agent states, synthesizes "what's happening where", produces prioritized actionable lists, detects stuck/blocked agents
- Better-than-original features:
  - Smart "Conductor" view: LLM-powered overview + "what should I focus on next?"
  - Cross-surface search and commands (broadcast, targeted LLM instructions)
  - Persistent memory of surface states (integrate with Hermes/Honcho if available)
  - Advanced preview: syntax-aware, diff view, agent output highlighting
  - Multiple layouts: classic list+preview, split overview, full conductor mode
- UX polish: themes, better performance (virtual rendering), mouse support, command palette, toasts, modals, undo
- Bug fixes from v0.1 (attach robustness, key mapping, connection recovery, etc.)
- Proper project structure (.planning, tests, CI skeleton)

## Future
- v0.3: Plugin system for custom surface types / LLM prompts
- Integration as first-class citizen in cmux ecosystem
- Web + TUI hybrid options
- Multi-host aggregation (one TUI for many remotes)

## Principles
- Fidelity first: anything you can do in local cmux, you can do here (and see the structure)
- Intelligence layer on top: the LLM synthesis makes the remote experience *superior* for orchestration of many agents
- Performance & simplicity: keep the fast persistent agent model; add deps only where they massively improve UX (Textual is worth it)
- User (Wojciech) workflow: optimized for Hermes + GSD + multi-agent coding sessions

Last updated: 2026-06-10
Mode: active improvement phase (v0.2)
