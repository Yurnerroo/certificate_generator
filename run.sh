#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

VENV_DIR=".venv"
PYTHON="$VENV_DIR/bin/python"

if ! command -v python3 >/dev/null 2>&1; then
    echo "Python 3 was not found on this system."
    echo
    case "$(uname -s)" in
        Darwin)
            echo "Install it with Homebrew:  brew install python"
            echo "or download it from:       https://www.python.org/downloads/macos/"
            ;;
        Linux)
            echo "Install it with your package manager, e.g.:"
            echo "  sudo apt install python3 python3-venv   (Debian/Ubuntu)"
            echo "  sudo dnf install python3                (Fedora)"
            ;;
        *)
            echo "Download it from: https://www.python.org/downloads/"
            ;;
    esac
    echo
    echo "Then run this script again."
    exit 1
fi

if [ ! -x "$PYTHON" ]; then
    echo "Creating virtual environment..."
    python3 -m venv "$VENV_DIR"
fi

echo "Installing dependencies..."
"$PYTHON" -m pip install --quiet --upgrade pip
if ! "$PYTHON" -m pip install --quiet -r requirements.txt; then
    echo
    echo "Dependency installation failed. Re-running with full output so you can see why:"
    echo
    "$PYTHON" -m pip install -r requirements.txt
    echo
    echo "A common cause is no internet access, a blocked/very restrictive"
    echo "network, or missing build tools for a package with no pre-built wheel"
    echo "for your platform."
    echo "On Debian/Ubuntu try:  sudo apt install build-essential python3-dev"
    echo "On macOS try:          xcode-select --install"
    exit 1
fi

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
