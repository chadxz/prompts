---
name: formatting-github-alerts
description:
  Formats GitHub alert callouts (NOTE, TIP, IMPORTANT, WARNING,
  CAUTION) in markdown. Use when adding annotations, callouts, or
  admonitions to GitHub PR descriptions, comments, issues, or any
  GitHub-rendered markdown.
---

# GitHub Alerts

GitHub renders blockquote-based alerts with colored callout styling.

## Syntax

```markdown
> [!NOTE]
> Useful information that users should know, even when skimming.

> [!TIP]
> Helpful advice for doing things better or more easily.

> [!IMPORTANT]
> Key information users need to know to achieve their goal.

> [!WARNING]
> Urgent info that needs immediate user attention to avoid problems.

> [!CAUTION]
> Advises about risks or negative outcomes of certain actions.
```

## Rules

- The `> [!TYPE]` line must be on its own line inside the blockquote.
- Alert content follows as additional blockquote lines.
- Don't nest alerts inside other elements.
- Don't place alerts consecutively.
- Use sparingly: one or two per document at most.
