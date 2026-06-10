# cmux-remote-tui

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.8%2B-blue.svg)](https://www.python.org/)
[![Zero dependencies](https://img.shields.io/badge/dependencies-none-success.svg)](pyproject.toml)
[![PRs welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](#contributing)

**Control your [cmux](https://github.com/manaflow-ai/cmux) terminal on another
machine, over SSH, from a single fast TUI.** Browse every workspace and terminal,
fuzzy-find the one you want, watch it live, and **attach interactively** — your
keystrokes stream straight to the remote terminal, so model pickers, menus, `vim`,
`ESC` dialogs and your coding agents all just work.

> Your beefy always-on desktop runs the agents. Your laptop drives them.

```
 cmux @ desk  ● live  (12 surfaces)  /fakt
 ────────────────────────────────────────────────────────────────────────
 ● faktury-CC          ~                │  Opus 4.8 (1M) · auto mode on
   ✳ Fix parser bugs   ✳ Claude Code   │  ❯ implement the fix and run tests
   ia-build3           ~                │  ────────────────────────────────
   hermes              hermes           │  -- INSERT -- ⏵⏵ auto · ← agents
 ────────────────────────────────────────────────────────────────────────
 ↵/a attach  f focus  r rename  n new  x close  m move  s send  /find  ?help  q
```

---

## Why

cmux is a terminal built for coding agents. It's brilliant on the machine it runs
on — but if that machine is your Mac mini in the corner and you're on the couch
with a laptop, there's no built-in way to see and steer all those terminals
remotely. SSH gets you *one* shell; it doesn't get you the *topology* (which
agent is in which workspace, what's on each screen) or the ability to jump in.

`cmux-remote-tui` gives you the whole picture and full control from anywhere on
your network (great with [Tailscale](https://tailscale.com/)).

## Features

- **Live topology** — every window / workspace / pane / terminal, refreshed in the
  background.
- **Fuzzy find** — press `/`, type a few letters, jump to any terminal instantly.
- **Live preview** — see the current screen of the selected terminal, updating in
  real time, side-by-side with the list.
- **Interactive attach** — press `Enter`: go fullscreen on one terminal and type
  into it live. Arrows, `Tab`/`Shift-Tab`, `Esc`, `Ctrl-*`, everything passes
  through, so **model pickers and TUIs inside the remote terminal are fully
  usable**. `Ctrl-]` to detach.
- **Manage workspaces** — focus, rename, create, close, move surfaces, pin, flash.
- **`read all`** — dump the screen of every terminal at once (handy for agents and
  scripts).
- **Genuinely fast** — a tiny persistent agent on the remote host keeps the cmux
  connection warm, so requests cost ~1 network round-trip (≈0.1–0.2s on a LAN)
  instead of spawning a fresh `ssh + shell + cmux` every time. A background thread
  owns all I/O; the UI never blocks.

## How it works

```
┌── your laptop ───────────┐         ┌── remote host (runs cmux) ──┐
│  cmux-remote (TUI)        │  one    │  agent.py  ──►  cmux CLI    │
│   ├─ UI thread (30fps)    │ persist │   (stdlib only, no deps)    │
│   └─ worker thread ──────────SSH───►│   holds the socket warm     │
└──────────────────────────┘  pipe   └─────────────────────────────┘
```

The agent is ~120 lines of dependency-free Python that just shells out to the
`cmux` CLI already on the remote host and speaks newline-delimited JSON over the
SSH pipe. The client keeps the pipe open (SSH `ControlMaster`) and never lets
network I/O touch the render loop.

> **The trick that makes attach possible:** cmux scopes `read`/`send` to the
> caller's own pane *when the caller is itself a cmux terminal*. An SSH caller has
> no surface of its own, so it can read **and send keys to** any surface — which
> is exactly what we need to mirror and drive a remote terminal.

## Requirements

- **Remote host:** [cmux](https://github.com/manaflow-ai/cmux) installed and
  running, plus Python 3 and SSH access.
- **Local machine:** Python 3 and an SSH client. No third-party packages.
- A working SSH connection to the remote host (an entry in `~/.ssh/config` is
  recommended; pairs beautifully with Tailscale).

## Install

```bash
git clone https://github.com/vizi2000/cmux-remote-tui
cd cmux-remote-tui
./install.sh <ssh-host>        # e.g. ./install.sh desk   or  user@10.0.0.5
```

This copies the client to `~/.local/bin/cmux-remote` and the agent to the remote
host. Make sure `~/.local/bin` is on your `PATH`.

Or run straight from the repo without installing:

```bash
CMUX_REMOTE_HOST=<ssh-host> python3 -m cmux_remote_tui
```

## Usage

```bash
cmux-remote                       # launch the TUI (uses $CMUX_REMOTE_HOST)
cmux-remote --host desk           # or pass the host explicitly
cmux-remote ls                    # compact list of all remote terminals
cmux-remote read all              # dump every terminal's screen
cmux-remote read surface:11       # dump one terminal (with scrollback)
cmux-remote raw list-workspaces   # run any cmux command on the remote host
cmux-remote ssh                   # plain interactive ssh to the host
```

### Keys (TUI)

| Key | Action |
|-----|--------|
| `j` / `k` / arrows | move selection |
| `g` / `G` | top / bottom |
| `Ctrl-D` / `Ctrl-U` | half-page |
| `/` then type | fuzzy filter · `c` clears it |
| `Enter` / `a` | **attach** (interactive, live) |
| `f` | focus the surface on the remote |
| `o` | focus + raise the remote window |
| `r` · `n` · `x` | rename · new · close workspace |
| `m` | move surface to another workspace |
| `s` · `!` | send a line of text · send a single key |
| `P` · `b` | pin/unpin · flash (bell) |
| `p` | toggle live preview |
| `[` / `]` · `TAB` | scroll preview · move focus to preview |
| `R` / `F5` | force refresh |
| `?` | help overlay |
| `q` / `Esc` | quit |

**In attach mode:** every key goes to the remote terminal. Press **`Ctrl-]`** to
detach (because `Esc` has to pass through to whatever's running).

## Configuration

| Env var | Default | Meaning |
|---------|---------|---------|
| `CMUX_REMOTE_HOST` | — | SSH host to connect to (or use `--host`) |
| `CMUX_REMOTE_AGENT` | `~/.local/lib/cmux-remote-tui/agent.py` | agent path on the remote host |
| `CMUX_BIN` | `/Applications/cmux.app/Contents/Resources/bin/cmux` | cmux CLI path on the remote host |
| `CMUX_SOCKET_PASSWORD` | — | cmux socket password (read on the remote host) |

## Limitations

- Attach is screen-mirroring + key-injection, not a raw PTY, so very high-FPS,
  full-screen redraws (e.g. fast `htop`) update at ~5–6 fps. Pickers, menus,
  prompts, and editing feel smooth.
- Function keys (`F1`–`F12`) aren't currently mapped (cmux doesn't accept them via
  `send-key`).

## Contributing

Issues and PRs welcome. The whole thing is three small, dependency-free Python
files (`client.py`, `tui.py`, `agent.py`) — easy to read and hack on.

## License

MIT © Wojciech Wiesner
