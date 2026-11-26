# ADR sources

What the standard ADR guidance agrees on, and where it differs. Read this when
someone asks why the `writing-adrs` skill says what it says.

## Where the sources agree

- **Short.** Nygard asks for one or two pages. Azure says to keep records
  "pithy, assertive, on-topic, and factual." Zimmermann lists "Mega-ADR" and
  "Novel and epic" as anti-patterns and calls ADRs an executive summary.
- **One decision per record.** Nygard: "a set of forces and a single decision."
  Henderson's "Specific" criterion says the same. Azure and Zimmermann both say
  to split a phased decision into one record per phase.
- **The why, not the how.** AWS calls the focus on "the reason for the decision
  rather than how the team implemented it" one of the format's most useful
  traits. Azure says, "Avoid making decision records design guides," and to link
  supporting material while keeping the decision clear without it. Zimmermann's
  remedy for "Blueprint or Policy in Disguise" is to move detail design to a
  separate document.
- **Accepted records don't change; new ones supersede them.** Nygard marks
  reversed decisions superseded and keeps them. AWS treats accepted ADRs as
  immutable and requires a new ADR to change one. Azure calls the log
  append-only: "Don't go back and edit accepted records."
- **Context, decision, consequences at minimum,** with honest trade-offs. AWS
  names those three as the minimum. Nygard wants every consequence, not only the
  positive ones. Zimmermann flags "Free Lunch Coupon" (no downsides) and "Dummy
  Alternative" (an option nobody would pick) as anti-patterns.
- **Lightweight and kept with the code.** ThoughtWorks put lightweight ADRs at
  Adopt on its Technology Radar and recommends source control so the records
  stay in sync with the code.

## Where they differ

- **Amending in place.** Henderson allows amending an ADR by adding new
  information, and Google Cloud suggests revisiting an ADR with the previous
  decision and the reason for the change. Nygard, AWS, and Azure don't, and we
  follow them: a new ADR supersedes or amends, and the old one only gets a
  status link.
- **Title form.** Nygard uses short noun phrases. ee-monorepo titles each ADR as
  an action, and the skill follows the repo.
- **Attribution.** MADR, AWS, and Google Cloud record decision makers or
  stakeholders. ee-monorepo's README forbids attribution because the pull
  request's review history shows who approved it, and the skill follows the
  repo.

## Links

- Michael Nygard,
  [Documenting Architecture Decisions](https://www.cognitect.com/blog/2011/11/15/documenting-architecture-decisions)
  (2011)
- [MADR](https://adr.github.io/madr/) and the
  [ADR GitHub organization](https://adr.github.io/)
- AWS Prescriptive Guidance,
  [ADR process](https://docs.aws.amazon.com/prescriptive-guidance/latest/architectural-decision-records/adr-process.html)
- Microsoft Azure Well-Architected Framework,
  [Maintain an architecture decision record](https://learn.microsoft.com/en-us/azure/well-architected/architect-role/architecture-decision-record)
- Google Cloud,
  [Architecture decision records overview](https://cloud.google.com/architecture/architecture-decision-records)
- ThoughtWorks Technology Radar,
  [Lightweight Architecture Decision Records](https://www.thoughtworks.com/radar/techniques/lightweight-architecture-decision-records)
- Joel Parker Henderson,
  [architecture-decision-record](https://github.com/joelparkerhenderson/architecture-decision-record)
- Olaf Zimmermann,
  [How to create ADRs, and how not to](https://www.ozimmer.ch/practices/2023/04/03/ADRCreation.html),
  [How to review ADRs, and how not to](https://www.ozimmer.ch/practices/2023/04/05/ADRReview.html),
  and
  [A definition of done for architectural decisions](https://www.ozimmer.ch/practices/2020/05/22/ADDefinitionOfDone.html)
