---
name: notify
description:
  Sends a macOS notification alert to Chad. Use after completing
  long-running work or when the user wants to get Chad's attention.
user-invocable: true
---

# Notify

Send a macOS alert dialog to notify me. This is useful after completing
long-running tasks.

## Usage

Run the following command, replacing the message with whatever is
appropriate for the context:

```bash
osascript <<'APPLESCRIPT'
display alert "Claude Code" message "<message>"
APPLESCRIPT
```

## Guidelines

- Default message: "Task complete!"
- Keep the message short and informative
- If I provide a custom message, use that instead
- The title should always be "Claude Code"
