# Setup Notes Plan

Status: Completed

- [x] `rerank.notes`, `lifecycle.bootstrap_outdated`, `bootstrap_outdated` in
      the install report.
- [x] `status` and `install`: `note` lines and `notes` in `--json`.
- [x] Tests: each note, a ready judge on a large corpus yields none, the
      install report before and after `--refresh-bootstrap`, CLI output.
- [x] READMEs: where the judge's environment variables must be set, the
      notes, and an upgrade section.
- [x] Changelog and version 0.4.0.

Follow-ups:

- Let `install` write the judge's environment into the MCP registration
  without storing the key in a file.
- Refresh an unmodified bootstrap skill automatically, using the hash kept in
  the install state.
