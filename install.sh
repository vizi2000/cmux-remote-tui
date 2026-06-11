#!/usr/bin/env bash
#
# cmux-remote-tui installer (modern v0.2+).
#
# - Installs the package in editable mode using a WORKING Python (avoids Homebrew 3.14 pyexpat crash)
# - Copies the zero-dep agent to the remote host (Mac Mini etc.)
# - Installs the easy launcher script (recommended)
#
# Usage:
#   ./install.sh <ssh-host>
#
# Example:
#   ./install.sh macmini-ts
#   ./install.sh desk
#
set -euo pipefail

HOST="${1:-${CMUX_REMOTE_HOST:-}}"
if [[ -z "$HOST" ]]; then
  echo "usage: ./install.sh <ssh-host>" >&2
  exit 2
fi

SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# --- Find a working Python that can import the package (same logic as the easy launcher) ---
PYTHON=""
for cand in \
    python3 \
    python3.13 \
    python3.12 \
    /Library/Frameworks/Python.framework/Versions/3.13/bin/python3 \
    /opt/homebrew/bin/python3.13 \
    /opt/homebrew/bin/python3 ; do
    if command -v "$cand" >/dev/null 2>&1; then
        if "$cand" -c "import cmux_remote_tui.textual_app" 2>/dev/null; then
            PYTHON="$cand"
            break
        fi
    fi
done

if [ -z "$PYTHON" ]; then
    echo "ERROR: No Python found that has cmux-remote-tui installed."
    echo "Please run this first with a working Python (the one that can import textual):"
    echo "  cd \"$SELF_DIR\""
    echo "  pip install -e ."
    echo ""
    echo "Then re-run: ./install.sh $HOST"
    exit 1
fi

echo "==> Using Python: $PYTHON"
echo "==> Installing package in editable mode (so cmux-remote-tui always uses latest code)"
"$PYTHON" -m pip install -e "$SELF_DIR" --quiet

LOCAL_BIN="$HOME/.local/bin"

echo "==> Installing / updating agent on remote host: $HOST"
REMOTE_HOME=$(ssh "$HOST" 'echo "$HOME"' 2>/dev/null)
if [[ -z "$REMOTE_HOME" ]]; then
  echo "ERROR: Could not determine remote \$HOME on $HOST via ssh." >&2
  exit 1
fi
REMOTE_LIB="$REMOTE_HOME/.local/lib/cmux-remote-tui"

ssh "$HOST" "mkdir -p \"$REMOTE_LIB\""
scp -q "$SELF_DIR/cmux_remote_tui/agent.py" "$HOST:$REMOTE_LIB/agent.py"

echo "==> Installing easy launcher (recommended)"
mkdir -p "$LOCAL_BIN"
cp "$SELF_DIR/scripts/cmux-remote-tui" "$LOCAL_BIN/cmux-remote-tui"
chmod +x "$LOCAL_BIN/cmux-remote-tui"

# Keep the old name working for backward compat (now points to the new Textual + safe launcher)
ln -sf "$LOCAL_BIN/cmux-remote-tui" "$LOCAL_BIN/cmux-remote"

echo
echo "Done! The modern (Textual + LLM) version is now live."
echo
echo "  Run:   cmux-remote-tui"
echo "  or:    CMUX_REMOTE_HOST=$HOST cmux-remote-tui"
echo "  or:    cmux-remote-tui --host $HOST"
echo
echo "The launcher will auto-detect a good LLM provider (local claude/grok/codex preferred,"
echo "otherwise openai-compatible ready for llm.borg.tools etc.)."
echo
echo "Make sure ~/.local/bin is on your PATH."
echo "Run 'cmux-remote-tui --help' for usage and environment variables."
echo
echo "On the remote ($HOST): make sure cmux.app is running (open -a cmux)."
