#!/bin/bash
# Setup symlinks for pi configuration

set -euo pipefail

PROMPTS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PI_DIR="${PI_CODING_AGENT_DIR:-$HOME/.pi/agent}"

# shellcheck source=./setup-common.sh
source "$PROMPTS_DIR/setup-common.sh"

mkdir -p "$PI_DIR"

setup_global_gitignore "$PROMPTS_DIR/.gitignore_global"
setup_git_commit_template "$PROMPTS_DIR/.git_commit_template"
setup_git_clone_override "$PROMPTS_DIR/bin"
install_wt_stack "$PROMPTS_DIR"

for json_file in "$PROMPTS_DIR"/pi/*.json; do
    [[ -e "$json_file" ]] || continue
    link_path "$json_file" "$PI_DIR/$(basename "$json_file")"
done

link_path "$PROMPTS_DIR/AGENTS.md" "$PI_DIR/AGENTS.md"
link_path "$PROMPTS_DIR/pi/extensions" "$PI_DIR/extensions"
link_path "$PROMPTS_DIR/skills" "$PI_DIR/skills"

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
