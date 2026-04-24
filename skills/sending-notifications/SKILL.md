---
name: sending-notifications
description:
  Sends macOS notification alerts to Chad. Use after completing long-running
  work or when the user wants to get Chad's attention.
user-invocable: true
---

# Sending Notifications

Send a macOS alert dialog when the user asks for a notification or after
completing long-running work.

## Usage

Run this command, replacing the message with whatever is appropriate for the
context:

```bash
osascript <<'APPLESCRIPT'
display alert "Claude Code" message "<message>"
APPLESCRIPT
```

## Guidelines

- Default message: "Task complete!"
- Keep the message short and informative.
- If the user provides a custom message, use that instead.
- The title should always be "Claude Code".
