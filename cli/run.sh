#!/usr/bin/env bash
# AEGIS CLI — Launch a battle
# Usage:
#   ./run.sh              (prod — uses https://aegis-n8at.onrender.com)
#   ./run.sh --local      (dev  — uses http://localhost:5001)

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
VENV_DIR="$SCRIPT_DIR/venv"
REQUIREMENTS="$SCRIPT_DIR/requirements.txt"

# Defaults (prod)
SERVER_URL="https://aegis-n8at.onrender.com"
COMPETITION="mock-competition"

# Check for --local flag
EXTRA_ARGS=()
for arg in "$@"; do
  if [ "$arg" = "--local" ]; then
    SERVER_URL="http://localhost:5001"
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

echo "Server: $SERVER_URL"

# Run the engine from the project root
cd "$PROJECT_ROOT"
python -m engine.main \
  --url "$SERVER_URL" \
  --competition "$COMPETITION" \
  --rounds 1 \
  "${EXTRA_ARGS[@]}"
