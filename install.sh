#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGET_DIR="$HOME/.cursor/commands"

if [[ -L "$TARGET_DIR" ]]; then
    echo "Removing existing symlink at $TARGET_DIR"
    rm "$TARGET_DIR"
elif [[ -e "$TARGET_DIR" ]]; then
    echo "Error: $TARGET_DIR exists and is not a symlink"
    exit 1
fi

mkdir -p "$(dirname "$TARGET_DIR")"
ln -s "$SCRIPT_DIR/cursor-commands" "$TARGET_DIR"
echo "Symlinked $SCRIPT_DIR/cursor-commands -> $TARGET_DIR"
