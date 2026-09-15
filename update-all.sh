#!/usr/bin/env bash

set -euo pipefail

root_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
main_worktree_name="main"

dry_run=0
if [[ "${1:-}" == "--dry-run" ]]; then
    dry_run=1
    shift
fi

if [[ $# -gt 0 ]]; then
    echo "Usage: $(basename "$0") [--dry-run]" >&2
    exit 1
fi

declare -a skipped_repos=()
declare -a removed_repos=()

remote_state_dir="$(mktemp -d)"
trap 'rm -rf "${remote_state_dir}"' EXIT
active_repos_file="${remote_state_dir}/active-repos"
archived_repos_file="${remote_state_dir}/archived-repos"
: >"${active_repos_file}"
: >"${archived_repos_file}"

say_scan() {
    local message="$1"

    if [[ $dry_run -eq 1 ]]; then
        echo "${message} (dry run)"
    else
        echo "${message}"
    fi
}

record_skip() {
    local repo_name="$1"
    local reason="$2"

    skipped_repos+=("${repo_name}: ${reason}")
}

record_removed() {
    local repo_name="$1"
    local reason="$2"

    removed_repos+=("${repo_name}: ${reason}")
}

file_contains_line() {
    local line="$1"
    local file="$2"

    grep -Fqx -- "${line}" "${file}"
}

ensure_fetch_refspec() {
    local repo_path="$1"

    git -C "${repo_path}" config --replace-all \
        remote.origin.fetch '+refs/heads/*:refs/remotes/origin/*'
}

fetch_origin() {
    local repo_path="$1"
    local fetch_error

    fetch_error="$(mktemp)"
    if git -C "${repo_path}" fetch --prune --quiet origin 2>"${fetch_error}"; then
        rm -f "${fetch_error}"
        return 0
    fi

    if grep -q "case-insensitive filesystem" "${fetch_error}" \
        && [[ "$(git -C "${repo_path}" config --get extensions.refStorage \
            || true)" != "reftable" ]]; then
        git -C "${repo_path}" refs migrate --ref-format=reftable
        if git -C "${repo_path}" fetch --prune --quiet origin \
            2>"${fetch_error}"; then
            rm -f "${fetch_error}"
            return 0
        fi
    fi

    cat "${fetch_error}" >&2
    rm -f "${fetch_error}"
    return 1
}

remote_ref_for_branch() {
    local repo_path="$1"
    local branch="$2"

    if git -C "${repo_path}" show-ref --verify --quiet \
        "refs/remotes/origin/${branch}"; then
        printf 'refs/remotes/origin/%s\n' "${branch}"
        return 0
    fi

    if git -C "${repo_path}" show-ref --verify --quiet "refs/heads/${branch}"; then
        printf 'refs/heads/%s\n' "${branch}"
        return 0
    fi

    return 1
}

ensure_main_tracks_origin() {
    local repo_name="$1"
    local repo_path="$2"
    local default_branch="$3"
    local main_path="${repo_path}/${main_worktree_name}"
    local current_branch
    local upstream

    current_branch="$(git -C "${main_path}" rev-parse --abbrev-ref HEAD \
        2>/dev/null || echo "detached")"
    if [[ "${current_branch}" != "${default_branch}" ]]; then
        return 0
    fi

    if ! git -C "${repo_path}" show-ref --verify --quiet \
        "refs/remotes/origin/${default_branch}"; then
        echo "⚠️  ${repo_name}: no origin/${default_branch} to track"
        record_skip "${repo_name}" "no origin/${default_branch} to track"
        return 1
    fi

    upstream="$(git -C "${repo_path}" for-each-ref \
        --format='%(upstream:short)' "refs/heads/${default_branch}")"
    if [[ "${upstream}" == "origin/${default_branch}" ]]; then
        return 0
    fi

    if [[ $dry_run -eq 1 ]]; then
        echo "🔗 ${repo_name}: would set ${default_branch} to track origin/${default_branch}"
        return 0
    fi

    if git -C "${repo_path}" branch --set-upstream-to \
        "origin/${default_branch}" "${default_branch}" >/dev/null; then
        echo "🔗 ${repo_name}: ${default_branch} now tracks origin/${default_branch}"
        return 0
    fi

    echo "   ❌ Could not set upstream for ${default_branch}"
    record_skip "${repo_name}" "could not set upstream for ${default_branch}"
    return 1
}

infer_default_branch() {
    local repo_path="$1"
    local default_branch="${2:-}"
    local origin_head

    if [[ -n "${default_branch}" ]]; then
        printf '%s\n' "${default_branch}"
        return 0
    fi

    origin_head="$(git -C "${repo_path}" symbolic-ref --quiet --short \
        refs/remotes/origin/HEAD 2>/dev/null || true)"
    if [[ -n "${origin_head}" ]]; then
        printf '%s\n' "${origin_head#origin/}"
        return 0
    fi

    if git -C "${repo_path}" show-ref --verify --quiet refs/remotes/origin/main \
        || git -C "${repo_path}" show-ref --verify --quiet refs/heads/main; then
        printf 'main\n'
        return 0
    fi

    if git -C "${repo_path}" show-ref --verify --quiet refs/remotes/origin/master \
        || git -C "${repo_path}" show-ref --verify --quiet refs/heads/master; then
        printf 'master\n'
        return 0
    fi

    git -C "${repo_path}" for-each-ref --format='%(refname:short)' \
        refs/remotes/origin refs/heads | sed 's#^origin/##' | head -n 1
}

clone_bare_repo() {
    local repo_name="$1"
    local clone_url="$2"
    local repo_path="$3"

    if [[ $dry_run -eq 1 ]]; then
        echo "📦 ${repo_name}: not cloned locally (would clone bare repo with gh)"
        return 0
    fi

    echo "📦 ${repo_name}: not cloned locally (cloning bare repo with gh...)"
    if ! mkdir -p "${repo_path}"; then
        echo "   ❌ Could not create repo directory"
        record_skip "${repo_name}" "could not create repo directory"
        return 1
    fi

    if gh repo clone "${clone_url}" "${repo_path}/.git" --no-upstream \
        -- --bare --quiet; then
        ensure_fetch_refspec "${repo_path}"
        echo "   ✅ Cloned bare repo into ${repo_name}/.git"
        return 0
    fi

    echo "   ❌ Clone failed"
    record_skip "${repo_name}" "clone failed"
    return 1
}

ensure_main_worktree() {
    local repo_name="$1"
    local repo_path="$2"
    local default_branch="$3"
    local main_path="${repo_path}/${main_worktree_name}"
    local add_args=()

    if [[ -d "${main_path}" ]]; then
        if git -C "${main_path}" rev-parse --git-dir >/dev/null 2>&1; then
            return 0
        fi

        echo "⚠️  ${repo_name}: ${main_worktree_name}/ exists but is not a Git worktree"
        record_skip "${repo_name}" "${main_worktree_name}/ is not a Git worktree"
        return 1
    fi

    if git -C "${repo_path}" show-ref --verify --quiet \
        "refs/heads/${default_branch}"; then
        add_args=("${main_path}" "${default_branch}")
    elif git -C "${repo_path}" show-ref --verify --quiet \
        "refs/remotes/origin/${default_branch}"; then
        add_args=("--track" "-b" "${default_branch}" "${main_path}" \
            "refs/remotes/origin/${default_branch}")
    else
        echo "⚠️  ${repo_name}: cannot find branch ${default_branch}"
        record_skip "${repo_name}" "cannot find branch ${default_branch}"
        return 1
    fi

    if [[ $dry_run -eq 1 ]]; then
        echo "🌱 ${repo_name}: would create ${main_worktree_name}/ for ${default_branch}"
        return 0
    fi

    echo "🌱 ${repo_name}: creating ${main_worktree_name}/ for ${default_branch}"
    if git -C "${repo_path}" worktree add --quiet "${add_args[@]}"; then
        echo "   ✅ Created ${main_worktree_name}/"
        return 0
    fi

    echo "   ❌ Could not create ${main_worktree_name}/"
    record_skip "${repo_name}" "could not create ${main_worktree_name}/"
    return 1
}

update_main_worktree() {
    local repo_name="$1"
    local repo_path="$2"
    local default_branch="$3"
    local main_path="${repo_path}/${main_worktree_name}"
    local current_branch
    local local_commit
    local remote_commit
    local remote_ref
    local commits_behind

    if [[ -n "$(git -C "${main_path}" status --porcelain)" ]]; then
        echo "⚠️  ${repo_name}: ${main_worktree_name}/ has uncommitted changes"
        record_skip "${repo_name}" "uncommitted changes in ${main_worktree_name}/"
        return 1
    fi

    current_branch="$(git -C "${main_path}" rev-parse --abbrev-ref HEAD \
        2>/dev/null || echo "detached")"
    if [[ "${current_branch}" != "${default_branch}" ]]; then
        echo "⏭️  ${repo_name}: ${main_worktree_name}/ on ${current_branch}"
        record_skip "${repo_name}" \
            "${main_worktree_name}/ on ${current_branch}, expected ${default_branch}"
        return 1
    fi

    if ! remote_ref="$(remote_ref_for_branch "${repo_path}" "${default_branch}")"; then
        echo "⚠️  ${repo_name}: no fetched ref for ${default_branch}"
        record_skip "${repo_name}" "no fetched ref for ${default_branch}"
        return 1
    fi

    local_commit="$(git -C "${main_path}" rev-parse HEAD)"
    remote_commit="$(git -C "${repo_path}" rev-parse "${remote_ref}")"

    if [[ "${local_commit}" == "${remote_commit}" ]]; then
        echo "✓  ${repo_name}: ${main_worktree_name}/ up-to-date on ${default_branch}"
        return 0
    fi

    if ! git -C "${main_path}" merge-base --is-ancestor \
        HEAD "${remote_ref}" 2>/dev/null; then
        echo "⚠️  ${repo_name}: ${main_worktree_name}/ diverged from ${remote_ref}"
        record_skip "${repo_name}" \
            "${main_worktree_name}/ diverged from ${remote_ref}"
        return 1
    fi

    commits_behind="$(git -C "${main_path}" rev-list --count HEAD.."${remote_ref}")"

    if [[ $dry_run -eq 1 ]]; then
        echo "🔄 ${repo_name}: ${commits_behind} commit(s) behind (would update)"
        return 0
    fi

    echo "🔄 ${repo_name}: ${commits_behind} commit(s) behind (updating...)"
    if git -C "${main_path}" merge --ff-only --quiet "${remote_ref}"; then
        echo "   ✅ Updated ${main_worktree_name}/"
        return 0
    fi

    echo "   ❌ Update failed"
    record_skip "${repo_name}" "fast-forward failed"
    return 1
}

process_repo() {
    local repo_name="$1"
    local clone_url="$2"
    local default_branch="$3"
    local repo_path="${root_dir}/${repo_name}"

    if [[ ! -d "${repo_path}/.git" ]]; then
        clone_bare_repo "${repo_name}" "${clone_url}" "${repo_path}" || return 0
        [[ $dry_run -eq 0 ]] || return 0
    fi

    if [[ "$(git -C "${repo_path}" rev-parse --is-bare-repository \
        2>/dev/null || echo false)" != "true" ]]; then
        echo "⚠️  ${repo_name}: not using bare repo layout"
        record_skip "${repo_name}" "not using bare repo layout"
        return 0
    fi

    ensure_fetch_refspec "${repo_path}"
    if fetch_origin "${repo_path}"; then
        :
    else
        echo "⚠️  ${repo_name}: fetch failed"
        record_skip "${repo_name}" "fetch failed"
        return 0
    fi

    git -C "${repo_path}" remote set-head origin --auto >/dev/null 2>&1 || true

    default_branch="$(infer_default_branch "${repo_path}" "${default_branch}")"
    if [[ -z "${default_branch}" ]]; then
        echo "⚠️  ${repo_name}: cannot determine default branch"
        record_skip "${repo_name}" "cannot determine default branch"
        return 0
    fi

    ensure_main_worktree "${repo_name}" "${repo_path}" "${default_branch}" \
        || return 0
    [[ -d "${repo_path}/${main_worktree_name}" ]] || return 0
    ensure_main_tracks_origin "${repo_name}" "${repo_path}" "${default_branch}" \
        || return 0
    update_main_worktree "${repo_name}" "${repo_path}" "${default_branch}" \
        || return 0
}

remove_local_repo() {
    local repo_name="$1"
    local repo_path="$2"
    local reason="$3"

    if [[ $dry_run -eq 1 ]]; then
        echo "🗑️  ${repo_name}: would remove local repo (${reason})"
        return 0
    fi

    echo "🗑️  ${repo_name}: removing local repo (${reason})"
    if rm -rf -- "${repo_path}"; then
        record_removed "${repo_name}" "${reason}"
        echo "   ✅ Removed ${repo_name}/"
        return 0
    fi

    echo "   ❌ Could not remove ${repo_name}/"
    record_skip "${repo_name}" "could not remove local repo (${reason})"
    return 1
}

remove_inactive_local_repos() {
    local repo_path
    local repo_name
    local reason

    for repo_path in "${root_dir}"/*; do
        [[ -d "${repo_path}" ]] || continue
        [[ -d "${repo_path}/.git" ]] || continue

        repo_name="$(basename "${repo_path}")"
        if file_contains_line "${repo_name}" "${active_repos_file}"; then
            continue
        fi

        if [[ "$(git -C "${repo_path}" rev-parse --is-bare-repository \
            2>/dev/null || echo false)" != "true" ]]; then
            continue
        fi

        reason="no longer found upstream"
        if file_contains_line "${repo_name}" "${archived_repos_file}"; then
            reason="archived upstream"
        fi

        remove_local_repo "${repo_name}" "${repo_path}" "${reason}" || true
    done
}

if [[ $dry_run -eq 1 ]]; then
    say_scan "Checking non-archived repositories in convergint org"
else
    say_scan "Checking non-archived repositories in convergint org"
fi
echo ""

remote_repos="$(
    gh repo list convergint --limit 1000 \
        --json name,url,defaultBranchRef,isArchived \
        --jq '.[] | [.name, .url, .defaultBranchRef.name, (.isArchived | tostring)] | @tsv' \
        2>/dev/null || true
)"

if [[ -z "${remote_repos}" ]]; then
    echo "⚠️  Could not fetch repo list from convergint org (check gh auth status)"
else
    while IFS=$'\t' read -r repo_name clone_url default_branch is_archived; do
        [[ -n "${repo_name}" ]] || continue
        if [[ "${is_archived}" == "true" ]]; then
            printf '%s\n' "${repo_name}" >>"${archived_repos_file}"
            continue
        fi

        printf '%s\n' "${repo_name}" >>"${active_repos_file}"
        process_repo "${repo_name}" "${clone_url}" "${default_branch}"
    done <<< "${remote_repos}"

    remove_inactive_local_repos
fi

if [[ ${#removed_repos[@]} -gt 0 ]]; then
    echo ""
    echo "Repositories removed (${#removed_repos[@]}):"
    for entry in "${removed_repos[@]}"; do
        echo "  - ${entry}"
    done
fi

if [[ ${#skipped_repos[@]} -gt 0 ]]; then
    echo ""
    echo "Repositories not updated (${#skipped_repos[@]}):"
    for entry in "${skipped_repos[@]}"; do
        echo "  - ${entry}"
    done
fi

echo ""
echo "Done!"
