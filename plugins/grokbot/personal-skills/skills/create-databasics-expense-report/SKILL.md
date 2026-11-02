---
name: create-databasics-expense-report
description: >-
  Use when creating or filling a Convergint DATABASICS expense report on
  data-basics.com, including cover page, line items, and receipt attachments.
---

# Create and populate a DATABASICS expense report

Assumes Chrome on this computer can reach Convergint DATABASICS. Never type
passwords, anti-spam codes, or Authenticator numbers from memory; use the secure
sign-in handoff.

## Inputs

- `{purpose}` — Report Purpose / title (example: `CDC Visit`)
- `{region}` — Region lookup; default `United States of America (US)`
- `{expenses}` — List of line items. Each item needs: date, amount (USD),
  merchant/description, business purpose, category hint, optional attendees, and
  a local receipt file path when available.
- `{submit}` — Whether to submit when done. Default: **do not submit**; leave as
  draft for review.

## Part A — Create the report (if none is open)

1. Open Chrome and go to `https://data-basics.com/` (redirects to login).
2. Sign in with the Convergint email. Complete anti-spam and Microsoft SSO /
   Authenticator via secure handoff.
3. On the dashboard, under **Expense**, click **Create New Report**.
4. Cover page: set **Purpose** to `{purpose}`, **Region** to `{region}`, then
   click **CREATE REPORT**.
5. Confirm the empty expense workspace opens (`+ ADD AN EXPENSE`, total
   `$0.00`).

## Part B — Add each expense line

For every item in `{expenses}`:

1. Click **+ ADD AN EXPENSE**, or select the category from the left category
   list.
2. Use these Convergint DATABASICS categories (learned from a Chicago trip run):
   - Airfare → **Airfare**
   - Hotel out-of-pocket → **HOTEL OUT-OF-POCKET** (opens a per-item wizard; one
     Hotel item for the folio total is fine)
   - Uber / taxi / rideshare → **Taxi / Trains** (there is no Uber category)
   - Meals → **Meals**; put attendees and business purpose in the **Note** field
     when no dedicated attendees field fits
3. Payment type default is **Out-of-Pocket** unless told otherwise.
4. Fill date, amount, merchant/description, and notes from the expense item.
5. Attach the receipt file when the form allows. In the receipt repository,
   deselect any unrelated files already sitting there before saving.
6. Save the line and continue until every item is added.

## Part C — Finish

1. Verify the report total matches the sum of `{expenses}` (or note form-forced
   differences).
2. If `{submit}` is false (default): leave the draft open, or use **SAVE AS
   DRAFT & EXIT**. **Never click SUBMIT** unless explicitly asked.
3. If `{submit}` is true: confirm once more in chat before submitting.

## Report back

- Report ID / title
- Each line: category used, date, amount, receipt attached yes/no
- Final total on screen vs expected sum
- Any skipped lines, unrelated receipt-repo files, or missing required fields
- Confirm draft vs submitted
