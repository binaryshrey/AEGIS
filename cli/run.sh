#!/usr/bin/env bash
# AEGIS CLI — Launch a battle
# Usage:
#   ./run.sh              (prod  — real competition: https://intern-battleship-game-server.vercel.app)
#   ./run.sh --local      (dev   — local mock server: http://localhost:5001)
#   ./run.sh --connect    (first run only — approve agent via device flow)
#   ./run.sh --rounds 5   (multiple attempts, self-improving)
#   ./run.sh --history    (print past score history and exit)
#
# Prod auth requires AGENT_AUTH_AGENT_ID and AGENT_AUTH_PRIVATE_KEY env vars.

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
VENV_DIR="$SCRIPT_DIR/venv"
REQUIREMENTS="$SCRIPT_DIR/requirements.txt"

# Translate --local → --mock for engine.play; pass everything else through
EXTRA_ARGS=()
for arg in "$@"; do
  if [ "$arg" = "--local" ]; then
    EXTRA_ARGS+=("--mock")
  else
    EXTRA_ARGS+=("$arg")
  fi
done

# Create virtual environment if it doesn't exist
if [ ! -d "$VENV_DIR" ]; then
  echo "Creating virtual environment..."
  python3 -m venv "$VENV_DIR"
fi

# Activate virtual environment
source "$VENV_DIR/bin/activate"

# Install dependencies if needed
if [ ! -f "$VENV_DIR/.installed" ]; then
  echo "Installing dependencies..."
  pip install --quiet --upgrade pip
  pip install --quiet -r "$REQUIREMENTS"
  touch "$VENV_DIR/.installed"
fi

# Run the prod entry point — handles real competition routing, auth, and retry
cd "$PROJECT_ROOT"
python -m engine.play "${EXTRA_ARGS[@]}"
