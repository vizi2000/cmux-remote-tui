# Changelog

All notable changes to this project are documented here.

## [0.1.0] — 2026-06-07

Initial public release.

### Added
- Persistent SSH-pipe agent that keeps the cmux connection warm on the remote
  host (~1 network round-trip per request instead of a fresh `ssh + shell + cmux`
  spawn).
- Background worker thread for all remote I/O; the UI thread never blocks.
  Flicker-free curses rendering.
- Live topology view of every window / workspace / pane / terminal.
- Fuzzy find (`/`), vim-style navigation (`j/k`, `g/G`, `Ctrl-D/Ctrl-U`).
- Live preview of the selected terminal, refreshed in the background.
- **Interactive attach** (`Enter`/`a`): fullscreen live view with full keyboard
  passthrough — arrows, `Tab`/`Shift-Tab`, `Esc`, `Ctrl-*` — so model pickers and
  TUIs inside the remote terminal are fully usable. `Ctrl-]` detaches.
- Workspace management: focus, raise window, rename, new, close, move surface,
  pin, flash.
- CLI subcommands: `ls`, `tree`, `top`, `read all|<surface>`, `ping`, `ssh`,
  `raw <cmux args>`.
- One-command installer (`install.sh`) and `gh`-based publish script.
- Dependency-free: pure Python 3 standard library on both ends.
