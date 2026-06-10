#!/usr/bin/env python3
"""cmux-mini remote agent — runs ON the macmini, spoken to over one persistent
SSH pipe. Newline-JSON requests on stdin, newline-JSON responses on stdout."""
import json
import os
import subprocess
import sys

CMUX = os.environ.get("CMUX_BIN", "/Applications/cmux.app/Contents/Resources/bin/cmux")


def _pw():
    var = "CMUX_SOCKET_" + "PASS" + "WORD"
    pw = os.environ.get(var, "")
    if pw:
        return pw
    try:
        env = os.path.expanduser("~/.hermes/.env")
        with open(env) as f:
            for line in f:
                line = line.strip()
                if line.startswith(var + "="):
                    return line.split("=", 1)[1].strip().strip('"').strip("'")
    except OSError:
        pass
    return ""


PW = _pw()


def run_cmux(argv, capture=True):
    cmd = [CMUX, "--password", PW] + argv
    p = subprocess.run(cmd, text=True, capture_output=capture)
    return p.returncode, (p.stdout or ""), (p.stderr or "")


def flatten(tree):
    rows = []
    for w in tree.get("windows", []):
        for ws in w.get("workspaces", []):
            for pane in ws.get("panes", []):
                for s in pane.get("surfaces", []):
                    rows.append({
                        "window": w.get("ref"), "ws": ws.get("ref"),
                        "ws_title": ws.get("title") or "", "ws_selected": ws.get("selected"),
                        "ws_active": ws.get("active"), "ws_pinned": ws.get("pinned"),
                        "pane": pane.get("ref"), "surface": s.get("ref"),
                        "title": s.get("title") or "", "type": s.get("type") or "",
                        "tty": s.get("tty") or "", "selected": s.get("selected"),
                        "active": s.get("active"), "url": s.get("url") or "",
                    })
    return rows


def op_tree(args):
    rc, out, err = run_cmux(["tree", "--json"])
    if rc != 0:
        raise RuntimeError(err.strip() or "tree failed")
    tree = json.loads(out)
    # Return both flat (for CLI compat) and full hierarchical for new TUI
    return {
        "rows": flatten(tree),
        "active": tree.get("active"),
        "full_tree": tree  # raw cmux structure for perfect hierarchy mirroring
    }


def op_read(args):
    ref = args["ref"]; lines = int(args.get("lines", 200))
    argv = ["read-screen", "--surface", ref, "--lines", str(lines)]
    if args.get("sb"):
        argv.append("--scrollback")
    rc, out, err = run_cmux(argv)
    return out.rstrip("\n") if rc == 0 else f"<read error: {err.strip()}>"


def op_read_many(args):
    refs = args["refs"]; lines = int(args.get("lines", 200))
    blocks = {}
    for r in refs:
        rc, out, err = run_cmux(["read-screen", "--surface", r, "--lines", str(lines)])
        blocks[r] = out.rstrip("\n") if rc == 0 else f"<err: {err.strip()}>"
    return blocks


def op_cmux(args):
    rc, out, err = run_cmux(args["argv"])
    return {"rc": rc, "out": out, "err": err}


def op_keys(args):
    """Send a batch of input events to a surface in one round-trip, return screen after.
    events: list of ["text","<str>"] or ["key","<keyname>"]."""
    ref = args["ref"]
    for kind, val in args.get("events", []):
        if kind == "text":
            run_cmux(["send", "--surface", ref, val])
        else:
            run_cmux(["send-key", "--surface", ref, val])
    lines = int(args.get("lines", 200))
    rc, out, err = run_cmux(["read-screen", "--surface", ref, "--lines", str(lines)])
    return out.rstrip("\n") if rc == 0 else f"<err: {err.strip()}>"


OPS = {"tree": op_tree, "read": op_read, "read_many": op_read_many,
       "cmux": op_cmux, "keys": op_keys}


def main():
    sys.stdout.write(json.dumps({"id": 0, "ok": True, "data": "ready"}) + "\n")
    sys.stdout.flush()
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except Exception:
            continue
        rid = req.get("id"); op = req.get("op")
        if op == "quit":
            break
        try:
            data = OPS[op](req.get("args") or {})
            resp = {"id": rid, "ok": True, "data": data}
        except Exception as e:
            resp = {"id": rid, "ok": False, "err": str(e)}
        sys.stdout.write(json.dumps(resp) + "\n")
        sys.stdout.flush()


if __name__ == "__main__":
    main()
