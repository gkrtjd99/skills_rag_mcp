# Decision structure: selection protocol (fixed before any new signal was collected)

Written and committed on 2026-11-24 before a Choice, companion, gate, or Score
question was asked about a dev request, and before the `openai` judge was run
on dev. It extends `2026-11-24-precision-protocol.md` and follows the research
summary in the session report "스킬 선택 정확도 개선 방법".

## Why

The shipped rule returns the candidate with the highest independent yes/no
probability if it reaches 0.9. On dev, 27% of right skills and most of the best
wrong ones sit between 0.5 and 0.9, so one number per candidate cannot both
pick the skill and decide whether to return it. The vendor's own designs pick
with a multiple-choice question that makes candidates compete, and decide
whether to answer from a separate signal. Published comparisons favor
comparative over independent judgments for ranking; none shows that they
reduce false alarms, and a multiple-choice question always picks something.

## Data

The dev set of the precision protocol: 178 matching and 64 no-match requests,
350-skill corpus, the recorded local shortlist of 16, the same adjudicator.
The dev set has already been used to choose the 0.9 threshold, so the shipped
rule is itself fitted to it; that is the baseline to beat.

## Experiment 1: reanalysis

1a. **Threshold per judge.** Run `openai` once on the dev shortlists. Apply the
precision rule (junk at most 10% on no-match and 5% on matching requests, then
the highest useful rate) over thresholds 0.5, 0.6, 0.7, 0.8, 0.9, 0.95, 0.97,
0.98, 0.99, 0.995, 0.999. The result becomes the default threshold for that
judge.

1b. **Score-list model (`jev`).** Predict whether the top candidate is useful
from six features of the request's 16 probabilities: the top value, the second
value, their difference, how many are at least 0.5, the mean of the top five,
and the top candidate's position in the local ranking. Logistic regression,
predictions from 5-fold cross-validation with a fixed seed. Rule: return the
top candidate if the predicted probability is at least t, for t from 0.5 to
0.95 in steps of 0.05.

1c. **Conformal threshold.** Report the lowest yes/no threshold whose dev
junk rate on no-match requests satisfies the conformal risk bound at 10%.
Reported only.

## Experiment 2: new signals and four rules

One extra `jev` request per dev request collects, for the local shortlist:

- `c`: a Choice over the 16 candidates (name as the option, description as its
  criterion), asked three times with the candidate order rotated by 0, 5, and
  11 positions; the three distributions are averaged.
- `a`: one companion yes/no question, whether any of the listed skills is the
  right one for the request.
- `g`: four yes/no questions about the request alone (acts on the user's
  system; a careful expert would follow a documented procedure; prose alone
  would suffice, inverted; names a specific tool or method). The gate passes
  if the mean of the first three is at least 0.30 or the fourth is at least
  0.50.
- `s`: per candidate, a Score over three levels: unrelated; related topic or
  product but not the right skill; the right skill.

`n` is the yes/no probability already recorded. Rules, each returning at most
one skill:

- **S1, choose then check.** Take the Choice's top candidate; return it if its
  Choice probability is at least tc and its yes/no probability at least tn.
  tc in 0.5, 0.6, 0.7, 0.8, 0.9; tn in 0.3, 0.5, 0.7, 0.9.
- **S2, choose with existence.** Take the Choice's top candidate; return it if
  its Choice probability is at least tc and the companion is at least ta.
  ta in 0.3, 0.5, 0.7, 0.9.
- **S3, graded.** Take the candidate with the highest Score; return it if the
  Score is at least ts. ts in 1.2, 1.4, 1.5, 1.6, 1.7, 1.8, 1.9.
- **S4, rescue the middle.** Return the top yes/no candidate if it reaches
  0.9, as shipped. Otherwise return it if it is also the Choice's top
  candidate, its yes/no probability is at least tn (0.5, 0.6, 0.7, 0.8), and
  its Choice probability at least tc.

Each rule is scored with and without the gate as an extra condition. No other
rule is scored on these signals for selection; anything else looked at is
labelled exploratory.

## Selection, adoption, confirmation

The precision rule picks the best configuration of each family. A family is a
candidate for adoption only if its best configuration returns a useful skill
for at least five more points of matching dev requests than the shipped rule
at the same junk limits. If several qualify, the one with the highest useful
rate is taken, ties by fewest requests and tokens.

If something is adopted it is implemented, committed, and then run once on a
fresh test set built as in the precision protocol from skills and candidates
not used before, against the shipped rule on the same requests. It stays the
default only if on that test its useful rate is higher than the shipped
rule's and neither junk rate is more than three points higher. The 1a
threshold for `openai` is confirmed in the same run.

If nothing is adopted, the result is reported as negative and no test set is
used.

## Limits known in advance

242 dev requests cannot resolve differences of two or three points. The Choice
question shows the candidates to each other, so a description written to win
comparisons would be favored; descriptions are used as published. Requests are
model-written. Only the local shortlist is used; combining a new rule with the
whole-corpus scan is a later step and only if a rule is adopted.
