"""cmux-mini TUI — fast, fluid curses interface for remote cmux management.

Design principles (senior TUI/UX):
  * The UI thread NEVER does network I/O. A single worker thread drains a request
    queue and updates shared snapshots; the UI renders whatever is current at
    ~33ms cadence, so keys feel instant even while data refreshes in the bg.
  * Flicker-free: we don't erase the whole screen; we repaint cells and clear to
    EOL per line. No full-screen clear() per frame.
  * Navigate by typing: `/` opens a fuzzy filter that narrows the list live.
  * Vim muscle memory: j/k, g/G, Ctrl-D/Ctrl-U, n/N within filter.
  * Inline command/prompt bar (bottom) — non-blocking, never freezes the loop.
  * Optimistic + async actions: fire the request, show a transient toast, refresh
    arrives from the worker without blocking.

Keybindings shown in the help bar; press `?` for the full overlay.
"""
import curses
import threading
import time
from collections import deque


TREE_INTERVAL = 2.5       # bg tree refresh cadence (s)
PREVIEW_INTERVAL = 1.5    # bg preview refresh cadence (s)
FRAME = 0.033             # UI tick (~30fps)


# ------------------------------------------------------------------ worker

class Worker(threading.Thread):
    """Owns all remote I/O. UI pushes jobs; worker updates shared state."""

    def __init__(self, agent, state):
        super().__init__(daemon=True)
        self.agent = agent
        self.state = state
        self.jobs = deque()
        self.jobs_lock = threading.Lock()
        self.wake = threading.Event()
        self.stop_flag = False
        self.last_tree = 0.0
        self.last_preview = 0.0

    def submit(self, kind, **kw):
        with self.jobs_lock:
            self.jobs.append((kind, kw))
        self.wake.set()

    def _take(self):
        with self.jobs_lock:
            return self.jobs.popleft() if self.jobs else None

    def run(self):
        if not self.agent.start():
            self.state.set_conn(False, self.agent.last_err or "connect failed")
        else:
            self.state.set_conn(True, "")
            self._refresh_tree()
        while not self.stop_flag:
            job = self._take()
            if job:
                self._do(job)
                continue
            now = time.time()
            if now - self.last_tree >= TREE_INTERVAL:
                self._refresh_tree()
            elif (self.state.auto_preview and self.state.cur_ref
                  and now - self.last_preview >= PREVIEW_INTERVAL):
                self._refresh_preview(self.state.cur_ref, self.state.preview_lines)
            else:
                self.wake.wait(timeout=0.25)
                self.wake.clear()

    def _do(self, job):
        kind, kw = job
        if kind == "preview":
            self._refresh_preview(kw["ref"], kw.get("lines", 120), force=True)
        elif kind == "tree":
            self._refresh_tree()
        elif kind == "action":
            data = self.agent.cmux(kw["argv"])
            ok = data.get("rc", 1) == 0
            msg = kw.get("toast", "done") if ok else (data.get("err", "").strip()[:80] or "error")
            self.state.toast(("ok " if ok else "ERR ") + msg)
            self._refresh_tree()
        elif kind == "keys":
            # interactive attach: send batched events, get fresh screen back fast
            data = self.agent.call("keys", {"ref": kw["ref"], "events": kw["events"], "lines": kw.get("lines", 200)})
            if data is not None:
                self.state.set_preview(kw["ref"], data)
        elif kind == "attach_read":
            data = self.agent.call("read", {"ref": kw["ref"], "lines": kw.get("lines", 200)})
            if data is not None:
                self.state.set_preview(kw["ref"], data)

    def _refresh_tree(self):
        data = self.agent.call("tree")
        self.last_tree = time.time()
        if data is None:
            self.state.set_conn(False, self.agent.last_err or "tree failed")
            return
        self.state.set_conn(True, "")
        self.state.set_rows(data["rows"], data.get("active"))

    def _refresh_preview(self, ref, lines, force=False):
        data = self.agent.call("read", {"ref": ref, "lines": lines})
        self.last_preview = time.time()
        if data is not None:
            self.state.set_preview(ref, data)


# ------------------------------------------------------------------ state

class State:
    def __init__(self):
        self.lock = threading.Lock()
        self.rows = []
        self.active = None
        self.preview = {}            # ref -> text
        self.cur_ref = None
        self.preview_lines = 120
        self.auto_preview = True
        self.connected = False
        self.conn_err = ""
        self.toast_msg = ""
        self.toast_until = 0.0
        self.gen = 0                 # bumps on any data change -> redraw trigger

    def _bump(self):
        self.gen += 1

    def set_rows(self, rows, active):
        with self.lock:
            self.rows = rows
            self.active = active
            self._bump()

    def get_rows(self):
        with self.lock:
            return list(self.rows)

    def set_preview(self, ref, text):
        with self.lock:
            self.preview[ref] = text
            self._bump()

    def get_preview(self, ref):
        with self.lock:
            return self.preview.get(ref, "")

    def set_conn(self, ok, err):
        with self.lock:
            self.connected = ok
            self.conn_err = err
            self._bump()

    def toast(self, msg, secs=3.0):
        with self.lock:
            self.toast_msg = msg
            self.toast_until = time.time() + secs
            self._bump()


# ------------------------------------------------------------------ TUI

class TUI:
    def __init__(self, agent, stdscr):
        self.agent = agent
        self.scr = stdscr
        self.st = State()
        self.worker = Worker(agent, self.st)
        self.sel = 0
        self.scroll = 0
        self.preview_scroll = 0
        self.focus_preview = False
        # filter mode
        self.filtering = False
        self.filter_q = ""
        # prompt (inline command bar) state machine
        self.prompt_active = False
        self.prompt_label = ""
        self.prompt_buf = ""
        # interactive attach mode
        self.attach = False
        self.attach_ref = None
        self.attach_pending = []      # buffered events to flush as one batch
        self.attach_last_send = 0.0
        self.attach_lines = 200
        self.prompt_cb = None
        self.show_help = False
        self.last_gen = -1
        self.last_size = (0, 0)

    # ----- derived list (filtered) ---------------------------------

    def visible_rows(self):
        rows = self.st.get_rows()
        if not self.filter_q:
            return rows
        q = self.filter_q.lower()
        def score(r):
            hay = (r["ws_title"] + " " + r["title"] + " " + r["surface"] + " " + r["tty"]).lower()
            return _fuzzy(q, hay)
        scored = [(score(r), r) for r in rows]
        return [r for s, r in scored if s is not None]

    def cur(self):
        rows = self.visible_rows()
        if not rows:
            return None
        self.sel = max(0, min(self.sel, len(rows) - 1))
        r = rows[self.sel]
        self.st.cur_ref = r["surface"]
        self.st.preview_lines = max(60, self.preview_lines_for())
        return r

    def preview_lines_for(self):
        h, _ = self.scr.getmaxyx()
        return max(60, h * 2)

    # ----- actions (all async via worker) --------------------------

    def a_focus(self, raise_win=False):
        r = self.cur()
        if not r:
            return
        self.worker.submit("action", argv=["select-workspace", "--workspace", r["ws"]], toast=f"focus {r['ws_title']}")
        self.worker.submit("action", argv=["move-surface", "--surface", r["surface"], "--pane", r["pane"], "--focus", "true"], toast="focused")
        if raise_win:
            self.worker.submit("action", argv=["focus-window", "--window", r["window"]], toast="window raised")

    # ----- interactive attach (live, keystrokes stream to the surface) -----

    def a_attach(self):
        r = self.cur()
        if not r or r["type"] != "terminal":
            self.st.toast("can only attach to a terminal")
            return
        self.attach = True
        self.attach_ref = r["surface"]
        self.attach_pending = []
        self.preview_scroll = 0
        self.st.toast("ATTACH " + r["surface"] + " — Ctrl-] to detach")
        self.worker.submit("attach_read", ref=r["surface"], lines=self.attach_screen_lines())

    def exit_attach(self):
        self.flush_attach(force=True)
        self.attach = False
        self.attach_ref = None
        self.st.toast("detached")

    def attach_screen_lines(self):
        h, _ = self.scr.getmaxyx()
        return max(20, h)

    def queue_event(self, kind, val):
        self.attach_pending.append([kind, val])

    def flush_attach(self, force=False):
        if not self.attach_ref:
            return
        now = time.time()
        if not self.attach_pending and not force:
            return
        # coalesce: batch all pending events into one round-trip
        if self.attach_pending or force:
            events = self.attach_pending
            self.attach_pending = []
            self.attach_last_send = now
            self.worker.submit("keys", ref=self.attach_ref,
                               events=events, lines=self.attach_screen_lines())

    def a_flash(self):
        r = self.cur()
        if r:
            self.worker.submit("action", argv=["trigger-flash", "--surface", r["surface"]], toast="flashed")

    def a_pin(self):
        r = self.cur()
        if r:
            self.worker.submit("action", argv=["workspace-action", "--action", "toggle-pin", "--workspace", r["ws"]], toast="pin toggled")

    def a_close(self):
        r = self.cur()
        if r:
            self.open_prompt(f"close '{r['ws_title'] or r['ws']}'? type y", lambda v: (
                self.worker.submit("action", argv=["close-workspace", "--workspace", r["ws"]], toast="closed")
                if v.strip().lower() == "y" else None))

    def a_rename(self):
        r = self.cur()
        if r:
            self.open_prompt(f"rename '{r['ws_title']}' →", lambda v: (
                self.worker.submit("action", argv=["rename-workspace", "--workspace", r["ws"], v], toast="renamed")
                if v.strip() else None), preset=r["ws_title"])

    def a_new(self):
        self.open_prompt("new workspace name", lambda name: (
            self.open_prompt("command (optional)", lambda cmd: (
                self.worker.submit("action",
                    argv=(["new-workspace", "--name", name] + (["--command", cmd] if cmd.strip() else [])),
                    toast="created")))
            if name.strip() else None))

    def a_send_text(self):
        r = self.cur()
        if r:
            self.open_prompt(f"send → {r['surface']}", lambda v: [
                self.worker.submit("action", argv=["send", "--surface", r["surface"], v], toast="sent"),
                self.worker.submit("action", argv=["send-key", "--surface", r["surface"], "Enter"], toast="↵"),
            ] if v else None)

    def a_send_key(self):
        r = self.cur()
        if r:
            self.open_prompt(f"key → {r['surface']} (Enter/C-c/Up)", lambda v: (
                self.worker.submit("action", argv=["send-key", "--surface", r["surface"], v], toast=f"key {v}")
                if v.strip() else None))

    def a_move(self):
        r = self.cur()
        if not r:
            return
        rows = self.st.get_rows()
        wss = []
        for x in rows:
            if x["ws"] not in [w[0] for w in wss]:
                wss.append((x["ws"], x["ws_title"]))
        menu = " ".join(f"{i+1}={t or ref}" for i, (ref, t) in enumerate(wss))
        self.open_prompt(f"move {r['surface']} to # [{menu}]", lambda v: (
            self.worker.submit("action",
                argv=["move-surface", "--surface", r["surface"], "--workspace",
                      wss[int(v) - 1][0] if v.isdigit() and 1 <= int(v) <= len(wss) else v],
                toast="moved") if v.strip() else None))

    # ----- inline prompt -------------------------------------------

    def open_prompt(self, label, cb, preset=""):
        self.prompt_active = True
        self.prompt_label = label
        self.prompt_buf = preset
        self.prompt_cb = cb

    def close_prompt(self, fire):
        cb, buf = self.prompt_cb, self.prompt_buf
        self.prompt_active = False
        self.prompt_label = ""
        self.prompt_buf = ""
        self.prompt_cb = None
        if fire and cb:
            cb(buf)

    # ----- key handling --------------------------------------------

    def handle_key(self, c):
        if self.attach:
            return self._key_attach(c)
        if self.prompt_active:
            return self._key_prompt(c)
        if self.filtering:
            return self._key_filter(c)
        return self._key_nav(c)

    # curses keycode -> cmux key name (for non-printable keys)
    SPECIAL = None  # built lazily (needs curses constants)

    def _special_map(self):
        if TUI.SPECIAL is None:
            TUI.SPECIAL = {
                curses.KEY_UP: "up", curses.KEY_DOWN: "down",
                curses.KEY_LEFT: "left", curses.KEY_RIGHT: "right",
                curses.KEY_HOME: "home", curses.KEY_END: "end",
                curses.KEY_NPAGE: "pagedown", curses.KEY_PPAGE: "pageup",
                curses.KEY_BACKSPACE: "backspace", curses.KEY_DC: "delete",
                curses.KEY_BTAB: "shift+tab",
                10: "enter", 13: "enter", curses.KEY_ENTER: "enter",
                9: "tab", 27: "esc", 127: "backspace", 8: "backspace",
                32: "space",
            }
        return TUI.SPECIAL

    def _key_attach(self, c):
        # Ctrl-]  (29) detaches — the universal escape hatch (ESC must pass through)
        if c == 29:
            self.exit_attach()
            return True
        smap = self._special_map()
        if c in smap and smap[c] != "space":
            self.queue_event("key", smap[c])
            self.flush_attach(force=True)
            return True
        if 1 <= c <= 26 and c not in (9, 10, 13):
            # Ctrl-A..Ctrl-Z  -> ctrl+<letter>
            self.queue_event("key", "ctrl+" + chr(ord("a") + c - 1))
            self.flush_attach(force=True)
            return True
        if 32 <= c < 127:
            # printable: buffer as text, coalesce a burst then flush
            self.queue_event("text", chr(c))
            return True
        return True

    def _key_prompt(self, c):
        if c in (27,):                      # Esc cancel
            self.close_prompt(False)
        elif c in (10, 13, curses.KEY_ENTER):
            self.close_prompt(True)
        elif c in (curses.KEY_BACKSPACE, 127, 8):
            self.prompt_buf = self.prompt_buf[:-1]
        elif 32 <= c < 127:
            self.prompt_buf += chr(c)
        return True

    def _key_filter(self, c):
        if c == 27:
            self.filtering = False
            self.filter_q = ""
        elif c in (10, 13, curses.KEY_ENTER):
            self.filtering = False           # keep query, jump to list
        elif c in (curses.KEY_BACKSPACE, 127, 8):
            self.filter_q = self.filter_q[:-1]
            self.sel = 0
        elif 32 <= c < 127:
            self.filter_q += chr(c)
            self.sel = 0
        return True

    def _key_nav(self, c):
        rows = self.visible_rows()
        n = len(rows)
        page = max(1, (self.scr.getmaxyx()[0] - 4) // 2)
        if c in (ord("q"), 27):
            return False
        elif c == ord("?"):
            self.show_help = not self.show_help
        elif c == ord("/"):
            self.filtering = True
        elif self.filter_q and c == ord("c"):
            self.filter_q = ""
            self.sel = 0
        elif c in (ord("j"), curses.KEY_DOWN):
            if self.focus_preview:
                self.preview_scroll += 1
            else:
                self.sel = min(n - 1, self.sel + 1)
        elif c in (ord("k"), curses.KEY_UP):
            if self.focus_preview:
                self.preview_scroll = max(0, self.preview_scroll - 1)
            else:
                self.sel = max(0, self.sel - 1)
        elif c == 4:                          # Ctrl-D
            self.sel = min(n - 1, self.sel + page)
        elif c == 21:                         # Ctrl-U
            self.sel = max(0, self.sel - page)
        elif c == ord("g"):
            self.sel = 0
        elif c == ord("G"):
            self.sel = n - 1
        elif c == 9:                          # TAB
            self.focus_preview = not self.focus_preview
        elif c in (10, 13, curses.KEY_ENTER, ord("a")):
            self.a_attach()
        elif c == ord("f"):
            self.a_focus()
        elif c == ord("o"):
            self.a_focus(raise_win=True)
        elif c == ord("r"):
            self.a_rename()
        elif c == ord("n"):
            self.a_new()
        elif c == ord("x"):
            self.a_close()
        elif c == ord("m"):
            self.a_move()
        elif c == ord("s"):
            self.a_send_text()
        elif c == ord("!"):
            self.a_send_key()
        elif c == ord("P"):
            self.a_pin()
        elif c == ord("b"):
            self.a_flash()
        elif c == ord("p"):
            self.st.auto_preview = not self.st.auto_preview
            self.st.toast("live preview " + ("ON" if self.st.auto_preview else "PAUSED"))
        elif c in (ord("R"), curses.KEY_F5):
            self.worker.submit("tree")
            r = self.cur()
            if r:
                self.worker.submit("preview", ref=r["surface"], lines=self.preview_lines_for())
            self.st.toast("refreshing…")
        elif c == ord("]"):
            self.preview_scroll += page
        elif c == ord("["):
            self.preview_scroll = max(0, self.preview_scroll - page)
        return True

    # ----- rendering (flicker-free) --------------------------------

    def addstr(self, y, x, s, attr=0, width=None):
        h, w = self.scr.getmaxyx()
        if y < 0 or y >= h or x >= w:
            return
        if width is None:
            width = w - x
        s = s[:max(0, width)]
        s = s + " " * (width - len(s)) if len(s) < width else s
        try:
            self.scr.addnstr(y, x, s, max(0, w - x), attr)
        except curses.error:
            pass

    def draw(self):
        h, w = self.scr.getmaxyx()
        if (h, w) != self.last_size:
            self.scr.erase()
            self.last_size = (h, w)

        if self.attach:
            self._draw_attach(h, w)
            return
        left_w = max(36, int(w * 0.42))
        rows = self.visible_rows()

        # keep selection in view
        body_top = 2
        body_h = h - 3
        if self.sel < self.scroll:
            self.scroll = self.sel
        if self.sel >= self.scroll + body_h:
            self.scroll = self.sel - body_h + 1
        self.scroll = max(0, self.scroll)

        # header
        conn = "●" if self.st.connected else "○"
        cattr = curses.color_pair(1) if self.st.connected else curses.color_pair(2)
        flt = f"  /{self.filter_q}" if self.filter_q else ""
        head = f" cmux @ {self.agent.host}  {conn} {'live' if self.st.connected else self.st.conn_err}  ({len(rows)} surfaces){flt}"
        self.addstr(0, 0, head, curses.A_BOLD | cattr, w)
        self.addstr(1, 0, "─" * w, curses.A_DIM)

        # left list
        last_ws = None
        y = body_top
        for i in range(self.scroll, min(len(rows), self.scroll + body_h)):
            r = rows[i]
            if r["ws"] != last_ws:
                last_ws = r["ws"]
            sel = (i == self.sel)
            mark = "●" if r["active"] else ("·" if r["selected"] else " ")
            wst = (r["ws_title"] or r["ws"])[:18]
            label = f"{mark} {wst:<18} {r['title'][:left_w-26]}"
            attr = curses.A_REVERSE if (sel and not self.focus_preview) else 0
            if sel and self.focus_preview:
                attr = curses.A_BOLD
            self.addstr(y, 0, " " + label, attr, left_w - 1)
            y += 1
        # clear remaining left lines
        while y < body_top + body_h:
            self.addstr(y, 0, "", 0, left_w - 1)
            y += 1

        # divider
        for yy in range(body_top, body_top + body_h):
            self.addstr(yy, left_w - 1, "│", curses.A_DIM, 1)

        # right preview
        r = self.cur()
        px = left_w
        pw = w - left_w
        if r:
            ptitle = f" {r['title']} [{r['surface']}] tty={r['tty']} {'▶live' if self.st.auto_preview else '⏸'}"
            self.addstr(body_top - 0, px, ptitle, curses.A_BOLD | curses.color_pair(3), pw)
            text = self.st.get_preview(r["surface"])
            lines = text.split("\n") if text else ["(loading…)"]
            view = lines[self.preview_scroll: self.preview_scroll + body_h - 1]
            for i in range(body_h - 1):
                pl = view[i] if i < len(view) else ""
                self.addstr(body_top + 1 + i, px, pl, 0, pw)

        # footer: prompt OR toast+keys
        if self.prompt_active:
            self.addstr(h - 1, 0, f" {self.prompt_label}: {self.prompt_buf}▏", curses.A_REVERSE | curses.color_pair(4), w)
        elif self.filtering:
            self.addstr(h - 1, 0, f" filter: {self.filter_q}▏   (Enter=keep  Esc=clear)", curses.A_REVERSE, w)
        else:
            toast = self.st.toast_msg if time.time() < self.st.toast_until else ""
            keys = "↵/a attach  f focus  o win  r rename  n new  x close  m move  s send  ! key  /find  ?help  q quit"
            line = (" " + toast + "   ").ljust(2) if toast else " "
            self.addstr(h - 1, 0, (line + keys)[:w].ljust(w), curses.A_REVERSE, w)

        if self.show_help:
            self._draw_help(h, w)
        self.scr.noutrefresh()
        curses.doupdate()

    def _draw_attach(self, h, w):
        ref = self.attach_ref
        # title bar
        title = f" ATTACH {ref}  ●live  —  Ctrl-] detach   (keys stream live to the terminal) "
        self.addstr(0, 0, title, curses.A_BOLD | curses.color_pair(3), w)
        text = self.st.get_preview(ref) if ref else ""
        lines = text.split("\n") if text else ["(loading…)"]
        # show the tail so the active prompt / picker is visible
        body_h = h - 1
        view = lines[-body_h:] if len(lines) > body_h else lines
        for i in range(body_h):
            pl = view[i] if i < len(view) else ""
            self.addstr(1 + i, 0, pl, 0, w)

    def _draw_help(self, h, w):
        lines = [
            "  cmux-mini — keys",
            "",
            "  j / k / ↑ ↓     move           Ctrl-D / Ctrl-U  half page",
            "  g / G           top / bottom   TAB              focus preview (scroll there)",
            "  / then type     fuzzy filter   c                clear filter",
            "  ↵ / a           ATTACH (live!) f                focus on remote",
            "  o               focus + raise  Ctrl-]           detach (in attach)",
            "  r               rename ws      n                new workspace",
            "  x               close ws       m                move surface",
            "  s               send text      !                send key",
            "  P               pin/unpin      b                flash",
            "  p               toggle live    R / F5           force refresh",
            "  [ / ]           scroll preview ?                toggle this help",
            "  q / Esc         quit",
            "",
            "  press ? to close",
        ]
        bw = max(len(x) for x in lines) + 4
        bh = len(lines) + 2
        y0 = max(0, (h - bh) // 2)
        x0 = max(0, (w - bw) // 2)
        for i in range(bh):
            row = ""
            if 1 <= i <= len(lines):
                row = lines[i - 1]
            self.addstr(y0 + i, x0, " " + row.ljust(bw - 1), curses.color_pair(4) | curses.A_BOLD, bw)

    # ----- main loop -----------------------------------------------

    def loop(self):
        curses.curs_set(0)
        curses.use_default_colors()
        try:
            curses.init_pair(1, curses.COLOR_GREEN, -1)
            curses.init_pair(2, curses.COLOR_RED, -1)
            curses.init_pair(3, curses.COLOR_CYAN, -1)
            curses.init_pair(4, curses.COLOR_YELLOW, -1)
        except curses.error:
            pass
        self.scr.nodelay(True)
        self.scr.timeout(0)
        self.worker.start()
        prev_ref = None
        last_attach_poll = 0.0
        while True:
            # drain all pending keys this frame for snappy response
            handled_any = False
            while True:
                c = self.scr.getch()
                if c == -1:
                    break
                handled_any = True
                if not self.handle_key(c):
                    self.worker.stop_flag = True
                    self.agent.stop()
                    return 0

            if self.attach:
                now = time.time()
                # flush buffered typed chars as one batch (coalesce a burst ~40ms)
                if self.attach_pending and now - self.attach_last_send >= 0.04:
                    self.flush_attach()
                # poll the attached screen frequently for live feel
                elif now - last_attach_poll >= 0.18:
                    last_attach_poll = now
                    self.worker.submit("attach_read", ref=self.attach_ref, lines=self.attach_screen_lines())
                if handled_any or self.st.gen != self.last_gen:
                    self.last_gen = self.st.gen
                    self.draw()
                time.sleep(0.02)
                continue

            # request preview when selection changes
            r = self.cur()
            if r and r["surface"] != prev_ref:
                prev_ref = r["surface"]
                self.preview_scroll = 0
                self.worker.submit("preview", ref=r["surface"], lines=self.preview_lines_for())
            # redraw if data changed, input happened, or periodically (live preview)
            if handled_any or self.st.gen != self.last_gen or self.st.auto_preview:
                self.last_gen = self.st.gen
                self.draw()
            time.sleep(FRAME)


def _fuzzy(q, hay):
    """Return a score (lower=better) if all chars of q appear in order in hay, else None."""
    qi = 0
    score = 0
    last = -1
    for i, ch in enumerate(hay):
        if qi < len(q) and ch == q[qi]:
            if last >= 0:
                score += (i - last)
            last = i
            qi += 1
            if qi == len(q):
                return score
    return None


def run_tui(agent):
    def _main(stdscr):
        TUI(agent, stdscr).loop()
    curses.wrapper(_main)
    return 0