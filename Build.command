#!/bin/bash
set -e
cd "$(dirname "$0")"
export PATH="$PATH:/opt/homebrew/bin:/opt/homebrew/opt/rustup/bin:$HOME/.cargo/bin"
if ! command -v python3 >/dev/null 2>&1; then
    echo "Python 3 is required. Install it with Homebrew."
    exit 1
fi
exec python3 tools/build-celestia.py "$@"
