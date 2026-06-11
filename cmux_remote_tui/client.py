#!/usr/bin/env python3
"""cmux-remote-tui — fast remote control + TUI for the cmux terminal over SSH.

Architecture for speed:
  * ONE persistent SSH pipe to a tiny remote agent (agent.py) that holds the cmux
    connection locally on the remote host. Per-request cost ≈ 1 network RTT
    (Tailscale LAN ~5-30ms) instead of a fresh ssh+zsh+cmux spawn (~300-500ms).
  * A background worker thread owns ALL remote I/O. The UI thread NEVER blocks:
    it reads the latest snapshot from shared state and renders at ~60fps-feel.

CLI:
  cmux-remote               -> TUI (default)
  cmux-remote ls | tree | top
  cmux-remote read all | read <surface:N>
  cmux-remote ping | ssh | raw <cmux args>
"""
import json
import os
import shlex
import subprocess
import sys
import threading
import time
from typing import Any, Dict, List, Optional, Tuple, Union

HOST = os.environ.get("CMUX_REMOTE_HOST") or os.environ.get("CMUX_MINI_HOST", "")
# Where the remote agent lives on the target host (override with CMUX_REMOTE_AGENT).
REMOTE_AGENT = os.environ.get("CMUX_REMOTE_AGENT", "~/.local/lib/cmux-remote-tui/agent.py")
CTRL_PATH = os.path.expanduser("~/.ssh/cm-cmux-mini-%r@%h:%p")
SSH_OPTS = [
    "-o", "ControlMaster=auto",
    "-o", f"ControlPath={CTRL_PATH}",
    "-o", "ControlPersist=600",
    "-o", "BatchMode=yes",
    "-o", "ConnectTimeout=8",
    "-o", "ServerAliveInterval=15",
]


# ====================================================================== client

class Agent:
    """Persistent JSON-over-SSH-pipe client to the remote agent."""

    def __init__(self, host=HOST):
        self.host = host
        self.proc = None
        self.lock = threading.Lock()
        self.rid = 0
        self.connected = False
        self.last_err = ""

    def start(self):
        remote = (
            'source ~/.hermes/.env 2>/dev/null || true; '
            f'exec python3 {REMOTE_AGENT}'
        )
        cmd = ["ssh"] + SSH_OPTS + [self.host, "zsh", "-lc", remote]
        self.proc = subprocess.Popen(
            cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, text=True, bufsize=1,
        )
        # wait for ready banner
        line = self.proc.stdout.readline()
        try:
            banner = json.loads(line)
            self.connected = bool(banner.get("ok"))
        except Exception:
            self.connected = False
            self.last_err = "agent did not start"
        return self.connected

    def call(self, op, args=None, timeout=15):
        if not self.proc or self.proc.poll() is not None:
            if not self.start():
                return None
        with self.lock:
            self.rid += 1
            rid = self.rid
            req = {"id": rid, "op": op, "args": args or {}}
            try:
                self.proc.stdin.write(json.dumps(req) + "\n")
                self.proc.stdin.flush()
            except Exception as e:  # broken pipe -> reconnect once
                self.last_err = str(e)
                self.connected = False
                if not self.start():
                    return None
                self.proc.stdin.write(json.dumps(req) + "\n")
                self.proc.stdin.flush()
            line = self.proc.stdout.readline()
        if not line:
            self.connected = False
            self.last_err = "no response"
            return None
        try:
            resp = json.loads(line)
        except Exception:
            return None
        if not resp.get("ok"):
            self.last_err = resp.get("err", "")
            return None
        self.connected = True
        return resp.get("data")

    def get_full_tree(self) -> Dict[str, Any]:
        """Return full hierarchical cmux tree for domain model construction."""
        data = self.call("tree")
        if data and "full_tree" in data:
            return data["full_tree"]
        # Fallback: if old agent, reconstruct (not perfect but works)
        return {"windows": [], "active": data.get("active") if data else None}

    def cmux(self, argv):
        return self.call("cmux", {"argv": argv}) or {"rc": 1, "out": "", "err": "no conn"}

    def stop(self):
        try:
            if self.proc and self.proc.poll() is None:
                self.proc.stdin.write(json.dumps({"id": -1, "op": "quit"}) + "\n")
                self.proc.stdin.flush()
                self.proc.wait(timeout=2)
        except Exception:
            pass


# Fallback per-call helpers for plain CLI subcommands (no daemon needed)
def _ssh_cmux(argv, capture=True):
    remote = (
        'source ~/.hermes/.env 2>/dev/null || true; '
        'CMUX=/Applications/cmux.app/Contents/Resources/bin/cmux; '
        'exec "$CMUX" --password "${CMUX_SOCKET_PASSWORD:-}" '
        + " ".join(shlex.quote(a) for a in argv)
    )
    cmd = ["ssh"] + SSH_OPTS + [HOST, "zsh", "-lc", remote]
    return subprocess.run(cmd, text=True, capture_output=capture)


# ====================================================================== CLI

def cmd_ls(agent):
    data = agent.call("tree")
    rows = data["rows"] if data else []
    if not rows:
        print("No surfaces.")
        return 0
    headers = ["WS", "Workspace", "Surface", "Type", "TTY", "Flags"]
    table = []
    for r in rows:
        flags = []
        if r["ws_active"] or r["active"]:
            flags.append("active")
        if r["selected"]:
            flags.append("selected")
        table.append([r["ws"], r["ws_title"], r["title"], r["type"], r["tty"], " ".join(flags)])
    widths = [len(h) for h in headers]
    for row in table:
        for i, c in enumerate(row):
            widths[i] = max(widths[i], len(str(c)))
    fmt = "  ".join("{:%d}" % w for w in widths)
    print(fmt.format(*headers))
    print(fmt.format(*["-" * w for w in widths]))
    for row in table:
        print(fmt.format(*[str(c) for c in row]))
    return 0


def cmd_read(agent, args):
    data = agent.call("tree")
    rows = data["rows"] if data else []
    by = {r["surface"]: r for r in rows}
    term = [r["surface"] for r in rows if r["type"] == "terminal"]
    if not args or args[0] == "all":
        blocks = agent.call("read_many", {"refs": term, "lines": 200}) or {}
        for ref in term:
            r = by[ref]
            print("\n" + "=" * 100)
            print(f"  [{ref}] {r['ws_title']} / {r['title']}  (tty={r['tty']})")
            print("=" * 100)
            print(blocks.get(ref, "<no output>"))
        return 0
    print(agent.call("read", {"ref": args[0], "lines": 400, "sb": True}) or "")
    return 0


def main(argv):
    global HOST
    if len(argv) > 1 and argv[1] in ("-H", "--host"):
        HOST = argv[2]
        argv = [argv[0]] + argv[3:]
    cmd = argv[1] if len(argv) > 1 else "tui"
    if cmd in ("-h", "--help", "help"):
        print(__doc__)
        return 0
    if not HOST:
        print("No host configured. Set CMUX_REMOTE_HOST=<ssh-host> or pass --host <ssh-host>.",
              file=sys.stderr)
        return 2
    if cmd == "tui":
        from .tui import run_tui
        return run_tui(Agent(HOST))
    agent = Agent(HOST)
    if cmd in ("ls", "list"):
        return cmd_ls(agent)
    if cmd == "read":
        return cmd_read(agent, argv[2:])
    if cmd == "tree":
        return _ssh_cmux(["tree", "--all", "--id-format", "both"], capture=False).returncode
    if cmd == "top":
        return _ssh_cmux(["top", "--all"], capture=False).returncode
    if cmd == "ping":
        return _ssh_cmux(["ping"], capture=False).returncode
    if cmd == "ssh":
        return subprocess.call(["ssh"] + SSH_OPTS + [HOST])
    if cmd == "raw":
        if len(argv) < 3:
            print("usage: cmux-mini raw <cmux args>", file=sys.stderr)
            return 2
        return _ssh_cmux(argv[2:], capture=False).returncode
    print(f"unknown command: {cmd}\n", file=sys.stderr)
    print(__doc__, file=sys.stderr)
    return 2


def _console():
    """Console-script entry point (no args needed; reads sys.argv)."""
    raise SystemExit(main(sys.argv))


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
