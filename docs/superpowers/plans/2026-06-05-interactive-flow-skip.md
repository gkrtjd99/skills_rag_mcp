# Interactive-Flow Skip Plan

Status: Implemented

## Steps

- [x] Add `is_conversational(query)` and a `skip` response helper to
  `retrieve.py`.
- [x] Short-circuit `mcp_server.search_skills` to return `skip` before
  `sync_if_stale` and before any embedding work.
- [x] Reframe the bootstrap meta-skill: search per task / on topic shift, skip
  during sustained interactive flows; document the `skip` status.
- [x] Update interface docs (`mcp-interface.md`, `meta-skill-bootstrap.md`) and
  `ARCHITECTURE.md` (request flow + loop-prevention table) for the new status.
- [x] Record the decision in `docs/design-docs/index.md`.
- [x] Add unit tests for `is_conversational` and the `skip` short-circuit.
- [x] Run focused and full test suites.
