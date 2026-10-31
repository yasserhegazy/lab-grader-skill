#!/usr/bin/env bash
# Install the lab-grader skill for Claude Code and/or OpenAI Codex.
#
#   ./install.sh            # install for every agent found (Claude Code, Codex)
#   ./install.sh --claude   # Claude Code only  -> ~/.claude/skills/lab-grader
#   ./install.sh --codex    # Codex only        -> ~/.codex/skills/lab-grader
#   ./install.sh --link     # symlink instead of copy (edits in this repo apply immediately)
set -euo pipefail

REPO="$(cd "$(dirname "$0")" && pwd)"
SRC="$REPO/skills/lab-grader"
want_claude=0; want_codex=0; link=0
for arg in "$@"; do
  case "$arg" in
    --claude) want_claude=1 ;;
    --codex)  want_codex=1 ;;
    --link)   link=1 ;;
    -h|--help) sed -n '2,8p' "$0"; exit 0 ;;
    *) echo "unknown option: $arg" >&2; exit 1 ;;
  esac
done
if [ $want_claude -eq 0 ] && [ $want_codex -eq 0 ]; then
  { command -v claude >/dev/null || [ -d "$HOME/.claude" ]; } && want_claude=1
  { command -v codex  >/dev/null || [ -d "$HOME/.codex" ];  } && want_codex=1
  if [ $want_claude -eq 0 ] && [ $want_codex -eq 0 ]; then
    echo "Neither Claude Code nor Codex found. Use --claude or --codex to force." >&2; exit 1
  fi
fi

install_to() {
  local dest="$1/lab-grader"
  mkdir -p "$1"
  if [ -e "$dest" ] || [ -L "$dest" ]; then
    mv "$dest" "$dest.bak.$(date +%Y%m%d%H%M%S)"
    echo "  (previous version backed up next to it)"
  fi
  if [ $link -eq 1 ]; then ln -s "$SRC" "$dest"; else cp -r "$SRC" "$dest"; fi
  echo "  installed -> $dest"
}

echo "Installing lab-grader skill"
[ $want_claude -eq 1 ] && install_to "$HOME/.claude/skills"
[ $want_codex  -eq 1 ] && install_to "${CODEX_HOME:-$HOME/.codex}/skills"

echo
echo "Checking dependencies"
command -v python3 >/dev/null || { echo "  ✗ python3 missing: install Python 3.9+"; exit 1; }
missing=""
python3 -c "import fitz" 2>/dev/null || missing="$missing PyMuPDF"
python3 -c "import PIL"  2>/dev/null || missing="$missing Pillow"
if [ -n "$missing" ]; then
  echo "  ✗ Python packages missing:$missing"
  echo "    install with:  python3 -m pip install --user -r $REPO/requirements.txt"
  echo "    (on Ubuntu 23.04+ add --break-system-packages, or use a venv / pipx)"
else
  echo "  ✓ PyMuPDF and Pillow"
fi
if command -v tesseract >/dev/null; then
  echo "  ✓ tesseract (free OCR of screenshots)"
else
  echo "  ! tesseract not found. Optional but strongly recommended (saves most of the cost):"
  echo "      Ubuntu/Debian: sudo apt install -y tesseract-ocr"
  echo "      macOS:         brew install tesseract"
fi
echo
echo "Done. Restart Claude Code / Codex, then in your assignment folder ask:"
echo '  "grade the submissions in this folder"'
