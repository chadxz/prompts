---
name: choosing-notion-tools
description:
  Chooses between Notion MCP and the official Notion CLI (`ntn`) for Notion
  work. Use when deciding how to search, read, create, edit, query, automate,
  upload files, create HTML blocks, manage Workers, or call the Notion API.
---

# Choosing Notion Tools

Use Notion MCP by default for interactive agent work. Use `ntn` when the task
depends on local files, shell automation, Workers, or a public API capability
that the MCP does not expose.

## Decision rule

Choose Notion MCP for:

- semantic search across Notion and connected sources
- normal page and database reads or edits
- SQL-style data source queries
- page duplication and teamspace discovery
- high-level, agent-oriented operations such as targeted content edits and
  DDL-style database schema changes
- any `notion.so` or `notion.com` link supplied by the user

Choose `ntn` for:

- uploading local files
- creating HTML blocks through a file upload and `embed` block
- Notion Workers development and operations
- repeatable shell or CI automation
- low-level block CRUD and direct public API access
- operations missing from the current MCP tool surface

When both can complete the task, prefer MCP for an interactive agent session
and `ntn` for a reusable script.

## Verify current capabilities

Both surfaces change frequently. Before claiming that one cannot do something,
inspect the live tools:

```bash
ntn --help
ntn api ls
ntn doctor
```

Also inspect the currently exposed Notion MCP tools. Treat an absent MCP wrapper
as a tool-surface gap, not proof that Notion itself lacks the capability.

## Authentication

When MCP and `ntn` authenticate as the same user in the same workspace, they use
the same user permission boundary and should see the same pages. A different
workspace, user, or `NOTION_API_TOKEN` override can change access.

## HTML block pattern

Use the CLI's two-step upload and attach flow:

```bash
upload_id=$(
  ntn files create \
    --filename demo.html \
    --content-type text/html \
    --plain < demo.html |
    cut -f1
)

ntn api "v1/blocks/$page_id/children" -X PATCH \
  children[0][type]=embed \
  children[0][embed][type]=file_upload \
  children[0][embed][file_upload][id]="$upload_id"
```

Read the block back and verify the rendered interaction before reporting the
HTML block complete.
