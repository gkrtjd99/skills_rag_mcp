# Decision structure: negative result

Run on 2026-11-24 under `2026-11-24-structure-protocol.md` (`48fee12`,
committed before any new signal was collected). Nothing was adopted and no test
set was used.

Dev set as before: 178 matching and 64 no-match requests, 350 skills, the local
shortlist of 16, `jev`, same adjudicator. Limits for a rule to qualify: a
non-fitting first skill for at most 10% of no-match and 5% of matching
requests. Adoption bar: five points of useful rate over the shipped rule.

## Baseline

| Rule | Useful | Junk, matching | Junk, no-match |
|---|---:|---:|---:|
| Shipped: `jev` yes/no at least 0.9 | 0.674 | 0.034 | 0.094 |

## Experiment 2: pick by comparison, decide separately

Best configuration of each pre-registered family within the limits:

| Family | Best configuration | Useful | Junk, matching | Junk, no-match | Against shipped |
|---|---|---:|---:|---:|---:|
| S1 choose, then check the yes/no | Choice 0.5, yes/no 0.9 | 0.612 | 0.011 | 0.062 | -6.2 |
| S2 choose, with an "any fits" question | Choice 0.5, any 0.7 | 0.685 | 0.045 | 0.094 | +1.1 |
| S3 graded score | none qualifies | | | | |
| S4 yes/no 0.9, else rescue by agreement | none qualifies | | | | |

The request-level gate from the vendor's skill cookbook never helped.

Why, from the same records:

- **Picking was not the problem.** Forced to return its top candidate, the
  Choice is useful for 81.5% of matching requests, the yes/no ranking for
  80.9%, and the graded Score for 83.1%. Making candidates compete barely
  changes which one comes first.
- **No signal says "nothing here fits".** The companion question is at least
  0.5 for 87% of matching requests and still for 56% of no-match ones. The
  gate passes 95% of matching and 98% of no-match requests, because every
  request in this benchmark is a real task for some skill. Forced to return
  something, every method hands a non-fitting skill to about 60% of no-match
  requests.

The vendor cookbooks that motivated this decide among options that are all in
the pool. Here the hard case is a request whose right skill is absent while its
siblings are present, and the judge sees only descriptions.

## Experiment 1: reanalysis

**1a. Threshold for `openai`.** None qualifies:

| Threshold | Useful | Junk, matching | Junk, no-match |
|---:|---:|---:|---:|
| 0.5 | 0.831 | 0.112 | 0.391 |
| 0.9 | 0.792 | 0.073 | 0.344 |
| 0.99 | 0.742 | 0.045 | 0.297 |
| 0.999 | 0.685 | 0.039 | 0.219 |

Its probabilities saturate: a wrong sibling is rated above 0.999 for a fifth of
no-match requests. A higher threshold does not make `openai` precise on this
data; the research suggestion that the two judges differ only in where their
cut-off sits is not borne out here.

**1b. Score-list model.** A cross-validated logistic model over six features
of the 16 probabilities qualifies at a useful rate of 0.624, below the shipped
single threshold (0.674). Not adopted.

**1c. Conformal bound.** With 64 no-match dev requests, a 10% guarantee on
no-match junk needs a dev rate of at most 8.6%. The shipped 0.9 (9.4% on dev,
9.3% on the fresh test) does not meet it; 0.95 does, at a useful rate of 0.382.
The shipped setting's junk rate is best described as "about 9%, between 4% and
15%", not as guaranteed under 10%.

## What this means

Four attempts to improve the final decision with the same evidence have now
failed on dev: per-skill cards, a score-list model, comparative choice with
existence signals, and a graded score. With names and descriptions as the only
evidence, `jev` at 0.9 looks like the frontier on this benchmark: more useful
answers cost more wrong ones along the same curve.

What is left untested is different in kind:

1. the first stage (the right skill is missing from the shortlist for 16% of
   matching requests): a stronger multilingual embedder and synthetic requests
   per skill (tried next, see `2026-11-24-retrieval-results.md`: recall rose,
   the end result barely moved);
2. more evidence: the skill body, which the default does not send off the
   machine;
3. a stronger reader for uncertain cases: the agent itself, measured end to
   end;
4. real requests instead of model-written ones.

## Limits

One dev set of 242 requests, already used to choose the shipped threshold.
Single run of each signal. The Choice was asked over 16 candidates with three
rotations; smaller groups or pairwise duels were not tried. The `openai`
finding is for yes/no questions with this wording only.
