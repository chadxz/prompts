---
name: commenting-on-prs
description:
  Posts inline comments, file-level comments, and review replies on
  GitHub pull requests on Chad's behalf. Trigger when replying to PR
  review comments, leaving PR comments, formatting GitHub alert callouts,
  or responding to review feedback. Applies Chad's writing voice and uses
  the gh CLI.
---

# Commenting on PRs

Before writing any comment text, load and read the writing-in-my-voice skill.
Don't rely on memory; read the rules fresh every time this skill runs.

Use `gh` to post comments. Prefer feeding multiline bodies through stdin instead
of embedding escaped newlines in a quoted argument. Shells do not turn `\n`
inside ordinary quotes into newline characters, so GitHub will receive the
literal backslash-n text.

## Comment Placement

Start every new comment as a review thread attached to the relevant changed
line or file. Never leave a top-level pull request comment, including for
overall feedback, status updates, or feedback that doesn't apply to a specific
line. When there isn't a useful line target, attach a file-level comment to the
most relevant file.

Keep each new review thread unresolved until the pull request owner replies and
acknowledges it. A code change without a reply isn't an acknowledgement. Treat
any unacknowledged thread as blocking approval or merge so the owner has to
respond before the pull request can merge.

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

Common patterns:

```bash
# Start an inline review thread
gh api --method POST repos/{owner}/{repo}/pulls/{pr}/comments \
  -f commit_id='{head_sha}' \
  -f path='{path}' \
  -f side='RIGHT' \
  -F line=42 \
  -F body=@- <<'EOF'
<comment>
EOF

# Start a file-level review thread
gh api --method POST repos/{owner}/{repo}/pulls/{pr}/comments \
  -f commit_id='{head_sha}' \
  -f path='{path}' \
  -f subject_type='file' \
  -F body=@- <<'EOF'
<comment>
EOF

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
```

If a comment is short enough for a single line, `--body "<comment>"` and
`-f body="<comment>"` are fine. For anything with blank lines, bullets, or
paragraph breaks, use the heredoc form above or write a temporary Markdown file
and pass it with `--body-file` / `-F body=@file.md`.

Never type escaped newline sequences such as `\n\n` into `--body` or `-f body=`
expecting GitHub to render paragraph breaks.

Keep comments short. A few sentences with enough context to stand alone months
later.

## GitHub Alerts

Use GitHub's blockquote-based alerts when a review comment needs a callout:

```markdown
> [!WARNING]
> This migration replaces the production database.
```

Choose the alert type by purpose:

- `NOTE`: useful context readers should know, even when skimming.
- `TIP`: advice that makes the work easier or better.
- `IMPORTANT`: information required to achieve the intended result.
- `WARNING`: urgent information needed to avoid a problem.
- `CAUTION`: a risk or negative outcome.

Keep `> [!TYPE]` on its own line and prefix every content line with `>`. Don't
nest alerts, place them consecutively, or use more than one or two in a comment.
Prefer ordinary prose when the content doesn't need visual emphasis.

When replying to bot comments (claude[bot], Dependabot, GitHub Actions), don't
address the bot as a person. No "good catch", "thanks for flagging", or "great
find". State the facts for the humans who'll read the thread later.
