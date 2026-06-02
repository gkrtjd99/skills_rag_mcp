# Bootstrap Refresh Policy

Date: 2026-06-02
Status: Implemented

## Problem

`skill-rag install` copied the bootstrap meta-skill only when
`~/.skills/using-skill-rag` was missing. That preserved user edits, but there
was no explicit way to refresh the installed bootstrap after the repo template
changed.

## Decision

Keep the conservative default: an existing installed bootstrap is preserved.
Add `skill-rag install --refresh-bootstrap` to overwrite the installed
bootstrap from `bootstrap-skill/using-skill-rag`.

The install report now includes:

- `bootstrap_installed`: copied because the destination was missing.
- `bootstrap_refreshed`: overwritten because `--refresh-bootstrap` was used.

Dry-run reports what would happen without writing.

## Verification

- Lifecycle tests cover preserve-by-default, explicit refresh, and dry-run.
- CLI test verifies `--refresh-bootstrap` is passed to lifecycle.
- `uv run pytest tests/test_lifecycle.py tests/test_cli.py -q`
- `uv run pytest -q`
