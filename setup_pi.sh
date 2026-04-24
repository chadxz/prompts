#!/bin/bash
# Setup symlinks for pi configuration

set -euo pipefail

PROMPTS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PI_DIR="${PI_CODING_AGENT_DIR:-$HOME/.pi/agent}"

# shellcheck source=./setup-common.sh
source "$PROMPTS_DIR/setup-common.sh"

mkdir -p "$PI_DIR"

for json_file in "$PROMPTS_DIR"/pi/*.json; do
    [[ -e "$json_file" ]] || continue
    link_path "$json_file" "$PI_DIR/$(basename "$json_file")"
done

link_path "$PROMPTS_DIR/AGENTS.md" "$PI_DIR/AGENTS.md"
link_path "$PROMPTS_DIR/pi/extensions" "$PI_DIR/extensions"
link_path "$PROMPTS_DIR/skills" "$PI_DIR/skills"

ensure_bin_on_path "$PROMPTS_DIR/bin"

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
