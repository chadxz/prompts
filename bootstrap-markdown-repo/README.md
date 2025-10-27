# Bootstrap Markdown Repo Blueprint

## Goal

Use `https://github.com/chadxz/prompts` as the reference blueprint for
bootstrapping a new markdown-first project. Produce a fresh repository that
mirrors the structure and tooling (jj, mise, dprint, marksman) while customizing
names and narrative content to suit the new project.

## Reference Acquisition

- Inspect the `https://github.com/chadxz/prompts` repository tree.
- Copy every file that defines tooling defaults (`.editorconfig`, `mise.toml`,
  `dprint.json`, `.gitignore`, helper scripts, prompt directories, etc.) into
  the new workspace.
- Edit only fields that must change (project name, documentation copy, remote
  URLs, badges, or links) while preserving formatting and comments.

## Repository Initialization

- Create an empty directory for the new project.
- Run `jj git init` so jj manages history.
- Add the copied files, use `jj describe` to author the initial change message,
  and keep the change open for now (do not push yet).

## mise + Tooling Setup

- Ensure the new project retains the same `mise.toml` contents:

  ```toml
  [tools]
  dprint = "latest"
  marksman = "latest"
  ```

- Run `mise install` to materialize the toolchain. If a new runtime or tool is
  required, update `mise.toml` accordingly and document the change in both the
  commit description and README.

## Documentation

- Update `README.md` so it describes the new project while preserving sections
  that explain tooling commands (`mise run format`, `dprint fmt`, marksman
  language server usage, etc.).
- Carry over additional docs (templates, onboarding notes) from the reference
  repo, editing only where the new project’s context differs.

## Validation

- Execute the formatter helper or `mise run format` to confirm `dprint` leaves a
  clean tree.
- Verify `jj status` shows no unexpected modifications after formatting.

## Remote Finalization (Manual)

- Instruct the user to run `gh repo create <new-repo>` from the project root.
  This command prints the canonical HTTPS URL; append `.git` when using it as a
  remote.
- After the remote exists, run
  `jj git remote add origin https://github.com/<owner>/<repo>.git`.
- Add a bookmark so `main` points at the current change:
  `jj bookmark create main`.
- Suggest the user run `jj git push --allow-new` to publish the new repository.

## Deliverable

A ready-to-push repository that faithfully mirrors this blueprint’s structure
and automation, differing only where the destination project’s naming or content
demands it.
