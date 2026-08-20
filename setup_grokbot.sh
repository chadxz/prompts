#!/bin/bash
# Setup Grok Bot: shared git/tooling hooks, Tailscale on boot, plus a
# fuse-overlayfs union of prompts/skills over the Grok Bot workflows catalog.
#
# Grok Bot's catalog only treats real directories as skills (directory
# symlinks are ignored). fuse-overlayfs presents both the prompts skill
# packages and Grok-native packages as real directories in workflows/.
#
# Usage:
#   ./setup_grokbot.sh                 # shared hooks + Tailscale + overlay
#   ./setup_grokbot.sh --overlay-only  # remount the overlay only
#
# Overlay paths can be overridden with GROK_BOT_DATA_DIR (the directory
# that contains workflows/). The mount and Tailscale start need
# passwordless sudo.

set -euo pipefail

PROMPTS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FUSE_OVERLAYFS_VERSION="1.17"
FUSE_OVERLAYFS_RELEASE="v${FUSE_OVERLAYFS_VERSION}"

# shellcheck source=./setup-common.sh
source "$PROMPTS_DIR/setup-common.sh"

OVERLAY_ONLY=0
for arg in "$@"; do
  case "$arg" in
    --overlay-only)
      OVERLAY_ONLY=1
      ;;
    -h | --help)
      sed -n '2,16p' "$0"
      exit 0
      ;;
    *)
      echo "Error: unknown argument: $arg" >&2
      exit 1
      ;;
  esac
done

resolve_grok_data_dir() {
  if [[ -n "${GROK_BOT_DATA_DIR:-}" ]]; then
    printf '%s\n' "$GROK_BOT_DATA_DIR"
    return 0
  fi
  if [[ -d "$HOME/agent-data" ]]; then
    printf '%s\n' "$HOME/agent-data"
    return 0
  fi
  if [[ -d "$HOME/sand-data" ]]; then
    printf '%s\n' "$HOME/sand-data"
    return 0
  fi
  return 1
}

canonical_dir() {
  (cd "$1" && pwd -P)
}

package_has_regular_files() {
  local package_dir="$1"
  local found

  found="$(find "$package_dir" -type f -print -quit 2>/dev/null || true)"
  [[ -n "$found" ]]
}

install_fuse_overlayfs() {
  local dest="$HOME/.local/bin/fuse-overlayfs"
  local arch url tmp
  local current=""

  mkdir -p "$(dirname "$dest")"
  ensure_bin_on_path "$(dirname "$dest")" >/dev/null

  if [[ -x "$dest" ]]; then
    current="$("$dest" -V 2>&1 | awk '/^fuse-overlayfs: version/{print $3; exit}')"
    if [[ "$current" == "$FUSE_OVERLAYFS_VERSION" ]]; then
      echo "fuse-overlayfs $FUSE_OVERLAYFS_VERSION already installed" >&2
      printf '%s\n' "$dest"
      return 0
    fi
  fi

  arch="$(uname -m)"
  url="https://github.com/containers/fuse-overlayfs/releases/download/${FUSE_OVERLAYFS_RELEASE}/fuse-overlayfs-${arch}"
  tmp="$(mktemp)"
  echo "Downloading fuse-overlayfs $FUSE_OVERLAYFS_VERSION ($arch)" >&2
  curl -fsSL "$url" -o "$tmp"
  chmod +x "$tmp"
  if ! "$tmp" -V 2>&1 | grep -q "fuse-overlayfs: version ${FUSE_OVERLAYFS_VERSION}"; then
    rm -f "$tmp"
    echo "Error: downloaded fuse-overlayfs did not report version $FUSE_OVERLAYFS_VERSION" >&2
    return 1
  fi
  mv "$tmp" "$dest"
  echo "Installed fuse-overlayfs $FUSE_OVERLAYFS_VERSION -> $dest" >&2
  printf '%s\n' "$dest"
}

overlay_is_mounted() {
  local workflows="$1"
  local lower="$2"
  local upper="$3"
  local fstype opts

  fstype="$(findmnt -n -o FSTYPE --target "$workflows" 2>/dev/null || true)"
  opts="$(findmnt -n -o OPTIONS --target "$workflows" 2>/dev/null || true)"
  [[ "$fstype" == fuse.fuse-overlayfs ]] || return 1
  [[ "$opts" == *"lowerdir=${lower}"* ]] || return 1
  [[ "$opts" == *"upperdir=${upper}"* ]] || return 1
}

unmount_overlay_if_present() {
  local workflows="$1"
  local fstype

  fstype="$(findmnt -n -o FSTYPE --target "$workflows" 2>/dev/null || true)"
  if [[ "$fstype" == fuse.fuse-overlayfs ]]; then
    sudo -n umount "$workflows"
    echo "Unmounted existing fuse-overlayfs at $workflows"
  fi
}

migrate_local_workflow_files() {
  local workflows="$1"
  local upper="$2"
  local package_dir package_name rel dest

  shopt -s nullglob
  for package_dir in "$workflows"/*/; do
    package_name="$(basename "$package_dir")"
    if ! package_has_regular_files "$package_dir"; then
      continue
    fi
    echo "Preserving Grok-native files from $package_name in upperdir"
    while IFS= read -r -d '' rel; do
      dest="$upper/$package_name/$rel"
      mkdir -p "$(dirname "$dest")"
      cp -a "$package_dir/$rel" "$dest"
    done < <(find "$package_dir" -type f -printf '%P\0')
  done
}

clear_mountpoint() {
  local workflows="$1"

  find "$workflows" -mindepth 1 -maxdepth 1 -exec rm -rf {} +
}

prepare_work_dir() {
  local work="$1"

  mkdir -p "$work"
  find "$work" -mindepth 1 -maxdepth 1 -exec rm -rf {} +
}

verify_overlay() {
  local workflows="$1"
  local skill_md

  skill_md="$(find "$workflows" -mindepth 2 -maxdepth 2 -name SKILL.md -print -quit)"
  if [[ -z "$skill_md" ]]; then
    echo "Error: overlay mounted at $workflows but no SKILL.md packages are visible" >&2
    return 1
  fi
  echo "Verified overlay catalogs $(find "$workflows" -mindepth 2 -maxdepth 2 -name SKILL.md | wc -l) skill packages"
}

mount_skills_overlay() {
  local grok_data lower workflows upper work fuse_bin

  if [[ "$(uname -s)" != Linux ]]; then
    echo "Skipping Grok Bot skills overlay (Linux-only)"
    return 0
  fi

  if ! grok_data="$(resolve_grok_data_dir)"; then
    echo "Skipping Grok Bot skills overlay (no agent-data/sand-data directory)"
    return 0
  fi

  grok_data="$(canonical_dir "$grok_data")"
  lower="$(canonical_dir "$PROMPTS_DIR/skills")"
  workflows="$grok_data/workflows"
  upper="$grok_data/workflows-upper"
  work="$grok_data/workflows-work"

  mkdir -p "$workflows" "$upper" "$work"

  if overlay_is_mounted "$workflows" "$lower" "$upper"; then
    echo "Grok Bot skills overlay already mounted at $workflows"
    verify_overlay "$workflows"
    return 0
  fi

  if ! sudo -n true >/dev/null 2>&1; then
    echo "Error: passwordless sudo is required to mount the Grok Bot overlay" >&2
    return 1
  fi

  fuse_bin="$(install_fuse_overlayfs)"

  unmount_overlay_if_present "$workflows"
  migrate_local_workflow_files "$workflows" "$upper"
  clear_mountpoint "$workflows"
  prepare_work_dir "$work"

  sudo -n "$fuse_bin" \
    -o "lowerdir=${lower},upperdir=${upper},workdir=${work}" \
    "$workflows"
  echo "Mounted Grok Bot skills overlay at $workflows"
  echo "  lower: $lower"
  echo "  upper: $upper"
  verify_overlay "$workflows"
}

install_tailscale() {
  if [[ "$(uname -s)" != Linux ]]; then
    echo "Skipping Tailscale install (Linux-only)"
    return 0
  fi

  if command -v tailscale >/dev/null 2>&1 && command -v tailscaled >/dev/null 2>&1; then
    echo "tailscale already installed ($(tailscale version --short 2>/dev/null || tailscale version | awk 'NR==1{print; exit}'))"
    return 0
  fi

  if ! sudo -n true >/dev/null 2>&1; then
    echo "Error: passwordless sudo is required to install Tailscale" >&2
    return 1
  fi

  echo "Installing Tailscale"
  curl -fsSL https://tailscale.com/install.sh | sudo -n sh
}

ensure_tailscale_session_hook() {
  local bashrc="$HOME/.bashrc"
  local mark="# Tailscale: PID 1 is tini/pod-daemon"

  mkdir -p "$(dirname "$bashrc")"
  touch "$bashrc"
  if grep -qF "$mark" "$bashrc"; then
    echo "Tailscale session hook already in ~/.bashrc"
    return 0
  fi

  {
    echo ""
    echo "$mark (not systemd), so start tailscaled if needed."
    echo "if command -v start-grokbot-tailscaled >/dev/null 2>&1; then"
    echo "    start-grokbot-tailscaled >/dev/null 2>&1 || true"
    echo "fi"
  } >> "$bashrc"
  echo "Added Tailscale session hook to ~/.bashrc"
}

setup_grokbot_tailscale() {
  local dest="$HOME/.local/bin/start-grokbot-tailscaled"

  if [[ "$(uname -s)" != Linux ]]; then
    echo "Skipping Grok Bot Tailscale setup (Linux-only)"
    return 0
  fi

  install_tailscale
  mkdir -p "$(dirname "$dest")"
  ensure_bin_on_path "$(dirname "$dest")" >/dev/null
  # Copy so boot still works if this checkout moves.
  install -m 0755 "$PROMPTS_DIR/bin/start-grokbot-tailscaled" "$dest"
  echo "Installed $dest"
  ensure_tailscale_session_hook
  "$dest"
  if command -v tailscale >/dev/null 2>&1; then
    echo "Tailscale status:"
    tailscale status --self 2>/dev/null || tailscale status || true
  fi
}

if [[ "$OVERLAY_ONLY" -eq 0 ]]; then
  setup_global_gitignore "$PROMPTS_DIR/.gitignore_global"
  setup_git_commit_template "$PROMPTS_DIR/.git_commit_template"
  setup_git_clone_override "$PROMPTS_DIR/bin"
  install_wt_stack "$PROMPTS_DIR"
  setup_grokbot_tailscale
fi

mount_skills_overlay
