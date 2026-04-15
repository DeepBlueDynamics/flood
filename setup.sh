#!/usr/bin/env bash
# setup.sh — Mac / Linux first-run setup for Veo Studio
set -euo pipefail

echo ""
echo "==> Veo Studio — Setup"
echo ""

# ── 1. ffmpeg ───────────────────────────────────────────────────────────────
if command -v ffmpeg &>/dev/null; then
    echo "✓ ffmpeg found: $(ffmpeg -version 2>&1 | head -1)"
else
    if command -v brew &>/dev/null; then
        echo "Installing ffmpeg via Homebrew..."
        brew install ffmpeg
    else
        echo "✗ ffmpeg not found and Homebrew not available."
        echo "  Install ffmpeg manually: https://ffmpeg.org/download.html"
        echo "  Or install Homebrew first: https://brew.sh"
        exit 1
    fi
fi

# ── 2. Python version check ─────────────────────────────────────────────────
PYTHON=$(command -v python3.11 || command -v python3.12 || command -v python3 || true)
if [ -z "$PYTHON" ]; then
    echo "✗ Python 3.11+ not found. Install via: brew install python@3.11"
    exit 1
fi

PY_VERSION=$("$PYTHON" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
echo "✓ Python $PY_VERSION at $PYTHON"

# ── 3. Virtual environment ───────────────────────────────────────────────────
if [ ! -d ".venv" ]; then
    echo "Creating virtual environment..."
    "$PYTHON" -m venv .venv
fi

# shellcheck disable=SC1091
source .venv/bin/activate
echo "✓ Virtual environment active"

# ── 4. Python dependencies ───────────────────────────────────────────────────
echo "Installing Python dependencies..."
pip install --quiet --upgrade pip
pip install --quiet -r requirements.txt
echo "✓ Dependencies installed"

# ── 5. .env file ─────────────────────────────────────────────────────────────
if [ ! -f ".env" ]; then
    cp .env.example .env
    echo ""
    echo "⚠  Created .env from .env.example"
    echo "   Open .env and set GOOGLE_API_KEY before running."
else
    echo "✓ .env already exists"
fi

# ── 6. Output directories ─────────────────────────────────────────────────────
mkdir -p output/jobs
echo "✓ output/ directory ready"

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Setup complete!"
echo ""
echo "  To start the web UI:"
echo "    source .venv/bin/activate"
echo "    python run.py"
echo "    open http://localhost:8080"
echo ""
echo "  CLI usage:"
echo "    python veo_agent.py \"A scene...\" output/clip.mp4"
echo "    python veo_agent.py loop \"A scene...\" output/loop.mp4"
echo "    python veo_agent.py chain \"A scene...\" 4 output/long.mp4"
echo "    python extend_video.py source.mp4 \"next...\" -o output/extended.mp4"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
