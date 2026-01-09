# Personal Rules

- Any time you are renaming a file, use the `mv` command.

- When building Docker images, use `docker buildx build` instead of
  `docker build`.

- Always lookup the current date before ever doing anything that involves using
  the date (i.e. searches, defining filenames, etc).

- Do not perform any Git commit or push or Terraform apply unless explicitly
  requested to do so.

- When writing markdown, always wrap at 80 character line length and make sure
  it is easy to read without rendering (tables should line up etc).

- Any time you want to look at a github link, use `gh` cli instead.

- When writing C# unit tests, do not add Arrange / Act / Assert comments.

- When you are doing a git push and need to force, always use --force-with-lease.
  If it fails, investigate, but always use --force-with-lease.

- Use `linctl` to lookup details of linear tickets when asked. `linctl docs`
  will show you how to use it.
