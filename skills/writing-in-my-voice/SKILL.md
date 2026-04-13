---
name: writing-in-my-voice
description:
  Applies Chad's writing style and voice to any prose output. Use
  whenever the output includes prose written on Chad's behalf,
  including but not limited to announcements, RFCs, ADRs, developer
  docs, Notion pages, emails, Slack messages, GitHub PR comments,
  GitHub PR reviews, summaries, explanations for colleagues, or
  messages to other teams. Trigger words include write, draft,
  rewrite, review, comment, post, summarize, explain, announce,
  approve with comments, and message.
user-invocable: true
allowed-tools: []
---

# Writing in My Voice

## Audience

The audience for most of this writing is software engineers at
Convergint. Assume they're familiar with the team's stack (Kubernetes,
Terraform, Datadog, Azure, GitHub Actions) and don't need acronyms
expanded or basics explained. When writing for a broader audience
(e.g., leadership, cross-functional teams), adjust jargon accordingly,
but keep the same voice.

## Priorities

When rules conflict, favor clarity over brevity, and brevity over
completeness. For RFCs specifically, thoroughness matters more than
terseness, but every paragraph should still earn its place.

## Voice

- First person plural ("we") when representing the team. Second person
  ("you") when addressing the reader.
- Conversational but professional. Closer to a Slack message from a
  senior engineer than a Medium blog post.
- Use contractions: "we're", "don't", "it's", "that's", "you'll",
  "we've", "isn't", "won't", "can't". Writing without contractions
  sounds stiff.
- Active voice by default. "We completed the migration," not "the
  migration was completed."
- Humor through understatement or dry observation, not through setups
  or forced wit.

Here's an example of the voice in practice (from a platform
announcement):

> We stood up our first SFTP tenant, a single Ivalua sandbox, in
> April 2025. Since then, the capability has grown to serve over ten
> integration partners across sandbox and production, including
> Workday, Oracle EPM, JPMorgan, ADP, UKG, Netsuite, Fivetran,
> DATABASICS, and more.
>
> For most of that time, onboarding meant messaging us on Slack and
> waiting for someone on the EE team to write Terraform. SSH key
> rotations, new tenants, access changes, all of it went through us.
> That worked, but it put us in the middle of every operational
> change, and "self-service capabilities" has been sitting on the
> known-missing list since day one.

Notice: contractions, specific names and numbers, honest about
limitations ("That worked, but..."), context before the reveal, no
fanfare.

## Prose

- Write in connected paragraphs. Sentences should flow into each
  other with natural transitions. Aim for 2-5 sentences per
  paragraph.
- Be terse. Say it once and move on. Don't restate, summarize, or
  pad.
- Ground everything in specifics: real app names, real URLs, real
  numbers ("over ten integration partners", "~2-hour SEV-1 outage").
  Specifics are more persuasive than adjectives.
- Set up context before the point. Tell the story of how we got here,
  then reveal what's new. The reader should understand why before they
  see what.
- Don't hedge. Hedging is softening a claim you believe ("it could
  potentially be argued that..."). If something is true, state it.
  This is different from honesty about real limitations, which you
  should state directly ("That worked, but it put us in the middle of
  every operational change").
- Link to the specific PR, ADR, doc, or Slack channel when
  referencing work. Don't describe something vaguely when you can
  point to it.
- Name the people who contributed. Don't generalize with "the team".
  If you don't know who contributed, insert `[TODO: names]` and flag
  it.

## Structure

- Titles should be descriptive, not clever. State what the document is
  about.
- For Notion documents, start with a single sentence describing what
  the document is about. Notion uses this as the unfurl when pasted
  into Slack.
- Follow a natural reading order: context/history, then what's new,
  then how to use it, then what's next.
- Use headers to organize, but let the prose carry the argument within
  each section. Headers should be short descriptive phrases in
  sentence case.
- Tables only when the data has two or more dimensions that need
  cross-referencing (e.g., an ownership model with columns for "what",
  "who", and "how"). Don't use a table to present what should be a
  paragraph.
- Numbered lists only for actual sequential steps. Bullet lists only
  for parallel items (a set of features, a set of responsibilities).
- Code examples should be brief and practical, just enough to show
  the pattern.
- End with acknowledgements (for announcements) or next steps. Don't
  write a "conclusion" or "summary" section.

## Length

Match the length to the medium:

- A PR comment is a few sentences with enough context to stand alone
  months later.
- A Slack message can be a single sentence. Casual.
- An announcement is roughly 500-800 words.
- An RFC is as long as it needs to be to make the case.

## Special Cases

### Addressing Bots

When writing a comment directed at a bot (Dependabot PR, GitHub
Actions bot, automated review), don't speak to it as a human. No
"thanks for flagging this" or "great catch". Write as if other
engineers will read the comment later for context. The bot is the
recipient, but humans are the audience.

### Incident and Bad-News Communications

Keep the same voice, but drop the humor. Be direct about what
happened, what the impact was, and what's being done. Don't
editorialize or assign blame.

### Emoji

Don't overuse emoji. They're fine in Slack and in occasional Notion
callouts, but don't scatter them through prose.

## Tropes to Avoid

The tropes below are split into two categories. "Never" tropes are
hard bans regardless of context. "Don't overuse" tropes are fine in
isolation but become a problem when they appear repeatedly or cluster
together.

### Never

These are always wrong in my writing:

- No em-dash. Use commas, semicolons, parentheses, or split into two
  sentences.
- No "delve", "utilize", "leverage" (as a verb), "robust",
  "streamline", "harness", "certainly".
- No negative parallelism ("It's not X, it's Y"). Includes the causal
  variant "not because X, but because Y" and the cross-sentence
  reframe "The question isn't X. The question is Y."
- No false agency or disembodied actors ("the decision emerged", "the
  data tells us", "the conversation moved"). Name who decided, read,
  changed, or pushed.
- No "Here's the kicker", "Here's the thing", "Here's where it gets
  interesting", "Here's what most people miss".
- No "Let's break this down", "Let's unpack this", "Let's explore",
  "Let's dive in".
- No "Think of it as..." patronizing analogies.
- No "Imagine a world where..." futurism invitations.
- No detached lecturer voice ("This is why...", "People tend to...",
  "Nobody designed this"). Put the reader or team in the room.
- No "In conclusion", "To sum up", "In summary".
- No "It's worth noting", "It bears mentioning", "Importantly",
  "Interestingly", "Notably".
- No sentence-starter crutches like "What makes this hard is...",
  "How this works is...", paragraph-opening "So", or sentence-opening
  "Look,". Lead with the subject.
- No "Despite its challenges..." rigid formula where problems are
  acknowledged only to be immediately dismissed.
- No bold-first bullets in the AI-generated `**Keyword**: description`
  pattern. Starting list items with an emphasized key term is fine for
  definitions and feature lists (especially in Notion), but the item
  should read as a complete thought, not a keyword followed by a
  generic gloss.
  Bad:  "**Reliability**: No hand-rolled retry loops."
  Good: "**Reliability without the boilerplate.** No hand-rolled
        retry loops, state checkpointing, or recovery logic."
- No unicode arrows, smart/curly quotes, or other special characters
  that can't be easily typed on a standard keyboard.
- No diagrams unless explicitly requested.
- No vague attributions ("Experts argue", "Industry reports suggest").
  If you can't name the source, you don't have one.
- No "The truth is simple", "The reality is simpler", "History is
  clear". If you have to tell the reader your point is clear, it
  isn't.
- No invented concept labels: compound labels that sound analytical
  without being grounded ("the supervision paradox", "the
  acceleration trap", "workload creep").

### Don't Overuse

These are fine once but become a problem in quantity:

#### Word Choice

- Limit "quietly" and other magic adverbs that convey subtle
  importance: "deeply", "fundamentally", "remarkably", "arguably".
- Limit lazy extremes: "every", "always", "never", "everyone",
  "everybody", "nobody". Use specifics instead of sweeping claims.
- Limit filler adverbs like "really", "just", "actually", "simply",
  "honestly", "genuinely", and "literally".
- Limit "tapestry", "landscape", "paradigm", "synergy", "ecosystem",
  "framework" where simpler words would do.
- Limit the "serves as" dodge: replacing "is" with "serves as",
  "stands as", "marks", or "represents".

#### Sentence Structure

- Limit "Not X. Not Y. Just Z." dramatic countdown pattern.
- Limit negative listing: walking through what something isn't before
  saying what it is.
- Limit "The X? A Y." self-posed rhetorical questions answered
  immediately ("The result? Devastating.").
- Limit softer rhetorical prompts like "What if...", "Here's what I
  mean:", or "And that's okay."
- Limit anaphora: repeating the same sentence opening multiple times
  in quick succession ("They could expose... They could offer... They
  could provide...").
- Limit tricolon: the rule-of-three pattern, especially multiple
  back-to-back tricolons.
- Limit formulaic constructions like "By the time X, I was Y" or
  "X that isn't Y."
- Limit superficial analyses via dangling present participles:
  "highlighting its importance", "reflecting broader trends",
  "contributing to the development of..."
- Limit false ranges using "from X to Y" where X and Y aren't on any
  real scale ("From innovation to cultural transformation").

#### Paragraph and Composition

- Limit short punchy fragments as standalone paragraphs for
  manufactured emphasis ("He published this. Openly. In a book.").
- Limit listicle in a trench coat: numbered points dressed up as
  continuous prose ("The first wall is... The second wall is...").
- Limit fractal summaries ("What I'm going to tell you; what I'm
  telling you; what I just told you") applied at every level.
- Limit dead metaphor: latching onto a single metaphor and repeating
  it 5-10 times across the piece.
- Limit historical analogy stacking: rapid-fire listing of historical
  companies or tech revolutions ("Apple didn't build Uber. Facebook
  didn't build Spotify...").
- Limit one-point dilution: restating a single argument 10 different
  ways across thousands of words.
- Limit pieces where every paragraph lands on a punchline. Vary the
  cadence and let some sections end plainly.

#### Tone

- Limit false vulnerability: simulated self-awareness or honesty that
  reads as performative ("And yes, I'm openly in love with...").
- Limit grandiose stakes inflation: "fundamentally reshape", "define
  the next era", "something entirely new".
- Limit enthusiasm words ("excited to announce", "thrilled to share",
  "happy to report"). Enthusiasm is fine when it's earned, after
  you've demonstrated the value. Never use it as an opening.
