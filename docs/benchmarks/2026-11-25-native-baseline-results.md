# Baseline: every description in context, no search: results

Protocol: `2026-11-25-native-baseline-protocol.md`, committed as `15fe081`
before the baseline was run. Script: `bench/scale/native_baseline.py`.

## Result

Putting all 350 descriptions in the agent's context and letting it pick loads
a useful skill far more often than search does, and loads a wrong skill far
more often when nothing matches. Search is not "the same accuracy for less
context". It is a different trade.

Test set (`test3` and `test3neg`: 194 matching, 97 no-match requests), primary
agent `gpt-6.1-terra`. Search rows are the recorded results on the same
requests (`2026-11-25-agent2-results.md`).

| | Useful loads | Wrong loads, matching | Wrong loads, no-match | English | Korean | Skill metadata in context |
|---|---|---|---|---|---|---|
| Search, `jev` (shipped default) | 67.0% | 2.1% | 8.2% (8) | 70.8% | 63.3% | about 110 characters per search |
| Search, no judge (gate result) | 69.6% | 4.1% | 14.4% (14) | 79.2% | 60.2% | about 1,210 characters per search |
| **All descriptions, no search** | 93.8% | 3.6% | 34.0% (33) | 95.8% | 91.8% | about 33,750 tokens, always |
| All descriptions cut to 120 characters | 91.8% | 5.2% | 40.2% (39) | 91.7% | 91.8% | about 11,600 tokens, always |

Confirmation agent `gpt-6-astra`, all descriptions: 97.4% useful, 1.5% and
29.9% (29) wrong loads.

`dev3` (184 matching, 96 no-match), primary agent; search rows from
`2026-11-25-scan-results.md`:

| | Useful loads | Wrong loads, matching | Wrong loads, no-match | Korean |
|---|---|---|---|---|
| Search, `jev` (shipped default) | 77.2% | 4.3% | 1.0% (1) | 71.0% |
| Search, `jev` with the whole-corpus scan | 82.1% | 4.3% | 4.2% (4) | 80.6% |
| All descriptions, no search | 97.3% | 2.2% | 36.5% (35) | 95.7% |

## Reading it by the rule fixed in advance

The protocol named three readings. None fits cleanly, and that is itself the
finding: the first requires a useful rate at least five points higher with
junk on no-match within three points of the shipped default's. The useful
rate is 26.8 points higher; junk on no-match is 25.8 points higher. Both
differences are far outside the tolerances, in opposite directions. The
READMEs therefore state both numbers and call it a trade, which is the
disclosure the first reading demanded and more.

## What the numbers say

- With every description in view the agent finds the right skill for 94 to
  97% of matching requests. Search with a judge finds it for 67 to 82%. The
  misses of search are losses of the pipeline (shortlist and threshold), not
  of the descriptions.
- With every description in view the agent also loads a skill that does not
  fit for about a third of requests that have no matching skill. These
  requests come from skills outside the corpus, often siblings of skills
  inside it, so a plausible-looking neighbour is always in the list. Search
  shows the agent at most one candidate and holds wrong loads to 1 to 8%.
- Counting all 291 test requests: all-descriptions makes 222 loads of which
  182 are useful (82%); search with `jev` makes 142 loads of which 130 are
  useful (92%).
- The Korean gap is a property of search. With all descriptions English and
  Korean requests score alike (95.8% and 91.8%).
- Cutting descriptions to 120 characters costs two points of useful loads and
  a third of the tokens (11,600 against 33,750).
- Context: the full list is about 33,750 tokens in every session whether or
  not a skill is needed (nearly all of it cacheable by the provider). Search
  adds about 30 tokens of metadata per search.

## What this means for the project

At 350 skills search saves about 34,000 tokens of standing context and avoids
most wrong loads, and pays for it with a quarter of the right ones. Whether
that is worth it depends on how often a session's request has a matching
skill at all, and on how much a missed skill costs compared with a wrong one.
At a few dozen skills the full list is about 2,000 tokens and search has
little to offer.

The gap also shows where the headroom is: the agent is a better selector than
the judge when it can see the candidates. Showing it more candidates (for
example the 16 the scan finds, at 120 characters each, about 600 tokens)
sits between the two extremes measured here and has not been measured.

## Limits

One corpus size. One model call with nothing else in context stands in for an
agent; in a harness the list sits in a long system prompt next to a task in
progress, the harness may truncate or budget the list, and the agent may load
several skills. The agent models are not the ones in the targeted harnesses.
Requests are model-written and were built for search experiments. The
no-match requests come from skills near the corpus, which may make wrong
loads more likely than in ordinary use, for both approaches. The test-set
requests had been used once before, for a different comparison; nothing was
selected here.

## Cost of the measurement

1,153 agent calls, 32.5 million input tokens, of which 32.3 million were
served from the provider's cache.

## Later

The candidate list suggested above was measured and adopted
(`2026-11-25-candidates-results.md`). On its fresh test set (`test4`: 191
matching, 96 no-match) all descriptions in context scored 94.8% useful, 5.2%
junk on matching, and 54.2% (52) junk on no-match requests.
