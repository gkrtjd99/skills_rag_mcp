# Duplicate Skill Name Policy Plan

Status: Implemented

## Steps

- [x] Detect duplicate frontmatter names during sync.
- [x] Keep the first scanned record and skip later duplicates.
- [x] Exclude skipped duplicate paths from the disk path set so stale indexed
  duplicates are removed.
- [x] Add structured `duplicate_names` entries to the sync report.
- [x] Print duplicate warnings in human CLI sync output.
- [x] Add sync and CLI tests.
- [x] Run focused and full test suites.
