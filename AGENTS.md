# Personal Rules

- Any time you are renaming a file, use the `mv` command.

- When building Docker images, use `docker buildx build` instead of
  `docker build`.

- In zsh commands and scripts, never use special parameter names such as
  `status`, `path`, `commands`, `functions`, or `pipestatus` as variables. Use
  domain-specific names such as `exit_code`, `file_path`, or `command_status`.
  Never repurpose `$HOME`, `$home`, `$PATH`, `$path`, or `$CODEX_HOME`.

- Quote shell arguments containing glob characters, especially GitHub API
  endpoints containing `?`. When code uses Bash-specific syntax or semantics,
  run it explicitly with Bash instead of the default zsh shell.

- Don't assume the current date from model knowledge. Prefer the date provided
  by the environment context, and look it up yourself if you don't already have
  it. Use an explicit lookup when exact local time matters.

- When running locally, do not perform any Git commit or push or Terraform apply
  unless explicitly requested to do so. When running in a cloud agent, Git
  commits and pushes are allowed without asking for permission first, but
  Terraform apply still requires explicit permission.

- Source for applications can be found in `~/src`.

- When changing files in a git repository, work from a task-specific git
  worktree and use the `using-git-worktrees` skill when available.

- Never force a git push to main, unless explicitly requested to do so.

- When you are doing a git push and need to force, always use
  --force-with-lease. If it fails, investigate, but always use
  --force-with-lease.

- When Markdown's durable form is a file or commit message, wrap prose at 80
  characters and make sure it is easy to read without rendering. This keeps
  repo files, standalone temp artifacts, and commit messages pleasant to review
  in diffs, terminals, and plain text editors. This rule excludes chat and
  UI-submitted text such as PR descriptions, GitHub issue comments, and Linear
  ticket content, even when a temporary file is used only to submit the text.

- Never hard-wrap ordinary chat responses, including progress updates and final
  answers. Do not insert newlines inside a prose paragraph, including prose
  within a list item. Preserve all intentional Markdown structure, including
  blank lines, headings, separate and nested list items, blockquotes, and code
  blocks, and let the chat UI wrap text.

- Never hard-wrap Linear ticket descriptions or comments. Do not insert newlines
  inside a prose paragraph, including prose within a list item or content staged
  in a temporary file or passed to `linctl`. Preserve all intentional Markdown
  structure, including blank lines, headings, separate and nested list items,
  blockquotes, and code blocks, and let Linear wrap text in the UI.

- Any time you want to look at a github link, use `gh` cli instead.

- Any time I paste a notion.so link, use the available Notion tools to access it
  instead of web tools.

- I work at a company named "Convergint" spelled exactly like that, and it is
  not a misspelling.

- I lead platform engineering at Convergint. Treat platform-related
  improvements as non-blockers: I can drive them myself, so don't gate
  application work on them. Do surface them as considerations in the course of
  building software.

- When writing C# unit tests, do not add Arrange / Act / Assert comments.

- When writing TypeScript or JavaScript, give every function and class a
  corresponding JSDoc header. The header should describe the purpose of the
  function or class and any context that helps a reader understand why it exists
  or why it is written a certain way. Avoid argument type annotations in
  TypeScript files, but include argument and return value explanations when they
  clarify behavior.

- When writing and executing Python scripts, use `uv` to ensure the necessary
  runtime and packages are installed and available.

- Use `linctl` to lookup details of linear tickets when asked. `linctl docs`
  will show you how to use it.

- When in a monorepo and referring to mise tasks, always use the monorepo
  syntax. The absolute path form is //apps/my-app:test. The relative form is
  :test.

- When using `mise` in a new directory, run `mise trust` if needed instead of
  working around trust failures.

- Do not put directory structures in README files.

- Avoid grab-bag files like `utils`, `helpers`, or `constants`. Prefer placing
  constants and helper functions alongside the code that uses them, or in
  narrowly named domain modules when sharing is truly needed.
