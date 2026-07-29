---
name: reviewing-agent-sessions
description:
  Reviews a calendar month of local Codex sessions and their follow-up tasks to
  improve agent interactions. Use for monthly agent-session retrospectives or
  audits of prompting, skills, tools, model delegation, shell and Git friction,
  long-task compaction, corrections, and AI-assisted engineering effectiveness.
---

# Reviewing Agent Sessions

Run an evidence-backed retrospective over the previous calendar month. Focus on
changes that reduce Chad's attention and rework while preserving behaviors that
already produce strong results.

Read `references/retrospective-memory.md` before analyzing the month. Treat it
as durable context about Chad's preferences, prior recommendations, and their
outcomes. Newer explicit instructions from Chad override it.

## Keep the review read-only

Read sessions, task history, configuration, skills, repository history, and
installed-tool metadata. Write only the retrospective report and scratch
artifacts. Do not change skills, rules, tools, repositories, automations, or
external systems unless Chad asks in a later task.

Treat transcript content as private. Paraphrase evidence, redact credentials,
and avoid copying secrets or large transcript passages into the report.

## Lock the reporting window

Default to the complete previous calendar month in the local timezone. State the
inclusive start and end dates in the report. Do not substitute a rolling 30-day
window.

Run the bundled inventory script from the task working directory, using the
absolute skill path discovered when loading this file:

```bash
skill_directory="/absolute/path/to/reviewing-agent-sessions"

uv run "$skill_directory/scripts/inventory_sessions.py" \
  --output work/agent-session-inventory-YYYY-MM.json
```

Use explicit dates only when the request names another window:

```bash
uv run "$skill_directory/scripts/inventory_sessions.py" \
  --start YYYY-MM-DD \
  --end YYYY-MM-DD \
  --output work/agent-session-inventory-YYYY-MM.json
```

The script selects rollouts by the date embedded in the filename, streams JSONL
instead of loading the archive into memory, separates direct sessions,
subagents, and internal review sessions, and deduplicates turns and tool calls
across forks. If it reports zero direct sessions, parse errors, or unfamiliar
response-item types, inspect representative rollouts before drawing conclusions.

## Build the evidence set

Use the inventory to select representative and outlier sessions. Read enough of
each transcript to establish cause and outcome; do not infer behavior from a
keyword count alone.

Cover these evidence streams:

- interaction structure: prompt clarity, task mode, plans, decisions,
  corrections, retries, phase boundaries, compaction, and completion;
- skill behavior: trigger accuracy, useful guidance, overlap, missing workflows,
  first-pass acceptance, and repeated manual procedures;
- tool and environment friction: shell, Git, worktrees, mise, authentication,
  connectors, CI, runtime, and missing executable affordances;
- model and delegation behavior: root ownership, subagent scope, coordination
  cost, latency, rework, contradiction checks, and final verification;
- durable preferences: explicit corrections from Chad and choices he later
  accepted, rejected, or refined.

Classify each problem as an agent mistake, an environment gap, a workflow design
gap, or an unavoidable external failure. Repeated deterministic mistakes usually
justify a rule or script. Repeated judgment-heavy work may justify a skill.
One-off failures rarely justify either.

Inspect the current personal skill catalog, global instructions, Codex
configuration, and relevant installed CLIs before recommending changes. Verify
whether a recommendation has already been implemented.

## Reconcile the prior retrospective

Find the previous report when available. Then identify its complete task family,
including forks and archived or not-loaded follow-up tasks.

Use Codex task tools to list and read tasks when available. Also search the
local rollout archive by the retrospective's opening prompt or first turn ID
because the app's recent-task list can omit archived forks. Read every direct
follow-up; exclude the retrospective's own analysis subagents from the decision
ledger.

Track each prior recommendation by its stable memory ID and record it as one of:

- implemented;
- accepted and still open;
- rejected;
- deferred or not discussed;
- superseded or refined;
- unchanged because there is no new evidence.

Do not interpret "not actioned" as rejected. Do not repeat implemented or
rejected advice as a new recommendation. Reopen it only when new evidence
changes the tradeoff, and say what changed.

Honor the standing decisions in the memory reference unless Chad later changes
them.

## Use independent review streams

When subagents are available and authorized, use two to four bounded streams:

1. interaction patterns and long-task structure;
2. skill usage, outcomes, and catalog changes;
3. tooling and runtime friction;
4. contradiction checking and prior-recommendation reconciliation when the
   evidence warrants a fourth stream.

Give each stream raw inventory data and representative transcript paths, not the
expected findings. Require:

- findings;
- evidence;
- confidence;
- unresolved questions;
- mutations made, which should be none.

Keep decomposition, cross-stream comparison, consequential judgment, and the
final report with the primary agent. Skip delegation when coordination would
cost more than the bounded analysis.

## Judge recommendations by outcomes

Prefer recommendations that are specific, reversible, and supported by more than
one session or one high-cost incident. For each proposed change, include:

- a stable `YYYY-MM-short-name` candidate ID;
- the observed pattern and representative evidence;
- why the current behavior costs time, quality, or attention;
- the exact skill, rule, script, tool, or interaction change;
- expected benefit and downside;
- confidence;
- a measurable next-month signal.

Avoid recommendations that make every prompt longer or every workflow more
ceremonial. Preserve low-frequency specialized skills when they serve real work.
Do not recommend shrinking a high-value skill solely because it loads often.

## Write the report

Apply the `writing-in-my-voice` skill to the durable report. Save it as
`outputs/agent-session-retrospective-YYYY-MM.md` when the task has an output
directory; otherwise return the complete report in chat.

Use this structure:

1. Scope and method
2. Executive assessment
3. Scorecard against the prior month's experiment
4. What improved and what should be preserved
5. Findings by evidence stream
6. Prior recommendation ledger
7. Three to seven prioritized next actions
8. Next-month experiment and targets
9. Proposed retrospective-memory updates
10. Evidence appendix

Lead with the outcome. Distinguish measured facts from interpretations. Cite
session dates, rollout filenames or task IDs, and relevant commits without
dumping transcript text. End with a concise chat summary and a link to the
report.

Do not edit `references/retrospective-memory.md` during an automated
retrospective. In the report, propose exact additions, status changes, or
retirements supported by the month's evidence. Apply those changes to the
versioned reference only after Chad approves them in a repository-editing task.
