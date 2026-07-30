# Personal Rules

## Shells and Tools

- Rename files with the `mv` command.

- Build Docker images with `docker buildx build`.

- In shell commands and scripts, never repurpose `$HOME`, `$PATH`, or
  `$CODEX_HOME`. In zsh, do not assign to special parameters such as `status`,
  `path`, `commands`, `functions`, `pipestatus`, or `home`. Use domain-specific
  names such as `exit_code`, `file_path`, or `command_status`.

- Quote shell arguments containing glob characters, especially GitHub API
  endpoints containing `?`. Run Bash-specific code explicitly with Bash rather
  than the default zsh shell.

- Use the date provided by the environment rather than relying on model
  knowledge. Query the system when no date is provided or exact local time
  matters.

- When writing or running Python scripts, use `uv` to provide the interpreter
  and dependencies.

- If `mise` reports that a directory is untrusted, run `mise trust` rather than
  working around the trust failure.

## Repository Workflow and Change Safety

- Look for source repositories under `~/src`.

- Before changing files in a Git repository, work from a task-specific Git
  worktree and use the `using-git-worktrees` skill when available.

- In local sessions, commit or push only when explicitly requested. In cloud
  implementation tasks, commit and push without asking separately when doing so
  is part of delivering the requested change. Never run `terraform apply`
  without explicit permission.

- Never force-push `main` unless explicitly requested. For any authorized force
  push, use `--force-with-lease`. If the lease is rejected, investigate; never
  fall back to `--force`.

- In a monorepo, invoke and refer to mise tasks using monorepo syntax. The
  absolute form is `//apps/my-app:test`; the relative form is `:test`.

## Durable and UI Content

- Hard-wrap Markdown prose at 80 characters when its durable form is a
  repository file or standalone artifact. Hard-wrap commit messages likewise.

- Do not hard-wrap ordinary chat or UI-submitted content, including PR
  descriptions, GitHub issue comments, and Linear ticket descriptions or
  comments. This applies even when content is staged in a temporary file or
  passed through `linctl`. Preserve intentional Markdown structure and let the
  target UI wrap prose.

## Connected Services and Browser

- When opening or inspecting a GitHub URL, use the `gh` CLI rather than browser
  or web tools.

- When given a `notion.so` URL, access it with the available Notion tools rather
  than web tools.

- Use `linctl` to look up Linear ticket details. Run `linctl docs` when usage
  guidance is needed.

- Safari is my primary web browser. For browser UI tasks that require computer
  use, prefer Codex Computer Use with Safari. Do not use Chrome or
  Chrome-extension-driven browser control unless I explicitly request it or
  Safari Computer Use cannot complete the required workflow.

## Personal Context

- Convergint is the correct spelling of my company's name; do not treat it as a
  typo.

- I lead platform engineering at Convergint. Surface optional platform
  improvements as considerations, but do not gate application work on them; I
  can drive those improvements separately.

## Code Style

- When writing C# unit tests, do not add Arrange / Act / Assert comments.

- Give every named TypeScript or JavaScript function and class a JSDoc header
  that explains its purpose and any non-obvious context. Exclude trivial inline
  callbacks. In TypeScript JSDoc, do not repeat types using annotations such as
  `{string}`. Describe parameters and return values when those descriptions
  clarify behavior.

- Do not add directory-tree listings to README files.

- Do not create new grab-bag modules such as `utils`, `helpers`, or `constants`.
  Place constants and helper functions alongside the code that uses them, or in
  narrowly named domain modules when sharing is necessary.
