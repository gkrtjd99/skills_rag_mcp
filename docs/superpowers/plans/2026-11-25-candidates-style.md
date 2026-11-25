# Candidates Style Plan

Status: Completed

- [x] Baseline: every description in context, protocol and reading rule
      committed first (`native_baseline.py`).
- [x] Protocol for several candidates, committed before any agent saw a list;
      ten configurations on `dev3`; selection; confirmation agent.
- [x] `retrieve.candidates_response`; `RERANK_STYLE`, `RERANK_FLOOR`,
      `RERANK_SHOWN`; scan default 500; CLI `query` and `status`.
- [x] Fresh test `test4` with both agents, and the all-descriptions baseline
      on the same requests.
- [x] Tests: response shape and wording equal to what was measured, floor and
      limit, `single` style unchanged.
- [x] Docs: bootstrap skill, MCP contract, SECURITY, ARCHITECTURE, READMEs
      (opening comparison), changelog, benchmark results.

Follow-ups:

- Read real loads of candidates from the usage log.
- Measure the style with the `openai` judge.
- Measure other corpus sizes, and the scan's cost and latency above 350.
- A path without a judge that comes closer to these numbers.
