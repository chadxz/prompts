---
name: creating-skills
description:
  Creates and updates portable Agent Skills across Codex, Claude, Zed,
  Pi, and other agent runtimes. Use when the user asks to create, improve,
  review, validate, test, or document an agent skill, SKILL.md file,
  skill metadata, bundled scripts, references, assets, or cross-runtime
  skill behavior.
---

# Creating Skills

Create small, reusable skill packages. Treat `SKILL.md` as the portable source
of truth; add platform-specific metadata only when it improves discovery,
invocation, permissions, or user experience.

## Workflow

1. Ground the skill in real usage: existing skills, task traces, docs, issue
   comments, source artifacts, or user corrections.
2. Scope one coherent job. Split unrelated capabilities; skip the skill if
   ordinary instructions or one helper script is enough.
3. Choose the skill name and folder layout before writing. Treat them as part of
   the skill contract, not cleanup work after the instructions are done.
4. Choose resources before writing: `scripts/` for deterministic or fragile
   work, `references/` for details loaded on demand, and `assets/` for templates
   or files used in outputs.
5. Scaffold or edit the skill folder. Use tools such as the Codex
   `$skill-creator` skill or Zed `create-skill` when helpful, then verify their
   output.
6. Write metadata, instructions, and optional resources. Add platform-specific
   files only when they add value.
7. Validate and forward-test when the skill controls a workflow, external
   system, generated artifact, or cross-runtime behavior.

## Portable Baseline

- Use a directory containing `SKILL.md` as the canonical package format.
- Choose the skill name deliberately. Prefer a short, verb-led, task-shaped name
  over shorthand, implementation details, or broad noun labels.
- Keep the folder name and frontmatter `name` identical. Use lowercase letters,
  digits, and hyphens only; avoid leading, trailing, or repeated hyphens and
  reserved words for target runtimes, such as `anthropic` or `claude`.
- Prefer each skill as a direct child of the skills root. Nested discovery and
  name-collision behavior vary across runtimes.
- Keep the package structure simple and predictable: `SKILL.md` at the package
  root, with only direct child `agents/`, `scripts/`, `references/`, and
  `assets/` directories when they are useful.
- Include `name` and `description` in YAML frontmatter. Keep `description` under
  1024 characters, third person, specific, and front-loaded with trigger words;
  some runtimes shorten long descriptions in large catalogs.
- Use optional frontmatter sparingly: `license` for redistribution,
  `compatibility` for non-obvious requirements, `metadata` for stable custom
  fields, and `allowed-tools` only when the target runtime supports it.
- Keep `SKILL.md` under roughly 500 lines. Move details to direct child
  reference files, and say when to read or run each resource.
- Prefer relative paths. Do not rely on one platform-specific environment
  variable unless the skill is intentionally tied to that platform.
- Avoid auxiliary files such as README, installation guide, quick reference, or
  changelog unless the user explicitly asks for them.
- Audit bundled scripts, external URLs, package installation, filesystem access,
  and network calls before trusting or distributing a skill.

## Writing Rules

- Assume the agent is capable. Add what it would otherwise miss: project
  conventions, fragile sequences, edge cases, preferred tools, exact output
  shapes, validation commands, and recurring user corrections.
- Favor reusable procedures over one-off answers. A skill should teach an
  approach that generalizes across similar tasks.
- Pick defaults instead of presenting long menus. Mention alternatives only as
  escape hatches.
- Use exact scripts or steps for brittle work and prose guidance for
  judgment-heavy work.
- Put gotchas in `SKILL.md` when the agent must know them early.
- Write imperative steps with explicit inputs and outputs for workflows and
  scripts.
- Keep examples short and realistic. Use templates when output format matters.
- Qualify every cross-skill reference with the word "skill", as in
  "`creating-commits` skill", so readers can distinguish skills from commands,
  packages, and files.
- When updating a skill, preserve the user's existing structure unless it harms
  discovery, portability, or validation.

## Platform Metadata

Start from the Agent Skills baseline. Add these only when relevant:

- `agents/openai.yaml` for Codex UI metadata, tool dependencies, and invocation
  policy. Include `display_name`, `short_description`, and a `default_prompt`
  that mentions `$skill-name`.
- `policy.allow_implicit_invocation: false` in `agents/openai.yaml` when Codex
  should only load the skill through explicit `$skill-name` invocation.
- `disable-model-invocation: true` in frontmatter when a runtime supports it and
  the skill should stay manual, such as dangerous deploy or release workflows.

The core `name`, `description`, body, and bundled resources must still be enough
for another capable agent to use the skill if this metadata is ignored.

## Validation

- Run any validator available in the current environment.
- Verify the folder name, frontmatter `name`, `agents/openai.yaml`
  `$skill-name`, and validation paths all match before calling the skill done.
- For skills created with the Codex system `skill-creator` skill, run:

  ```bash
  validator="${CODEX_HOME:-$HOME/.codex}/skills/.system/skill-creator"
  uv run "$validator/scripts/quick_validate.py" path/to/skill
  ```

- Inspect `agents/openai.yaml` after generation or edits. Ensure the default
  prompt still names the skill with `$skill-name`.
- Test positive and negative prompts against the `description` to confirm the
  right trigger behavior.
- Forward-test with realistic requests. Pass raw artifacts, not the expected
  answer or your diagnosis. Inspect traces when available.
- Test with the runtimes and model families the skill is expected to support.
- Revise when validation shows wasted steps, false triggers, missing context, or
  leaked-context dependence.

## Current References

When exact platform behavior matters, refresh current docs instead of relying on
memory:

- Agent Skills specification: https://agentskills.io/specification
- Agent Skills best practices:
  https://agentskills.io/skill-creation/best-practices
- Claude Agent Skills:
  https://platform.claude.com/docs/en/agents-and-tools/agent-skills/overview
- Claude skill authoring:
  https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices
- Codex Agent Skills: https://developers.openai.com/codex/skills
- Zed Agent Skills: https://zed.dev/docs/ai/skills
- Pi skills docs:
  https://github.com/earendil-works/pi/blob/main/packages/coding-agent/docs/skills.md
