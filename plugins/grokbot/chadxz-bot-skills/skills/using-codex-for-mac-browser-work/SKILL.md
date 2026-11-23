---
name: using-codex-for-mac-browser-work
description: >-
  Use when a task needs a browser or a GUI app on Chad's Mac (machine
  484f84c2-f218-4443-bb08-3778e593f230), such as a site with no connector or an
  app you can't drive with commands.
---

# Using Codex for browser work on Chad's Mac

- Run browser work on the Mac through Codex Computer Use:
  `codex exec --yolo`. Never use Grok Bot's built-in computer use on the Mac
  (Chad, Nov 17, 2026). It keeps popping the browser up while it enables
  JavaScript from AppleScript.
- If Codex's Chrome browser plugin fails (for example "browser access host is
  unavailable"), tell Codex to use macOS Computer Use instead (Chad, Nov 2, 2026).
- This doesn't change your own box browser. Use that as usual.

## Admin consoles are your job

- A step in a vendor's web console (Claude Console, Azure portal, Datadog,
  GitHub settings, and so on) with no API or CLI is browser work. Chad is
  logged in on the Mac, so "needs an admin" means do it through Codex on the
  Mac. Don't hand it to a person.
- If the Mac is offline, add the step to the list you finish when the Mac is
  back, the same way you would a Mac-only command. Say "waiting on the Mac,"
  not "needs a human."
- Ask Chad only when the console blocks Codex: a 2FA prompt, a locked
  1Password, or a role Chad doesn't have. Say which one it was.
