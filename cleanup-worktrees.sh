#!/usr/bin/env bash

set -uo pipefail

root_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

dry_run=0
interactive=0
fetch_remotes=1

usage() {
    printf 'Usage: %s [--dry-run] [--interactive] [--no-fetch]\n' \
        "$(basename "$0")"
    printf '\n'
    printf 'Scans repo containers under %s (bare .git with worktrees\n' \
        "${root_dir}"
    printf 'directly under each repo) and removes clean task worktrees when either:\n'
    printf '  - the current branch has a merged GitHub pull request, or\n'
    printf '  - the worktree HEAD is already contained in origin/<default-branch>.\n'
    printf '\n'
    printf 'Options:\n'
    printf '  --dry-run       Report what would be removed without deleting anything.\n'
    printf '  --interactive   After cleanup, choose remaining worktrees to delete.\n'
    printf '  --no-fetch      Skip git fetch before checking remote branch state.\n'
    printf '  -h, --help      Show this help.\n'
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --dry-run)
            dry_run=1
            ;;
        --interactive)
            interactive=1
            ;;
        --no-fetch)
            fetch_remotes=0
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            printf 'Unknown option: %s\n\n' "$1" >&2
            usage >&2
            exit 1
            ;;
    esac
    shift
done

declare -a remaining_paths=()
declare -a remaining_repo_paths=()
declare -a remaining_repos=()
declare -a remaining_names=()
declare -a selected_indices=()

deleted_count=0
kept_count=0
skipped_count=0
fetched_repos='|'
fetch_failed_repos='|'

have_gh=0
if command -v gh >/dev/null 2>&1; then
    have_gh=1
fi

epoch_for_path() {
    local path="$1"
    local value=""

    if value="$(stat -f '%B' "$path" 2>/dev/null)" &&
        [[ "$value" =~ ^[0-9]+$ ]] &&
        [[ "$value" -gt 0 ]]; then
        printf '%s\n' "$value"
        return
    fi

    if value="$(stat -c '%W' "$path" 2>/dev/null)" &&
        [[ "$value" =~ ^[0-9]+$ ]] &&
        [[ "$value" -gt 0 ]]; then
        printf '%s\n' "$value"
        return
    fi

    if value="$(stat -f '%m' "$path" 2>/dev/null)" &&
        [[ "$value" =~ ^[0-9]+$ ]] &&
        [[ "$value" -gt 0 ]]; then
        printf '%s\n' "$value"
        return
    fi

    if value="$(stat -c '%Y' "$path" 2>/dev/null)" &&
        [[ "$value" =~ ^[0-9]+$ ]] &&
        [[ "$value" -gt 0 ]]; then
        printf '%s\n' "$value"
    fi
}

date_for_epoch() {
    local epoch="$1"

    date -r "$epoch" '+%Y-%m-%d' 2>/dev/null ||
        date -d "@${epoch}" '+%Y-%m-%d' 2>/dev/null ||
        printf 'unknown'
}

age_for_path() {
    local path="$1"
    local created_at
    local now
    local delta
    local days
    local hours
    local minutes
    local label
    local created_date

    created_at="$(epoch_for_path "$path")"
    if [[ -z "$created_at" ]]; then
        printf 'unknown'
        return
    fi

    now="$(date '+%s')"
    delta=$((now - created_at))
    if [[ "$delta" -lt 0 ]]; then
        delta=0
    fi

    days=$((delta / 86400))
    hours=$((delta / 3600))
    minutes=$((delta / 60))

    if [[ "$days" -ge 365 ]]; then
        label="$((days / 365))y"
    elif [[ "$days" -ge 1 ]]; then
        label="${days}d"
    elif [[ "$hours" -ge 1 ]]; then
        label="${hours}h"
    elif [[ "$minutes" -ge 1 ]]; then
        label="${minutes}m"
    else
        label='0m'
    fi

    created_date="$(date_for_epoch "$created_at")"
    printf '%s, created %s' "$label" "$created_date"
}

list_task_worktrees() {
    local repo_path="$1"
    local line
    local worktree_path=""
    local is_bare=0

    # Repos use the bare container layout: a bare repository at
    # <repo>/.git with worktrees directly under <repo>/. The `main`
    # worktree holds the default branch and is never a cleanup target.
    while IFS= read -r line; do
        if [[ "$line" == worktree\ * ]]; then
            worktree_path="${line#worktree }"
            is_bare=0
        elif [[ "$line" == 'bare' ]]; then
            is_bare=1
        elif [[ -z "$line" ]]; then
            if [[ -n "$worktree_path" &&
                "$is_bare" -eq 0 &&
                "$(basename "$worktree_path")" != 'main' ]]; then
                printf '%s\n' "$worktree_path"
            fi
            worktree_path=""
            is_bare=0
        fi
    done < <(
        git -C "$repo_path" worktree list --porcelain 2>/dev/null
        printf '\n'
    )
}

is_clean_worktree() {
    local worktree_path="$1"
    [[ -z "$(git -C "$worktree_path" status --porcelain 2>/dev/null)" ]]
}

current_branch() {
    local worktree_path="$1"

    git -C "$worktree_path" symbolic-ref --quiet --short HEAD 2>/dev/null ||
        printf 'detached'
}

default_branch_for_repo() {
    local repo_path="$1"
    local default_ref

    default_ref="$(git -C "$repo_path" symbolic-ref --quiet --short \
        refs/remotes/origin/HEAD 2>/dev/null || true)"
    if [[ -n "$default_ref" ]]; then
        printf '%s\n' "${default_ref#origin/}"
        return
    fi

    if git -C "$repo_path" rev-parse --verify -q origin/main >/dev/null 2>&1; then
        printf 'main\n'
        return
    fi

    if git -C "$repo_path" rev-parse --verify -q origin/master >/dev/null 2>&1; then
        printf 'master\n'
    fi
}

remote_slug_for_repo() {
    local repo_path="$1"
    local url
    local slug

    url="$(git -C "$repo_path" remote get-url origin 2>/dev/null || true)"
    if [[ "$url" != *github.com* ]]; then
        return 1
    fi

    slug="$(printf '%s' "$url" |
        sed -E \
            -e 's#^(https?://([^/@]+@)?github\.com/|git@github\.com:|ssh://git@github\.com/|git://github\.com/)##' \
            -e 's#\.git$##')"

    if [[ "$slug" == */* ]]; then
        printf '%s\n' "$slug"
    else
        return 1
    fi
}

fetch_repo_once() {
    local repo_path="$1"
    local repo_name="$2"
    local repo_key="|${repo_path}|"

    if [[ "$fetch_remotes" -eq 0 ]]; then
        return 0
    fi

    if [[ "$fetched_repos" == *"$repo_key"* ]]; then
        [[ "$fetch_failed_repos" != *"$repo_key"* ]]
        return
    fi

    fetched_repos="${fetched_repos}${repo_path}|"

    if git -C "$repo_path" fetch origin --prune >/dev/null 2>&1; then
        return 0
    fi

    fetch_failed_repos="${fetch_failed_repos}${repo_path}|"
    printf 'WARN  %s: git fetch origin --prune failed; using local refs only\n' \
        "$repo_name" >&2
    return 1
}

merged_pr_for_branch() {
    local repo_path="$1"
    local branch="$2"
    local slug
    local pr_summary

    if [[ "$have_gh" -ne 1 || "$branch" == 'detached' ]]; then
        return 1
    fi

    slug="$(remote_slug_for_repo "$repo_path" || true)"
    if [[ -z "$slug" ]]; then
        return 1
    fi

    pr_summary="$(gh -R "$slug" pr list \
        --head "$branch" \
        --state all \
        --limit 20 \
        --json number,state,mergedAt,url,baseRefName \
        --jq 'map(select(.state == "MERGED" or ((.mergedAt // "") != ""))) | last | if . then "PR #\(.number) merged into \(.baseRefName): \(.url)" else "" end' \
        2>/dev/null || true)"

    if [[ -n "$pr_summary" ]]; then
        printf '%s\n' "$pr_summary"
        return 0
    fi

    return 1
}

head_is_in_default_branch() {
    local repo_path="$1"
    local worktree_path="$2"
    local default_branch="$3"
    local head_sha

    if [[ -z "$default_branch" ]]; then
        return 1
    fi

    if ! git -C "$repo_path" rev-parse --verify -q \
        "origin/${default_branch}" >/dev/null 2>&1; then
        return 1
    fi

    head_sha="$(git -C "$worktree_path" rev-parse HEAD 2>/dev/null || true)"
    if [[ -z "$head_sha" ]]; then
        return 1
    fi

    git -C "$repo_path" merge-base --is-ancestor \
        "$head_sha" "origin/${default_branch}" 2>/dev/null
}

remove_worktree() {
    local repo_path="$1"
    local worktree_path="$2"
    local reason="$3"
    local remove_output
    local force_output

    if [[ "$dry_run" -eq 1 ]]; then
        printf 'DRY   would remove %s\n' "$worktree_path"
        printf '      %s\n' "$reason"
        return 0
    fi

    printf 'DEL   removing %s\n' "$worktree_path"
    printf '      %s\n' "$reason"

    if remove_output="$(git -C "$repo_path" worktree remove \
        "$worktree_path" 2>&1)"; then
        return 0
    fi

    if [[ "$remove_output" == *'locked working tree'* ]]; then
        printf '      locked; retrying with --force --force\n'
        if force_output="$(git -C "$repo_path" worktree remove \
            --force --force "$worktree_path" 2>&1)"; then
            return 0
        fi

        printf 'WARN  failed to force remove locked worktree %s\n' \
            "$worktree_path" >&2
        while IFS= read -r line; do
            printf '      %s\n' "$line" >&2
        done <<< "$force_output"
        return 1
    fi

    printf 'WARN  failed to remove %s\n' "$worktree_path" >&2
    while IFS= read -r line; do
        printf '      %s\n' "$line" >&2
    done <<< "$remove_output"
    return 1
}

scan_worktree() {
    local repo_path="$1"
    local repo_name="$2"
    local worktree_path="$3"
    local worktree_name
    local branch
    local default_branch
    local clean=0
    local reason=""
    local merged_pr=""
    local eligible=0

    worktree_name="$(basename "$worktree_path")"

    if [[ ! -d "$worktree_path" ]] ||
        ! git -C "$worktree_path" rev-parse --is-inside-work-tree \
            >/dev/null 2>&1; then
        printf 'KEEP  %s/%s: not a usable git worktree\n' \
            "$repo_name" "$worktree_name"
        skipped_count=$((skipped_count + 1))
        return
    fi

    printf 'SCAN  %s/%s\n' "$repo_name" "$worktree_name"

    fetch_repo_once "$repo_path" "$repo_name" || true

    branch="$(current_branch "$worktree_path")"
    default_branch="$(default_branch_for_repo "$repo_path")"

    if is_clean_worktree "$worktree_path"; then
        clean=1
    fi

    merged_pr="$(merged_pr_for_branch "$repo_path" "$branch" || true)"
    if [[ -n "$merged_pr" ]]; then
        eligible=1
        reason="$merged_pr"
    elif head_is_in_default_branch "$repo_path" "$worktree_path" "$default_branch"; then
        eligible=1
        reason="HEAD is already contained in origin/${default_branch}"
    fi

    if [[ "$eligible" -eq 1 && "$clean" -eq 1 ]]; then
        if remove_worktree "$repo_path" "$worktree_path" "$reason"; then
            deleted_count=$((deleted_count + 1))
        else
            skipped_count=$((skipped_count + 1))
        fi
    elif [[ "$eligible" -eq 1 ]]; then
        printf 'KEEP  %s/%s: eligible, but has local changes\n' \
            "$repo_name" "$worktree_name"
        kept_count=$((kept_count + 1))
    else
        printf 'KEEP  %s/%s: no merged PR and not contained in origin/%s\n' \
            "$repo_name" "$worktree_name" "${default_branch:-unknown}"
        kept_count=$((kept_count + 1))
    fi
}

scan_and_cleanup() {
    local repo_path
    local repo_name
    local worktree_path

    shopt -s nullglob
    for repo_path in "${root_dir}"/*/; do
        repo_path="${repo_path%/}"
        [[ -d "${repo_path}/.git" ]] || continue
        repo_name="$(basename "$repo_path")"

        while IFS= read -r worktree_path; do
            scan_worktree "$repo_path" "$repo_name" "$worktree_path"
        done < <(list_task_worktrees "$repo_path")
    done
    shopt -u nullglob
}

load_remaining_worktrees() {
    local worktree_path
    local repo_path

    remaining_paths=()
    remaining_repo_paths=()
    remaining_repos=()
    remaining_names=()

    shopt -s nullglob
    for repo_path in "${root_dir}"/*/; do
        repo_path="${repo_path%/}"
        [[ -d "${repo_path}/.git" ]] || continue

        while IFS= read -r worktree_path; do
            remaining_paths+=("$worktree_path")
            remaining_repo_paths+=("$repo_path")
            remaining_repos+=("$(basename "$repo_path")")
            remaining_names+=("$(basename "$worktree_path")")
        done < <(list_task_worktrees "$repo_path")
    done
    shopt -u nullglob
}

print_worktree_status() {
    local worktree_path="$1"
    local status_output

    if ! git -C "$worktree_path" rev-parse --is-inside-work-tree \
        >/dev/null 2>&1; then
        printf '    git status: not a git worktree\n'
        return
    fi

    status_output="$(git -C "$worktree_path" status --short --branch 2>&1)"
    while IFS= read -r line; do
        printf '    %s\n' "$line"
    done <<< "$status_output"
}

print_remaining_worktrees() {
    local title="$1"
    local i
    local worktree_path
    local age

    printf '\n%s\n' "$title"

    if [[ "${#remaining_paths[@]}" -eq 0 ]]; then
        printf '  None.\n'
        return
    fi

    for ((i = 0; i < ${#remaining_paths[@]}; i++)); do
        worktree_path="${remaining_paths[$i]}"
        age="$(age_for_path "$worktree_path")"

        printf '[%d] %s/%s\n' \
            "$((i + 1))" "${remaining_repos[$i]}" "${remaining_names[$i]}"
        printf '    path: %s\n' "$worktree_path"
        printf '    age: %s\n' "$age"
        print_worktree_status "$worktree_path"
    done
}

add_selected_index() {
    local index="$1"
    local existing

    if [[ "$index" -lt 1 || "$index" -gt "${#remaining_paths[@]}" ]]; then
        printf 'WARN  ignoring out-of-range selection: %s\n' "$index" >&2
        return
    fi

    for existing in "${selected_indices[@]}"; do
        if [[ "$existing" -eq "$index" ]]; then
            return
        fi
    done

    selected_indices+=("$index")
}

parse_numeric_selection() {
    local input="$1"
    local token
    local start
    local end
    local i

    selected_indices=()
    input="${input//,/ }"
    input="${input//;/ }"

    for token in $input; do
        if [[ "$token" =~ ^([0-9]+)-([0-9]+)$ ]]; then
            start="${BASH_REMATCH[1]}"
            end="${BASH_REMATCH[2]}"
            if [[ "$start" -le "$end" ]]; then
                for ((i = start; i <= end; i++)); do
                    add_selected_index "$i"
                done
            else
                for ((i = start; i >= end; i--)); do
                    add_selected_index "$i"
                done
            fi
        elif [[ "$token" =~ ^[0-9]+$ ]]; then
            add_selected_index "$token"
        else
            printf 'WARN  ignoring selection token: %s\n' "$token" >&2
        fi
    done
}

select_with_fzf() {
    local choices
    local selected
    local line
    local index
    local i

    if ! command -v fzf >/dev/null 2>&1 || [[ ! -t 1 ]]; then
        return 1
    fi

    choices="$(
        for ((i = 0; i < ${#remaining_paths[@]}; i++)); do
            printf '%d\t%s/%s\t%s\n' \
                "$((i + 1))" \
                "${remaining_repos[$i]}" \
                "${remaining_names[$i]}" \
                "${remaining_paths[$i]}"
        done
    )"

    selected="$(printf '%s\n' "$choices" |
        fzf --multi --prompt='Delete worktrees > ' --height=40% --border)"

    selected_indices=()
    while IFS=$'\t' read -r index _; do
        [[ -n "$index" ]] || continue
        add_selected_index "$index"
    done <<< "$selected"

    [[ "${#selected_indices[@]}" -gt 0 ]]
}

select_interactively() {
    local input

    if select_with_fzf; then
        return 0
    fi

    printf '\nEnter worktree numbers to delete '
    printf '(example: 1 3 5-7), or press Enter to keep all: '
    read -r input

    if [[ -z "$input" ]]; then
        selected_indices=()
        return 0
    fi

    parse_numeric_selection "$input"
}

remove_interactive_selection() {
    local index
    local array_index
    local worktree_path
    local repo_path
    local repo_name
    local answer
    local remove_output
    local force_output

    if [[ "${#selected_indices[@]}" -eq 0 ]]; then
        printf '\nNo interactive deletions selected.\n'
        return
    fi

    printf '\nInteractive deletions\n'

    for index in "${selected_indices[@]}"; do
        array_index=$((index - 1))
        worktree_path="${remaining_paths[$array_index]}"
        repo_path="${remaining_repo_paths[$array_index]}"
        repo_name="${remaining_repos[$array_index]}"

        printf 'DEL   removing %s\n' "$worktree_path"

        if [[ "$dry_run" -eq 1 ]]; then
            printf '      dry run; not deleted\n'
            continue
        fi

        if remove_output="$(git -C "$repo_path" worktree remove \
            "$worktree_path" 2>&1)"; then
            continue
        fi

        printf 'WARN  normal removal failed for %s\n' "$worktree_path" >&2
        while IFS= read -r line; do
            printf '      %s\n' "$line" >&2
        done <<< "$remove_output"
        printf '      Force remove %s/%s and discard local changes or locks? [y/N] ' \
            "$repo_name" "$(basename "$worktree_path")"
        read -r answer

        if [[ "$answer" =~ ^[Yy]$ ]]; then
            force_output="$(git -C "$repo_path" worktree remove \
                --force --force "$worktree_path" 2>&1)" ||
                printf 'WARN  force removal failed for %s\n' "$worktree_path" >&2
            if [[ -n "${force_output:-}" ]]; then
                while IFS= read -r line; do
                    printf '      %s\n' "$line" >&2
                done <<< "$force_output"
            fi
        else
            printf 'KEEP  %s\n' "$worktree_path"
        fi
    done
}

if [[ "$dry_run" -eq 1 ]]; then
    printf 'Scanning worktrees under %s (dry run)\n' "$root_dir"
else
    printf 'Scanning worktrees under %s\n' "$root_dir"
fi

if [[ "$have_gh" -ne 1 ]]; then
    printf 'WARN  gh not found; merged PR checks will be skipped\n' >&2
fi

scan_and_cleanup

printf '\nSummary\n'
if [[ "$dry_run" -eq 1 ]]; then
    printf '  Would remove: %d\n' "$deleted_count"
else
    printf '  Removed: %d\n' "$deleted_count"
fi
printf '  Kept: %d\n' "$kept_count"
printf '  Skipped/errors: %d\n' "$skipped_count"

load_remaining_worktrees
print_remaining_worktrees 'Remaining worktrees'

if [[ "$interactive" -eq 1 && "${#remaining_paths[@]}" -gt 0 ]]; then
    select_interactively
    remove_interactive_selection
    load_remaining_worktrees
    print_remaining_worktrees 'Remaining worktrees after interactive deletions'
fi
