#!/bin/bash
# Setup symlinks for pi configuration

set -euo pipefail

PROMPTS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PI_DIR="${PI_CODING_AGENT_DIR:-$HOME/.pi/agent}"

link_path() {
    local source="$1"
    local target="$2"

    mkdir -p "$(dirname "$target")"

    if [[ -L "$target" ]]; then
        rm "$target"
    elif [[ -e "$target" ]]; then
        echo "Error: $target exists and is not a symlink"
        exit 1
    fi

    ln -s "$source" "$target"
    echo "Symlinked $source -> $target"
}

mkdir -p "$PI_DIR"

for json_file in "$PROMPTS_DIR"/pi/*.json; do
    [[ -e "$json_file" ]] || continue
    link_path "$json_file" "$PI_DIR/$(basename "$json_file")"
done

link_path "$PROMPTS_DIR/AGENTS.md" "$PI_DIR/AGENTS.md"
link_path "$PROMPTS_DIR/pi/extensions" "$PI_DIR/extensions"
link_path "$PROMPTS_DIR/skills" "$PI_DIR/skills"

# Add bin/ to PATH in .zshrc if not already present
BIN_LINE="export PATH=\"$PROMPTS_DIR/bin:\$PATH\""
if ! grep -qF "$PROMPTS_DIR/bin" "$HOME/.zshrc" 2>/dev/null; then
    echo "" >> "$HOME/.zshrc"
    echo "# prompts repo bin" >> "$HOME/.zshrc"
    echo "$BIN_LINE" >> "$HOME/.zshrc"
    echo "Added $PROMPTS_DIR/bin to ~/.zshrc"
else
    echo "$PROMPTS_DIR/bin already in PATH"
fi

echo "Symlinked pi JSON config, AGENTS.md, extensions, and skills."

for extension_dir in "$PROMPTS_DIR"/pi/extensions/*; do
    [[ -d "$extension_dir" ]] || continue
    [[ -f "$extension_dir/package.json" ]] || continue

    echo "Running npm install in $extension_dir"
    (
        cd "$extension_dir"
        npm install
    )
done
