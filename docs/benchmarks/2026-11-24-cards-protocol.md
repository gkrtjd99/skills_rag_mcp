# Skill cards: selection protocol (fixed before any card existed)

Written and committed on 2026-11-24 before a card was generated or a judge
asked about one. It extends `2026-11-24-precision-protocol.md`.

## Why

On the dev set the judge gave the expected skill at least 0.9 only 69% of the
time, and 27% of expected skills sit between 0.5 and 0.9 together with 78% of
the best non-fitting skills. The judge sees a skill's frontmatter description
and nothing else, and community descriptions are short and vague. A card that
says when the skill is and is not for might separate the two groups.

## Card

One card per skill, generated once from the skill's description and body (cut
to 8,000 characters) by `gpt-6.1-terra`, a different model from the query
generator. Developer message, verbatim:

> You are writing a card that helps decide whether an agent skill is the right
> one to load for a user's request. Read the skill and return JSON with:
> use_when: up to 3 short clauses naming the concrete tasks the skill is for;
> not_for: up to 2 short clauses naming nearby tasks, products, or situations
> it is not for, mentioning what to use instead only if the skill says so;
> terms: up to 8 product, tool, or file-format names the skill is about, as
> written in the skill. State only what the skill text supports. Keep the
> whole card under 60 words.

The card text shown to the judge is
`Use when: a; b; c. Not for: x; y. Terms: t1, t2, ...`.

## Dev comparison

Same dev set, corpus, judge, shortlists, and adjudicator as the precision
protocol: 178 matching and 64 no-match dev requests at 350 skills, `jev`,
the recorded local and scan shortlists. Only the text in the fit question
changes:

1. description (already recorded; the shipped behavior),
2. card,
3. description followed by the card.

For each evidence variant the decision-rule grid of the precision protocol is
scored without verification: shortlist source, threshold, margin, and one
returned skill.

## Selection and adoption

The precision rule picks one configuration per evidence variant: junk at most
10% on no-match and 5% on matching requests, then the highest useful rate,
ties broken by fewest returned skills, requests, tokens.

Cards are adopted only if the best card configuration beats the best
description-only configuration by at least five points of useful rate on dev.
Otherwise nothing ships and the result is reported as negative.

## Fresh test, only if adopted

Built after the configuration is committed: 50 targets from the corpus members
that were never a target (first test set, dev, or second test set) and 50
no-match skills from skills.sh candidates never used before, with the same
generator and rules. Arms on the 350-skill corpus, one run: `gate`, `jev`
shipped without cards, `jev` with the selected card configuration.

## Limits known in advance

- Test and dev requests were written from skill bodies. A card is also written
  from the body, so it may agree with these requests more than with real ones;
  the card model differs from the request model to reduce shared phrasing, not
  to remove this.
- Building a card sends the skill's body to the card model's provider. That is
  acceptable for the public skills of this benchmark. In the product it would
  have to be an explicit command, never part of sync.
