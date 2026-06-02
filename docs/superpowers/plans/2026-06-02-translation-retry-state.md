# Translation Retry State Plan

Status: Implemented

## Steps

- [x] Add `SkillRecord.translation_status`.
- [x] Add `translate_for_index(text) -> (text, status)`.
- [x] Bump LanceDB schema to v6 with a `translation_status` column.
- [x] Store translation status on upsert and include it in indexed metadata.
- [x] Retry unchanged rows whose prior translation status is failed, disabled,
  or pending while translation is enabled.
- [x] Remove the resolved follow-up from the tech debt tracker.
- [x] Update architecture, design log, and LanceDB reference docs.
- [x] Add focused tests for status values, index storage, and sync retry.
- [x] Run focused and full test suites.
