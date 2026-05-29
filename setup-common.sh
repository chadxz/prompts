#!/usr/bin/env bash

set -euo pipefail

link_path() {
  local source="$1"
  local target="$2"

  mkdir -p "$(dirname "$target")"

  if [[ -L "$target" ]]; then
    rm "$target"
  elif [[ -e "$target" ]]; then
    echo "Error: $target exists and is not a symlink" >&2
    return 1
  fi

  ln -s "$source" "$target"
  echo "Symlinked $source -> $target"
}

link_path_if_present() {
  local source="$1"
  local target="$2"

  if [[ ! -e "$source" && ! -L "$source" ]]; then
    echo "Skipping missing source: $source"
    return 0
  fi

  link_path "$source" "$target"
}

ensure_bin_on_path() {
  local bin_dir="$1"
  local zshrc="$HOME/.zshrc"
  local bin_line="export PATH=\"$bin_dir:\$PATH\""

  if ! grep -qF "$bin_dir" "$zshrc" 2>/dev/null; then
    {
      echo ""
      echo "# prompts repo bin"
      echo "$bin_line"
    } >> "$zshrc"
    echo "Added $bin_dir to ~/.zshrc"
  else
    echo "$bin_dir already in PATH"
  fi
}

setup_global_gitignore() {
  local source="$1"
  local target="$HOME/.gitignore_global"
  local configured_path

  link_path "$source" "$target"

  configured_path="$(git config --global --get core.excludesfile || true)"
  if [[ "$configured_path" != "$target" ]]; then
    git config --global core.excludesfile "$target"
    echo "Configured git core.excludesfile -> $target"
  else
    echo "git core.excludesfile already points to $target"
  fi
}
