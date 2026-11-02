# Chad's bot setup

> [!NOTE]
> These plugins are preliminary. The names, the split between plugins, and the
> skills in each will change as we learn how the bots use them.

These Cursor plugins organize the skills for my Grok Bot team: the bots that
orchestrate my work, and the Cursor cloud agents they launch to do the coding.
The repository root's `.cursor-plugin/marketplace.json` lists all three, so the
whole repository imports as one team marketplace, named `chads-bot-setup`
(Chad's bot setup).

## Not team tooling

These are my personal bot plugins, not team-approved tooling. Every plugin is
Default Off, so nothing installs for anyone automatically, and the `chadxz-`
prefix on each name marks it as mine. If you're a teammate browsing the team
marketplace, don't install them. They encode my voice, my Linear board habits,
and my bots' routing rules, and they change without notice.

## Which plugin is for whom

| Plugin                   | Install on                              |
| ------------------------ | --------------------------------------- |
| `chadxz-bot-skills`      | Every bot, including team bots in Slack |
| `chadxz-coding-skills`   | Cursor cloud agents that bots launch    |
| `chadxz-personal-skills` | My personal bots only, never team bots  |

`chadxz-bot-skills` holds the orchestration skills every bot shares: tracking
work in Linear, writing in my voice, shepherding pull requests, routing PR
review requests to Slack, choosing Notion tools, and the checklist every brief
to a cloud agent has to carry. Team bots in Slack can only see plugin skills and
their own team skills, so anything they need has to live here.

`chadxz-coding-skills` holds the skills cloud agents use while coding: creating
commits and creating pull requests. Cloud agents install team marketplace
plugins when they start, so these are written for cloud VMs. The parts that only
work on my Mac are conditional.

`chadxz-personal-skills` holds skills that only make sense for my personal bots:
building complex features, enriching idea cards, briefing engineering
leadership, reporting work activity, creating DATABASICS expense reports, and
running bot retrospectives. Add it only to personal bots.

## Importing the marketplace

1. In the Cursor dashboard, open **Plugins & MCPs**.
2. Under **Team Marketplaces**, click **Add Marketplace**, choose **Import from
   Repo**, and paste `https://github.com/chadxz/prompts`.
3. Review the three plugins and add them with **Add to Marketplace**.
4. Set each plugin's installation mode to **Default Off**. Bots get plugins
   added one at a time, so nothing should install automatically. The mode is a
   dashboard setting; `marketplace.json` has no field for it.
5. Under **Marketplace Settings**, set **Marketplace Access**, turn on **Enable
   Auto Refresh**, and save. Auto Refresh needs the Cursor GitHub App installed
   on this repository. It re-indexes the tracked branch at most once every 10
   minutes after a push.

A running cloud agent keeps the plugin versions it started with. Start a new
agent to pick up an update.

## First step: a throwaway test

Before rolling anything out, add `chadxz-bot-skills` to one team bot, Samwise,
and start a Slack turn with it. Confirm the `chadxz-bot-skills` skills show up
in that turn. If they don't, fix the import before adding plugins to any other
bot.

## Changing a plugin skill

Bots can't edit plugin skills. To change one, open a pull request against this
repository. After it merges, Auto Refresh picks up the change, and bots and
cloud agents get it on their next start.

Before opening the pull request, run Cursor's plugin template validator from the
repository root:

```bash
curl -fsSL -o /tmp/validate-template.mjs \
  https://raw.githubusercontent.com/cursor/plugin-template/main/scripts/validate-template.mjs
node /tmp/validate-template.mjs
```

Every `SKILL.md` needs YAML frontmatter with a `name` equal to its folder name
and a `description`. The description decides when an agent loads the skill, so
keep it specific about when to use it.
