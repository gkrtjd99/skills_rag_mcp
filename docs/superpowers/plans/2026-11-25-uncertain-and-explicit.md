# Uncertain Candidates and Explicitly Named Skills Plan

Status: Completed

- [x] Protocol for the agent-in-the-loop measurement, committed before data;
      first dev run (not adopted).
- [x] Second protocol, new dev set (`dev2`), selection, confirmation agent.
- [x] `retrieve.uncertain_response`; band in `rerank.search_traced`
      (`SKILL_RAG_RERANK_UNCERTAIN_FROM`); local candidates
      (`SKILL_RAG_LOCAL_CANDIDATES`).
- [x] Fresh test (`test3`, `test3neg`); local candidates made opt-in after
      failing it.
- [x] `retrieve.explicit_matches` and the bypass in `rerank.search_traced`
      (`SKILL_RAG_EXPLICIT`); false-positive check on benchmark requests;
      file-extension cases after review.
- [x] Usage log tolerates hits without a score; CLI `query` prints uncertain
      results; `status` shows the new settings.
- [x] Tests: response shape and wording equal to what was measured, band on
      and off, local candidates opt-in, explicit forms and non-forms.
- [x] Docs: bootstrap skill, MCP contract, ARCHITECTURE, READMEs, changelog,
      benchmark protocols and results.

Follow-ups:

- Read real loads of uncertain candidates from the usage log.
- Measure the band with the `openai` judge.
- Session context for the judge and phase matching, once real requests exist.
