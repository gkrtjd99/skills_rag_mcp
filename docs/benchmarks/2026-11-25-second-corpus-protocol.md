# The shipped default on a second corpus: protocol (fixed before any skill of the new corpus was downloaded)

Written and committed on 2026-11-25 before a skill of the new corpus was
fetched or a request written. `jev` only.

## Why

Every decision so far (threshold, shortlist of 16, floor 0.5, at most 8
candidates) was taken on one pool of 350 skills. The test sets were new
requests, but on the same skills. `2026-11-25-candidates-results.md` reports
91.1% useful loads and 9.4% wrong loads on no-match requests for the shipped
default, against 94.8% / 54.2% for every description in context. This run
asks whether those numbers are a property of that pool.

Nothing is selected here. The shipped configuration is run once.

## Corpus B

- Candidates: `https://skills.sh/api/skills/all-time/<page>` for pages 3 to
  12 on 2026-11-25 (ranks 601 to 2,600 by installs; pages 0 to 2 are the 600
  entries the first snapshot already covered), in page order, saved as
  `bench/scale2/candidates.json`. Dropped before saving: entries listed in
  `bench/scale/candidates-2026-11-24.json` or `candidates-2026-11-25.json`,
  and entries from any repository that has a skill in the first pool
  (`bench/scale/manifest.json`) or that supplied a no-match request to any
  earlier set. Corpus B therefore shares no repository with anything used so
  far.
- Acceptance: the rules of `2026-11-24-scale-protocol.md` unchanged (GitHub
  source, `SKILL.md` found at the repository's HEAD, parser accepts it,
  description of at least 40 and body of at least 200 characters, skill id
  and frontmatter name not yet accepted, at most 20 skills per repository).
  Also dropped: a skill whose frontmatter name is in the first pool or was a
  no-match source before.
- Split, seed 20261201: the accepted skills are shuffled; the first 350 are
  the corpus, the first 50 of those are targets, the next 50 after the corpus
  are no-match sources and never enter the corpus.
- If fewer than 400 are accepted, further pages (13, 14, ...) are added one
  at a time until 400 are. If the listing cannot supply 350, the run stops
  and that is reported.

What was seen before this was written: the number of entries per listing page
and per repository. No skill text.

## Requests

Generator, prompt, and name rule as in every earlier set: two requests per
language for each target (200), one per language for each no-match source
(100), minus any dropped by the name rule.

## What is run

`bench/scale2.py` points the existing scripts at `bench/scale2/` and
`var/bench/scale2/`; the recording, the simulated agent, its messages, and
the adjudicator are those of `2026-11-25-candidates-protocol.md`.

- **C:scan:8:0.5**: the shipped default with a judge.
- **L**: the earlier default (one skill; local shortlist, uncertain band).
- **ALL**: every description of corpus B in the agent's context.

Primary agent `gpt-6.1-terra` on all three; confirmation agent `gpt-6-astra`
on C:scan:8:0.5. Each once.

## Reading the result, fixed in advance

The first corpus gave, on `test4`, C 91.1% useful / 9.4% junk on no-match,
L 74.9% / 0.0%, ALL 94.8% / 54.2%. With the primary agent on corpus B:

- **Holds**: C useful at least 86.1% (within five points), C junk on no-match
  at most 13% (the limit plus three points), and C junk on no-match below
  half of ALL's.
- **Partly holds**: C useful is above L's by at least five points and C junk
  on no-match is below ALL's, but one of the conditions above fails.
- **Does not hold**: anything else.

Whatever the outcome, the README states both corpora's numbers. No setting
is changed on the basis of this run; a change would need new dev data.

## Limits known in advance

Corpus B is one more pool from the same listing site, at lower install ranks,
so its skills may be less polished and its descriptions shorter; a difference
may come from that and not from overfitting. The requests are written by the
same generator and the agents and adjudicator are the same models as before,
so this run says nothing about those three. About 200 matching and 100
no-match requests: three points either way is within noise.
