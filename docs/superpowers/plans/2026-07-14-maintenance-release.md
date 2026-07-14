# P0/P1 Maintenance Release Plan

Status: Completed for the repository; corpus-specific evaluation is an
external follow-up, while `make eval-codex` covers the stable Codex system
skills.

- [x] Fix full-suite LanceDB background-thread shutdown interference.
- [x] Add lockfile/pytest/build CI and dry-run install smoke coverage.
- [x] Add version/changelog/contribution/security release hygiene.
- [x] Add sync serialization and natural-language evaluation commands.
- [x] Run the final full verification and record release gates.

Verification: `make check` completed with 244 tests passing, `uv lock
--check`, `uv build` for `skill_rag-0.2.0`, and `make install-smoke` passing.
User corpora and model caches remain external and are not committed. The
Codex gold set is evaluated separately with `make eval-codex`; arbitrary
personal corpora must supply matching gold names through `make eval-personal`.
