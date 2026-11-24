# Skill cards: negative result

Run on 2026-11-24 under `2026-11-24-cards-protocol.md` (`7da9deb`, committed
before any card existed). Nothing was adopted and no test set was used.

## What was tried

One card per skill of the 350-skill corpus, written by `gpt-6.1-terra` from
the description and body: when to use it, what it is not for, and its key
terms (median 355 characters). The `jev` fit question was then asked with the
card, or the description followed by the card, in place of the description,
on the same 242 dev requests and the same shortlists as the precision work.

## Result on dev

Best configuration per evidence type under the precision rule (junk at most
10% on no-match and 5% on matching requests, one skill returned):

| Evidence shown to the judge | Configuration | Useful | Junk, matching | Junk, no-match |
|---|---|---:|---:|---:|
| Description (shipped) | local shortlist, 0.9 | 0.674 | 0.034 | 0.094 |
| Card | local shortlist, 0.9 | 0.680 | 0.034 | 0.094 |
| Description + card | scan shortlist, 0.95 | 0.511 | 0.017 | 0.078 |

The card gains 0.6 points, one request out of 178, against an adoption bar of
five points. Not adopted.

The closest a card came to mattering was with the scan shortlist at 0.9:
useful 0.736 with junk of 5.6% and 10.9%, each one request over its limit
(description: 0.708, 7.3%, 14.1%).

## Why it did not help

The judge's confidence barely moved. With the scan shortlist, the expected
skill was rated at least 0.9 for 68.8% of requests with the description, 64.2%
with the card, and 68.8% with both; the median change in the expected skill's
probability was +0.01, with 25 requests raised by more than 0.1 and 16
lowered. The top candidate on no-match requests was rated at least 0.9 for
42%, 44%, and 50%.

So the mixing of right and wrong skills between 0.5 and 0.9 does not come
from descriptions failing to say when a skill applies. Restating that more
sharply gives the judge the same information in different words. What it
lacks is either a way to compare similar skills against each other or a
stronger reader for the uncertain cases.

## Limits

One card prompt, one card model, one judge. Requests and cards were both
written from skill bodies, which if anything should have favored cards. A
different card design, for example one written to contrast a skill with its
nearest neighbors in the same corpus, was not tried.
