# First stage, second attempt: results

Run on 2026-11-24 under `2026-11-24-retrieval-protocol.md` (`5b89f99`,
committed before any synthetic request or new embedding existed). By the rule
nothing was adopted and no test set was used.

Dev set as before: 178 matching and 64 no-match requests at 350 skills. The
decision is the shipped one in every row: `jev` yes/no at least 0.9, one skill.

| Condition | Embedder | Synthetic requests | Right skill in top 16 (en / ko) | Useful (en / ko) | Junk, matching | Junk, no-match | Index time |
|---|---|---|---:|---:|---:|---:|---:|
| E0 | e5-base | none (shipped) | 0.787 (0.841 / 0.733) | 0.674 (0.727 / 0.622) | 0.034 | 0.094 | 6.0 s |
| E1 | e5-base | from descriptions | 0.820 (0.830 / 0.811) | 0.708 (0.750 / 0.667) | 0.028 | 0.094 | 12.8 s |
| E2 | e5-base | from bodies | 0.916 (0.898 / 0.933) | 0.697 (0.739 / 0.656) | 0.039 | 0.125 | 12.3 s |
| B0 | bge-m3 | none | 0.792 (0.841 / 0.744) | 0.685 (0.716 / 0.656) | 0.034 | 0.094 | 7.7 s |
| B1 | bge-m3 | from descriptions | 0.860 (0.886 / 0.833) | 0.730 (0.784 / 0.678) | 0.034 | 0.141 | 24.1 s |
| B2 | bge-m3 | from bodies | 0.916 (0.898 / 0.933) | 0.713 (0.739 / 0.689) | 0.039 | 0.109 | 25.1 s |

E0 reproduces the product's shortlist recall exactly (0.787), so the
experiment's retrieval matches the shipped path.

## Reading it

- **Nothing meets the rule.** B1 gains 5.6 points of useful rate but returns a
  non-fitting skill for 14.1% of no-match requests, over the 10% limit. E1
  stays within the junk limits and gains 3.4 points, under the five-point bar.
  E2 and B2 exceed the no-match limit.
- **The embedder alone does almost nothing.** bge-m3 without synthetic
  requests: recall 0.792 against 0.787, useful 0.685 against 0.674. The
  Korean-to-English gap reported for e5-base in passage retrieval does not show
  up on skill descriptions.
- **Synthetic requests fix recall, especially Korean.** Description-based ones
  lift Korean top-16 recall from 0.733 to 0.811 with the same embedder;
  body-based ones lift overall recall to 0.916. The body-based figure is the
  upper bound declared in the protocol, since dev requests were also written
  from bodies.
- **Most of the recovered recall does not survive the decision.** E2 puts the
  right skill in the shortlist for 13 more points of requests than E0 and
  returns a useful skill for 2 more. The judge rates many of the recovered
  skills under 0.9, and better retrieval also surfaces more near-miss siblings
  for no-match requests. This is the same limit the decision experiments ran
  into, seen from the other side.

## E1, for the record

E1 is the one condition that improves something without making anything worse:
no new model, only descriptions sent to the generator, junk rates unchanged or
lower, useful rate up 3.4 points (6 requests of 178), Korean up 4.5 points. It
does not meet the adoption bar set in advance, and a difference of 6 requests
is within what 178 requests can resolve only weakly. It is not shipped. It is
the first thing to re-test if a larger dev set becomes available.

## Costs

- `bge-m3`: 4.3 GB on disk as downloaded by sentence-transformers. Index time
  for 350 skills 7.7 s against 6.0 s; with ten synthetic vectors per skill
  about 25 s against 12.5 s.
- Synthetic requests: one generation call per skill, done once. For 350
  skills the description variant took about 77,000 input tokens and the body
  variant about 600,000.
- New yes/no judgments for this experiment: 4,787 pairs, 1.03 M `jev` input
  tokens.

## Limits

One dev set, used many times now for decisions that all concern the same 242
requests; small gains on it should be read with that in mind. Synthetic
requests were stored as query-side vectors and appended to the BM25 text; other
ways of using them were not tried. Only ten per skill, one generator.
