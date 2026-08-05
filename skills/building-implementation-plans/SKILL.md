---
name: building-implementation-plans
description:
  Builds and maintains implementation plans from ADRs, RFCs, specifications,
  tickets, and code. Use when asked for an implementation plan, execution plan,
  phased delivery plan, or reviewable change sequence before or during
  implementation.
---

# Building Implementation Plans

These guidelines supplement the normal implementation-planning workflow. They
aren't an exhaustive process or output template.

## Deliver value first

Start with the smallest safe, end-to-end MVP that delivers real value. Sequence
later work as improvements to that working slice so each step adds usable
capability. Include foundation work only when the MVP or a named improvement
requires it.

## Keep the plan current

When implementation, completed work, or a new decision changes the plan, update
every part affected by it, including later steps. Remove the superseded decision
and any relics it left behind. If that history matters, move it to a separate
file. Link to it once from the plan for readers who need it.
