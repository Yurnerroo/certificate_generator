#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

VENV_DIR=".venv"
PYTHON="$VENV_DIR/bin/python"

if [ ! -x "$PYTHON" ]; then
    echo "Creating virtual environment..."
    python3 -m venv "$VENV_DIR"
fi

echo "Installing dependencies..."
"$PYTHON" -m pip install --quiet --upgrade pip
"$PYTHON" -m pip install --quiet -r requirements.txt

open_browser() {
    sleep 2
    URL="http://127.0.0.1:8000"
    if command -v open >/dev/null 2>&1; then
        open "$URL"
    elif command -v xdg-open >/dev/null 2>&1; then
        xdg-open "$URL"
    else
        echo "Please open $URL in your browser."
    fi
}

echo "Starting Certificate Generator at http://127.0.0.1:8000 ..."
open_browser &
exec "$PYTHON" -m uvicorn app.main:app --host 127.0.0.1 --port 8000
