---
description: Create a commit with a well-formatted message.
---

# Create Commit

Create a commit message following my personal Git commit template.

## Template Lookup

First, retrieve my commit template:

```bash
git config --get commit.template
```

Then read the file at that path to understand the format.

## Constraints

- **Title**: Maximum 50 characters
- **Body**: Line length must not exceed 72 characters

## Before Generating

Unless I've already specified:

1. Check if I'm on `main` — if so, ask if I want to create a new branch first
2. Ask if I want to include a **co-authors** section
3. Ask for the **associated ticket number**
