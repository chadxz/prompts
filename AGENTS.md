# Personal Rules

- Any time you are renaming a file, use the `mv` command.

- When building Docker images, use `docker buildx build` instead of
  `docker build`.

- Don't assume the current date from model knowledge. Prefer the date provided
  by the environment context, and look it up yourself if you don't already have
  it. Use an explicit lookup when exact local time matters.

- When running locally, do not perform any Git commit or push or Terraform
  apply unless explicitly requested to do so. When running in a cloud agent,
  Git commits and pushes are allowed without asking for permission first, but
  Terraform apply still requires explicit permission.

- Never force a git push to main, unless explicitly requested to do so.

- When you are doing a git push and need to force, always use --force-with-lease.
  If it fails, investigate, but always use --force-with-lease.

- When writing Markdown intended as a saved or submitted artifact, wrap prose
  at 80 characters and make sure it is easy to read without rendering. This
  keeps durable text pleasant to review in diffs, terminals, and plain text
  editors. This includes things like repo files, temp files, and commit
  messages. Do not hard-wrap PR descriptions, issue comments, or ordinary chat
  responses unless I ask for wrapped output.

- Any time you want to look at a github link, use `gh` cli instead.

- Any time I paste a notion.so link, use the available Notion tools to access
  it instead of web tools.

- I work at a company named "Convergint" spelled exactly like that, and it is
  not a misspelling.

- When writing C# unit tests, do not add Arrange / Act / Assert comments.

- When writing and executing Python scripts, use `uv` to ensure the necessary
  runtime and packages are installed and available.

- Use `linctl` to lookup details of linear tickets when asked. `linctl docs`
  will show you how to use it.

- When in a monorepo and referring to mise tasks, always use the monorepo
  syntax. The absolute path form is //apps/my-app:test. The relative form is :test.

- Do not put directory structures in README files.
