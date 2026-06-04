#!/usr/bin/env bash
# AEGIS CLI — Launch a battle against the remote server
# Usage: cd cli && ./run.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
VENV_DIR="$SCRIPT_DIR/venv"
REQUIREMENTS="$SCRIPT_DIR/requirements.txt"

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

# Run the engine from the project root
cd "$PROJECT_ROOT"
python -m engine.main \
  --url https://aegis-n8at.onrender.com \
  --competition mock-competition \
  --rounds 1 \
  "$@"
