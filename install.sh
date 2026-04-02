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

# Add bin/ to PATH in .zshrc if not already present
BIN_LINE="export PATH=\"$SCRIPT_DIR/bin:\$PATH\""
if ! grep -qF "$SCRIPT_DIR/bin" "$HOME/.zshrc" 2>/dev/null; then
    echo "" >> "$HOME/.zshrc"
    echo "# prompts repo bin" >> "$HOME/.zshrc"
    echo "$BIN_LINE" >> "$HOME/.zshrc"
    echo "Added $SCRIPT_DIR/bin to PATH in ~/.zshrc"
else
    echo "$SCRIPT_DIR/bin already in PATH"
fi
