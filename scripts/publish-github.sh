#!/usr/bin/env bash
# One-shot GitHub publish for cmux-remote-tui.
# Spawned in its own cmux workspace so you can complete the interactive
# `gh auth login` (device code / browser) once; the rest is automated.
set -uo pipefail

REPO_DIR="$HOME/Projects/active/cmux-remote-tui"
REPO_NAME="cmux-remote-tui"
DESC="Fast, fluid TUI to control the cmux terminal on another machine over SSH — browse, fuzzy-find, preview and attach to remote terminals live."

cd "$REPO_DIR" || { echo "repo dir missing: $REPO_DIR"; exit 1; }

echo "============================================================"
echo " Publishing $REPO_NAME to GitHub"
echo "============================================================"
echo

# 1) Ensure gh is authenticated (interactive if needed)
if ! gh auth status >/dev/null 2>&1; then
  echo ">> GitHub CLI is not authenticated."
  echo ">> Starting 'gh auth login' — follow the prompts (choose HTTPS, login with browser/device code)."
  echo
  gh auth login || { echo "gh auth login failed/cancelled"; exit 1; }
fi
echo ">> Authenticated as: $(gh api user --jq .login 2>/dev/null || echo '?')"
echo

# 2) Create the repo (public) if it doesn't exist, set as origin, and push
if gh repo view "$REPO_NAME" >/dev/null 2>&1; then
  echo ">> Repo already exists on GitHub: $(gh repo view "$REPO_NAME" --json nameWithOwner --jq .nameWithOwner)"
  OWNER=$(gh api user --jq .login)
  git remote remove origin 2>/dev/null || true
  git remote add origin "https://github.com/$OWNER/$REPO_NAME.git"
  git branch -M main
  git push -u origin main
else
  echo ">> Creating public repo and pushing..."
  gh repo create "$REPO_NAME" --public --source=. --remote=origin \
     --description "$DESC" --push || { echo "repo create/push failed"; exit 1; }
fi
echo

OWNER=$(gh api user --jq .login)
URL="https://github.com/$OWNER/$REPO_NAME"

# 3) Topics + homepage metadata (discoverability)
echo ">> Setting topics and metadata..."
gh repo edit "$OWNER/$REPO_NAME" \
  --description "$DESC" \
  --homepage "https://github.com/manaflow-ai/cmux" \
  --add-topic cmux \
  --add-topic tui \
  --add-topic terminal \
  --add-topic ssh \
  --add-topic remote \
  --add-topic curses \
  --add-topic tmux \
  --add-topic coding-agents \
  --add-topic manaflow \
  --add-topic developer-tools \
  --add-topic python \
  --enable-issues --enable-wiki=false 2>/dev/null || true

echo
echo "============================================================"
echo " DONE."
echo " Repo:  $URL"
echo "============================================================"
echo
echo ">> Optional next steps to make it known:"
echo "   - Add a demo GIF/asciinema to the README (docs/demo.gif)."
echo "   - Open a 'Show & tell' / discussion link in the cmux repo:"
echo "       https://github.com/manaflow-ai/cmux"
echo "   - Submit to awesome-tuis: https://github.com/rothgar/awesome-tuis"
echo "   - Post on r/commandline and Hacker News (Show HN)."
echo
echo "__PUBLISH_DONE__ $URL"
