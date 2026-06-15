---
name: creating-agent-files
description:
  Creates or updates repository agent instruction files using Chad's shared
  source-of-truth pattern. Use when adding CONTRIBUTING.md, AGENTS.md, or
  CLAUDE.md files, migrating existing agent instructions, or standardizing a
  repo or subdirectory so Codex, Claude, and other agents read the same
  guidance.
---

# Creating Agent Files

Use this workflow when a repository or subdirectory needs agent instructions.
`CONTRIBUTING.md` is the source of truth. `AGENTS.md` points agents that load
that filename at the same content, and `CLAUDE.md` uses Claude's include syntax
to read it too.

## Pattern

Create these files in the same directory:

- `CONTRIBUTING.md` contains the actual guidance.
- `AGENTS.md` is a relative symlink to `CONTRIBUTING.md`.
- `CLAUDE.md` contains exactly `@CONTRIBUTING.md`, followed by a newline.

Use the same pattern at the repository root and in scoped directories that need
extra local instructions.

## Workflow

1. Read any existing `CONTRIBUTING.md`, `AGENTS.md`, and `CLAUDE.md` in the
   target directory before changing them.
2. Put all durable instructions in `CONTRIBUTING.md`. If existing `AGENTS.md`
   or `CLAUDE.md` files contain unique guidance, move that guidance into
   `CONTRIBUTING.md` before replacing them with the shared pattern.
3. Make `AGENTS.md` a relative symlink:

   ```bash
   ln -s CONTRIBUTING.md AGENTS.md
   ```

4. Make `CLAUDE.md` contain only the Claude include:

   ```markdown
   @CONTRIBUTING.md
   ```

5. Keep the instructions short and specific to that directory. Parent
   instructions still apply unless the local file says otherwise.

## Validation

Run these checks from the directory that owns the files:

```bash
test "$(readlink AGENTS.md)" = "CONTRIBUTING.md"
printf '@CONTRIBUTING.md\n' | cmp - CLAUDE.md
```

Also inspect the Git diff before finishing. `AGENTS.md` should show as a
symlink, and `CLAUDE.md` should show only the include line.
