# Skills

## Upstream Sources

The `developing-temporal-applications` skill is sourced from the upstream
Temporal developer skill repository, `temporalio/skill-temporal-developer`. It
was imported from commit `3973e73202f72cb6b157b827f270c04f96ad8c1f` on the
upstream `main` branch.

Repository: https://github.com/temporalio/skill-temporal-developer

### Updating developing-temporal-applications

Refresh the vendored skill from the repository root:

```bash
tmp="$(mktemp -d)"
GIT_BARE_CLONE_BYPASS=1 git clone --depth 1 \
  https://github.com/temporalio/skill-temporal-developer "$tmp/upstream"
git -C "$tmp/upstream" rev-parse HEAD
rsync -a --delete \
  --exclude '.git' --exclude '.github' --exclude 'README.md' \
  "$tmp/upstream/" skills/developing-temporal-applications/
rm -rf "$tmp"
```

The bypass variable keeps Chad's bare-clone git wrapper from rewriting the
temporary clone. After the sync, update the pinned commit above with the SHA
printed by `rev-parse`, review the diff, and commit.
