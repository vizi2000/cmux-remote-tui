#!/usr/bin/env bash
#
# cmux-remote-tui installer.
#
# Installs the client locally and copies the lightweight agent to the remote
# host that runs cmux. The agent is plain Python 3 (stdlib only) and just shells
# out to the cmux CLI already installed on that host.
#
# Usage:
#   ./install.sh <ssh-host>
#
# Example:
#   ./install.sh my-mac          # an entry in your ~/.ssh/config
#   ./install.sh user@10.0.0.5
#
set -euo pipefail

HOST="${1:-${CMUX_REMOTE_HOST:-}}"
if [[ -z "$HOST" ]]; then
  echo "usage: ./install.sh <ssh-host>" >&2
  exit 2
fi

SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOCAL_LIB="$HOME/.local/lib/cmux-remote-tui"
LOCAL_BIN="$HOME/.local/bin"
REMOTE_LIB="\$HOME/.local/lib/cmux-remote-tui"

echo "==> Installing client locally into $LOCAL_LIB"
mkdir -p "$LOCAL_LIB" "$LOCAL_BIN"
cp "$SELF_DIR/cmux_remote_tui/client.py" "$LOCAL_LIB/client.py"
cp "$SELF_DIR/cmux_remote_tui/tui.py"    "$LOCAL_LIB/tui.py"
cp "$SELF_DIR/cmux_remote_tui/agent.py"  "$LOCAL_LIB/agent.py"
touch "$LOCAL_LIB/__init__.py"

cat > "$LOCAL_BIN/cmux-remote" <<EOF
#!/usr/bin/env python3
import os, sys
sys.path.insert(0, os.path.expanduser("~/.local/lib"))
from cmux_remote_tui_pkg.client import main  # type: ignore
raise SystemExit(main(sys.argv))
EOF
# simpler: load the lib dir directly so the package import works
cat > "$LOCAL_BIN/cmux-remote" <<EOF
#!/usr/bin/env python3
import os, sys
LIB = os.path.expanduser("$LOCAL_LIB")
sys.path.insert(0, os.path.dirname(LIB))
# allow "import cmux_remote_tui" by aliasing the lib dir as a package
import importlib.util, types
pkg = types.ModuleType("cmux_remote_tui")
pkg.__path__ = [LIB]
sys.modules["cmux_remote_tui"] = pkg
from cmux_remote_tui.client import main  # type: ignore
raise SystemExit(main(sys.argv))
EOF
chmod +x "$LOCAL_BIN/cmux-remote"

echo "==> Installing agent on remote host: $HOST"
ssh "$HOST" "mkdir -p $REMOTE_LIB"
scp -q "$SELF_DIR/cmux_remote_tui/agent.py" "$HOST:$REMOTE_LIB/agent.py"

echo
echo "Done."
echo "  Run:   CMUX_REMOTE_HOST=$HOST cmux-remote"
echo "  or:    cmux-remote --host $HOST"
echo
echo "Make sure ~/.local/bin is on your PATH."
