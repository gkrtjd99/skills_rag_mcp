# P0/P1 Maintenance Release

Date: 2026-07-14
Status: Implemented and verified

## Scope

Stabilize the local MCP project before publishing a release. This work does
not disable native Claude/Codex skill loading and does not add AgentOTelStack
as a runtime dependency.

## Changes

- Isolate evaluator and sync clocks so tests cannot mutate the process-wide
  `time.monotonic` used by LanceDB background threads.
- Serialize in-process sync/index mutations with a reentrant lock.
- Add offline CI, lockfile verification, dry-run install smoke coverage, and
  wheel build verification.
- Add version `0.2.0`, changelog, contribution, and security guidance.
- Add reproducible natural-language and Docker evaluation commands.
- Document native skill loading as an independent fallback rather than a hard
  guarantee that every harness will skip its own loader.

## Gates

- Full offline pytest suite completes without hangs.
- `uv lock --check` and `uv build` pass.
- Public fixture recall@5 remains at least 0.8.
- English and Korean natural-language recall@1 remain at least 0.95 for the
  default model.
- No corpus, model cache, LanceDB index, or telemetry payload is committed.

