---
name: commenting-on-prs
description:
  Posts comments and review replies on GitHub pull requests on
  Chad's behalf. Trigger when replying to PR review comments,
  leaving PR comments, or responding to review feedback. Applies
  Chad's writing voice and uses the gh CLI.
---

# Commenting on PRs

Before writing any comment text, load and read the writing-in-my-voice skill.
Don't rely on memory; read the rules fresh every time this skill runs.

Use `gh` to post comments. Prefer feeding multiline bodies through stdin instead
of embedding escaped newlines in a quoted argument. Shells do not turn `\n`
inside ordinary quotes into newline characters, so GitHub will receive the
literal backslash-n text.

## Review Feedback Workflow

When responding to inline PR feedback, reply to the existing review comment
thread and then resolve that review thread. Use thread-aware data from GitHub
GraphQL or the GitHub comment helper scripts to map both IDs involved:

- the review comment REST ID for the reply endpoint
- the review thread GraphQL ID for `resolveReviewThread`

Treat a user request to respond to PR feedback as permission to reply in-thread
and resolve the thread once the feedback has been addressed. Leave a thread
unresolved only when the response asks for clarification, explains that the
feedback won't be addressed, or the user explicitly asks not to resolve it.

Do not leave a top-level PR comment for inline feedback when a review thread is
available. Top-level PR comments are only appropriate for top-level feedback,
overall status updates, or comments that aren't attached to a review thread.

Common patterns:

```bash
# Reply to a review comment thread
gh api repos/{owner}/{repo}/pulls/{pr}/comments/{id}/replies \
  -F body=@- <<'EOF'
<comment>
EOF

# Resolve the review thread after replying
gh api graphql \
  -f query='
mutation($threadId: ID!) {
  resolveReviewThread(input: { threadId: $threadId }) {
    thread { id isResolved }
  }
}
' \
  -f threadId='{thread_id}'

# Leave a top-level PR comment
gh pr comment {pr} --repo {owner}/{repo} --body-file - <<'EOF'
<comment>
EOF
```

If a comment is short enough for a single line, `--body "<comment>"` and
`-f body="<comment>"` are fine. For anything with blank lines, bullets, or
paragraph breaks, use the heredoc form above or write a temporary Markdown file
and pass it with `--body-file` / `-F body=@file.md`.

Never type escaped newline sequences such as `\n\n` into `--body` or `-f body=`
expecting GitHub to render paragraph breaks.

Keep comments short. A few sentences with enough context to stand alone months
later.

When replying to bot comments (claude[bot], Dependabot, GitHub Actions), don't
address the bot as a person. No "good catch", "thanks for flagging", or "great
find". State the facts for the humans who'll read the thread later.
