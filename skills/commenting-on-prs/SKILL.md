---
name: commenting-on-prs
description:
  Posts comments and review replies on GitHub pull requests on
  Chad's behalf. Trigger when replying to PR review comments,
  leaving PR comments, or responding to review feedback. Applies
  Chad's writing voice and uses the gh CLI.
---

# Commenting on PRs

Before writing any comment text, load and read the
writing-in-my-voice skill. Don't rely on memory; read the
rules fresh every time this skill runs.

Use `gh` to post comments. Common patterns:

```bash
# Reply to a review comment thread
gh api repos/{owner}/{repo}/pulls/{pr}/comments/{id}/replies \
  -f body="<comment>"

# Leave a top-level PR comment
gh pr comment {pr} --repo {owner}/{repo} --body "<comment>"
```

Keep comments short. A few sentences with enough context to stand
alone months later.

When replying to bot comments (claude[bot], Dependabot, GitHub
Actions), don't address the bot as a person. No "good catch",
"thanks for flagging", or "great find". State the facts for the
humans who'll read the thread later.
