# Personal Rules

- Any time you are renaming a file, use the `mv` command.

- When building Docker images, use `docker buildx build` instead of
  `docker build`.

- Always lookup the current date before ever doing anything that involves using
  the date (i.e. web searches, defining filenames with the date in them, etc).

- Do not perform any Git commit or push or Terraform apply unless explicitly
  requested to do so.

- Never force a git push to main.

- When you are doing a git push and need to force, always use --force-with-lease.
  If it fails, investigate, but always use --force-with-lease.

- When writing markdown, always wrap at 80 character line length and make sure
  it is easy to read without rendering (tables should line up etc).

- Any time you want to look at a github link, use `gh` cli instead.

- I work at a company named "Convergint" spelled exactly like that, and it is
  not a misspelling.

- When writing C# unit tests, do not add Arrange / Act / Assert comments.

- Use `linctl` to lookup details of linear tickets when asked. `linctl docs`
  will show you how to use it.

- When in a monorepo and referring to mise tasks, always use the monorepo
  syntax. The absolute path form is //apps/my-app:test. The relative form is :test.

- Do not put directory structures in README files.
