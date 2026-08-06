---
name: reviewing-complex-work
description:
  Allows one self-requested, independent, read-only peer-agent review per
  session for complex completed work through an installed alternate CLI such as
  Claude Code, Codex CLI, or Cursor Agent, then verifies and reconciles the
  findings. Covers writing the review brief, granting read-only investigation
  tools, running the peer detached, and collecting its result from a stream.
  Use automatically before finalizing substantial or high-risk code,
  architecture, infrastructure, migrations, security or authorization,
  concurrency, distributed systems, broad refactors, or long multi-step
  analysis where a second model could catch correctness gaps. Also use for
  explicit peer-review, second-opinion, adversarial-review, or cross-model
  review requests. Skip routine mechanical edits and small low-risk changes.
---

# Reviewing Complex Work

Self-request at most one independent peer review per agent session. Run it after
self-review and primary validation, while there is still time to correct the
work. Reviews explicitly requested by the user are user-directed and do not
count as the agent's self-requested review. Keep final judgment with the primary
agent.

A peer review has four parts, and most failures come from the last two rather
than the first two: decide whether to review, write the brief, invoke the peer,
and collect its result.

## Decide When to Review

Review automatically when there is one high-risk signal or at least two
complexity signals.

High-risk signals include security, privacy, migrations, data loss, irreversible
state, concurrency, distributed behavior, public APIs, schemas, compatibility,
and infrastructure boundaries.

Complexity signals include work spanning components, substantial refactors with
behavior changes, interacting requirements or edge cases, unfamiliar systems,
important behavior that tests cannot cover, and nuanced analysis.

Skip mechanical, low-risk work covered by deterministic checks. Honor a user
request to skip or limit external review.

## Choose the Peer

Start a fresh, non-resumed session in another installed and authenticated agent
CLI. Prefer a different provider:

- Claude Code host: prefer Codex CLI or Cursor Agent.
- Codex host: prefer Claude Code or Cursor Agent.
- Cursor host: prefer the direct CLI from another provider.
- Other hosts: choose the strongest available independent alternative.

Discover the current models rather than preserving model IDs here. Use the
newest permitted flagship or coding model and the highest supported single-agent
thinking level, commonly `max` or `xhigh`. Pin the exact model identifier the
CLI reports; do not pass a short alias that may resolve to a different tier
later. Do not use a mode that adds delegation unless the user asked for a panel.

Never lower the model or thinking level to make a review fit a waiting window.
If reviews are not finishing, fix the waiting mechanism described below. A
faster tier is a last resort after the detached pattern has been tried, and it
must be reported.

Read the matching reference for exact flags, tool grants, and collection
commands:

- `references/claude-code.md`
- `references/codex-cli.md`
- `references/cursor-agent.md`

## Write the Review Brief

Give the peer the task, review scope, repository instructions, raw diff or
artifact, validation output, and relevant surrounding code. Do not include the
primary agent's conclusions or suspected findings.

A brief has three parts. The environment and output sections are fixed
boilerplate; only the review content changes between runs.

### Environment

State the harness, because the peer cannot discover it and will otherwise waste
its budget rediscovering the same walls:

```text
ENVIRONMENT
- Non-interactive session. No human can approve anything, so a blocked action
  stays blocked. Do not retry a blocked command in another form, and do not
  investigate why it was blocked.
- Tools available: <exact list>.
- Readable roots: this worktree and <granted scratch paths>. Do not read
  anything else.
- Budget: about N minutes. At 80% of budget, stop investigating and report what
  you have, marking any area you did not reach as "not reviewed".
- Prefer one shell command per call. Chained commands are harder to admit.
```

Name every readable root, and make sure each one is actually granted. A brief
that points at a path the peer cannot open produces a confident review of the
wrong scope, and says so only in passing. Grant scratch paths with the CLI's
additional-directory flag, then confirm the peer can read them.

Set the budget from the size of the change, not from patience: roughly 15
minutes for a focused diff, 30 for an ordinary complex review, 60 for broad,
high-risk, or context-heavy work.

### Content

- The task intent and what "correct" means for it.
- The exact command that produces the diff under review, such as
  `git diff --find-renames origin/main...HEAD`.
- Which repository instruction files are authoritative.
- Accepted decisions and explicit non-goals, so the peer does not relitigate
  settled design or report known-deferred work.
- Primary validation already run, with results. This is the cheapest single
  addition to a brief: it stops the peer from spending its budget re-running
  suites it cannot complete.
- Prior findings only when the pass is an explicit closure check, and then say
  so. Otherwise the peer anchors on them instead of looking for new problems.

### Output Contract

Ask for a machine-checkable verdict in both the empty and non-empty case. A
contract that only defines "output exactly CLOSED" leaves the interesting case
unspecified, and every run invents a different header:

```text
OUTPUT CONTRACT
- First line, exactly one of:
    VERDICT: CLOSED
    VERDICT: FINDINGS <count>
- Then, per finding: SEVERITY | file:line | failure scenario | fix.
- Severity: BLOCKING = ships broken or unsafe. MAJOR = wrong under a realistic
  input. MINOR = correct but costly later. Report nothing below MINOR.
- For each finding, say how you verified it: read-only inspection, or a command
  you ran, quoted. Do not report anything you could not verify.
- Do not restate work that is already correct.
```

## Grant Read-Only Investigation Tools

Give the peer every useful read capability. A review is only as good as what it
can inspect, and an under-provisioned peer produces confident guesses:

- source, history, documentation, dependency, and read-only shell inspection;
- web search and web fetch, for advisories, upstream behavior, API contracts,
  and version-specific semantics the repository does not contain;
- read-only resources and actions from configured MCP connectors.

Withhold only mutation and delegation:

- no file editing, patching, or writing;
- no commits, pushes, or published comments;
- no subagent spawning, no nested agent CLI, and no invocation of this skill.
  Keep the review one hop deep.

Prefer the CLI's own read-only enforcement over prompt instructions, and prefer
an allowlist over a denylist. Enforcement strength differs by peer and is
described in each reference. Read-only shell still permits a determined write in
some harnesses, so treat the mutation check below as the real guarantee.

## Stage Scratch Files Outside the Worktree

Keep the review's own files out of the repository. Stage the brief, the event
stream, and any process-id file under `~/tmp`, in a run-specific directory:

```bash
review_dir="$HOME/tmp/peer-review-$(date +%Y%m%d-%H%M%S)"
mkdir -p "$review_dir"
```

The worktree is the artifact under review, so writing scratch files into it
corrupts the thing being measured. Untracked review output shows up in
`git status --short`, which is the mutation check below, and a peer that lists
the working tree sees files that are not part of the change.

Grant `~/tmp` to the peer when, and only when, the brief points at something
there, such as a progress ledger, a prior review, or an artifact under review.
The brief text and the stream file do not need a grant on their own: the caller
expands the brief and writes the stream, so both happen outside the peer's
session. Each reference gives the flag, or notes that the peer needs none.

## Run Detached and Collect Once

Do not launch the peer and then block on it. Blocking forces the caller to
choose between waiting blind and killing the run, and callers reliably choose
badly: they interrupt working reviews that had produced nothing yet, because a
silent process and a hung process look identical.

Three rules, which apply to every peer:

1. **Write the event stream to a file and detach.** Redirect the CLI's streaming
   output to a file under `~/tmp` and background the process. The caller keeps
   working instead of spending turns waiting.
2. **Never ingest the raw stream.** A streamed review carries every file the
   peer read and every intermediate step, which is routinely 40 or more times
   the size of the review itself and commonly exceeds a caller's output cap.
   Because the final result is the last event, an overflowing stream truncates
   away exactly the part that was wanted. Project the stream with `jq`; never
   paste it into the caller's context.
3. **Check status before consuming.** Every peer reports whether it finished or
   died. Treat an unfinished run as no review at all: a truncated run ends on
   mid-work narration that reads like a conclusion and will otherwise be
   mistaken for findings.

Do not cap the peer's turns. A turn ceiling truncates mid-investigation and
returns narration; the budget line in the brief is the right lever. Where a
spend cap is used, set it high enough that it is a runaway guard rather than a
stopping condition, and check for it in the status.

When a heartbeat is genuinely needed, this works for every peer without
depending on its event schema:

```bash
stream="$review_dir/review.jsonl"
printf '%s events, last=%s\n' "$(wc -l < "$stream")" \
  "$(tail -1 "$stream" | jq -Rr 'fromjson? // empty | .type // "partial"')"
```

Each reference gives a richer per-agent heartbeat and the exact extraction
command.

## Verify No Mutation

Compare before and after the review:

```bash
git rev-parse HEAD
git status --short
git stash list
```

Treat any unexpected mutation as a failed review. This check is only meaningful
when the review's own scratch files live under `~/tmp`; a stream file written
into the worktree shows up here as an untracked change and masks a real one.

## Reconcile and Report

Verify each finding against the task, source, and runtime behavior. Classify it
as confirmed, rejected with evidence, or unresolved. Fix confirmed in-scope
issues and rerun primary validation. Do not self-request a follow-up peer review
for any reason, including after a consequential fix or when a material finding
remains unresolved. Resolve or report remaining risk using primary-agent
verification.

Report the peer model and thinking level, confirmed findings and fixes, and any
unresolved risks. A clean review is useful evidence, not proof of correctness.

Reviewing the same artifact repeatedly has sharply diminishing returns. When
successive passes stop producing new confirmed findings, stop reviewing and
report the residual risk instead of running another pass.
