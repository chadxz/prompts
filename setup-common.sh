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

ensure_mise_shims_on_zprofile() {
  local zprofile="$HOME/.zprofile"
  local tmp_zprofile

  mkdir -p "$(dirname "$zprofile")"
  touch "$zprofile"

  if grep -qF "# mise shims for Codex login shells" "$zprofile"; then
    tmp_zprofile="$(mktemp "${zprofile}.XXXXXX")"
    awk '
      $0 == "# mise shims for Codex login shells" {
        skip = 1
        next
      }
      skip && ($0 == "esac" || $0 == "unset -f _remove_path_entry") {
        skip = 0
        next
      }
      !skip {
        print
      }
    ' "$zprofile" > "$tmp_zprofile"
    mv "$tmp_zprofile" "$zprofile"
  fi

  {
    echo ""
    echo "# mise shims for Codex login shells"
    echo '_remove_path_entry() {'
    echo '  local entry="$1"'
    echo '  PATH=":$PATH:"'
    echo '  PATH="${PATH//:$entry:/:}"'
    echo '  PATH="${PATH#:}"'
    echo '  PATH="${PATH%:}"'
    echo '}'
    echo ""
    echo '_remove_path_entry "$HOME/.local/bin"'
    echo '_remove_path_entry "$HOME/.local/share/mise/shims"'
    echo 'export PATH="$HOME/.local/bin:$HOME/.local/share/mise/shims:$PATH"'
    echo 'unset -f _remove_path_entry'
  } >> "$zprofile"
  echo "Configured mise shims in ~/.zprofile"
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

setup_git_clone_override() {
  local bin_dir="$1"
  local wrapper="$bin_dir/git"
  local resolved_git

  if [[ ! -x "$wrapper" ]]; then
    echo "Error: git clone override is not executable: $wrapper" >&2
    return 1
  fi

  ensure_bin_on_path "$bin_dir"

  resolved_git="$(PATH="$bin_dir:$PATH" command -v git || true)"
  if [[ "$resolved_git" == "$wrapper" ]]; then
    echo "Configured git clone override -> $wrapper"
  else
    echo "Warning: git clone override is not first on PATH: $wrapper" >&2
    echo "Resolved git: ${resolved_git:-not found}" >&2
  fi
}
