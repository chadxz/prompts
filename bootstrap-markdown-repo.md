---
description: Bootstrap a markdown-first repository that mirrors the prompts repo tooling.
---

# Bootstrap Markdown Repo Blueprint

## Goal

Bootstrap a fresh markdown-first repository that mirrors the tooling setup from
`https://github.com/chadxz/prompts` (jj, mise, dprint, marksman) while keeping
project-specific content minimal and bespoke to the new repository.

## Interactive Setup

- Start by prompting the user for two inputs:
  - **Repository name** (required).
  - **Destination path** (optional, default to the current working directory).
- Create the target directory only after both answers are confirmed.

## Reference Acquisition

- Inspect `https://github.com/chadxz/prompts` solely to copy shared tooling and
  configuration assets. At a minimum, bring over `.editorconfig`, `.helix/`,
  `mise.toml`, `dprint.json`, `.gitignore`, helper scripts, and any other files
  or directories that exist purely to configure editors, tooling, or automation.
- Do **not** copy prompt content, docs, or any narrative material that is
  specific to the source repository.
- Adjust only the values that must change for the new environment (project name,
  remote URLs, etc.).

## Repository Initialization

- After creating the destination directory, run `jj git init` so jj manages
  history.
- Immediately capture an initial change description such as `jj describe -m
  "init"`; this keeps the change open and removes any staging requirement.
- Copy the configuration files into place and run `jj status` as needed to
  inspect pending changes while the initial change remains open.

## mise + Tooling Setup

- Ensure the new project retains the same `mise.toml` contents:

  ```toml
  [tools]
  dprint = "latest"
  marksman = "latest"
  ```

- Run `mise trust` followed by `mise install` to materialize the toolchain. If
  extra runtimes or tools are required, update `mise.toml` and document the
  adjustments.

## Documentation

- Author a minimal `README.md` that includes:
  - The project title.
  - Brief instructions for installing dependencies via `mise install`.
  - Formatting instructions (e.g. `mise run format` or `dprint fmt`).
- Omit any additional narrative copied from the reference repository.

## Validation

- Execute the formatter helper or `mise run format` to confirm `dprint` leaves a
  clean tree.
- Verify the copied scaffolding (including `.helix/`) exists and that `jj
  status` shows no unexpected modifications after formatting.

## Remote Finalization (Manual)

- Prompt the user to run `gh repo create` (no additional arguments) from the
  project root and follow the interactive prompts to name the repository.
- After the remote exists, run
  `jj git remote add origin https://github.com/<owner>/<repo>.git`.
- Add a bookmark so `main` points at the current change:
  `jj bookmark create main`.
- Suggest the user run `jj git push --allow-new` to publish the repository.

## Deliverable

A ready-to-push repository that matches the configuration and tooling baseline
of the reference project without importing its project-specific content.
