# Store-Only Skills Plan

Status: Completed

- [x] Return the skill directory from `get_skill`; document it in the bootstrap
      skill and MCP contract.
- [x] Add `adopted` to the install state, tolerant of older state files.
- [x] Implement `lifecycle.adopt` and `lifecycle.restore` with dry-run, name
      filters, never-overwrite rules, and intent-first state writes.
- [x] Make `uninstall` restore adopted skills and protect stranded ones from
      `--purge`.
- [x] Add `skill-rag adopt` / `restore` and an adopted count in `status`.
- [x] Tests for moves, skips, conflicts, uninstall, purge protection, old
      state files, and the CLI.
- [x] End-to-end run in a throwaway home: adopt, search, `get_skill` path,
      restore, adopt again, `uninstall --purge`.

Open follow-ups:

- Project overlay: index the current project's skills alongside the store.
- Prompt hook that calls `search_skills` so use does not depend on the agent
  remembering.
- A local judge provider, measured on the held-out set.
