# Personal Rules

- Any time you are renaming a file, use the `mv` command.

- When building Docker images, use `docker buildx build` instead of
  `docker build`.

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

- When writing Markdown intended as a saved or submitted artifact, wrap prose at
  80 characters and make sure it is easy to read without rendering. This keeps
  durable text pleasant to review in diffs, terminals, and plain text editors.
  This includes things like repo files, temp files, and commit messages. Do not
  hard-wrap PR descriptions, issue comments, or ordinary chat responses unless I
  ask for wrapped output.

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
