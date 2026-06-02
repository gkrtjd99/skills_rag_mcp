# Duplicate Skill Name Policy

Date: 2026-06-02
Status: Implemented

## Problem

The LanceDB index is keyed by `path`, but retrieval metadata and `get_skill`
lookups use frontmatter `name`. If two different `SKILL.md` files declare the
same `name`, result metadata and body lookup become ambiguous.

## Decision

During sync, keep the first scanned record for each frontmatter `name` and skip
later records with the same name. Skipped duplicate paths are excluded from the
disk path set, so any previously indexed duplicate row is removed during the
same sync.

The sync report includes `duplicate_names` entries:

```json
{"name": "same", "kept": "/path/first/SKILL.md", "skipped": "/path/second/SKILL.md"}
```

The CLI prints a duplicate warning in human sync output. JSON sync output keeps
the structured report.

## Verification

- Sync unit tests cover duplicate skip and stale duplicate removal.
- CLI test covers duplicate warning output.
- `uv run pytest tests/test_sync.py tests/test_cli.py -q`
- `uv run pytest -q`
