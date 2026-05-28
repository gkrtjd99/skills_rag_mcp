# Design Decision Log

| Date | Decision | Doc |
| --- | --- | --- |
| 2026-05-28 | Centralize corpus at `~/.skills/`, drop multi-source | `../superpowers/specs/2026-05-28-centralized-skills-rag-design.md` |
| 2026-05-28 | LanceDB schema v3: drop `source` column | `../../src/skill_rag/index.py` (schema comment) |
| 2026-05-28 | `search_skills` + `get_skill` with explicit terminal statuses | `mcp-interface.md` |
| 2026-05-28 | Bootstrap skill via symlink from `~/.skills/` | `meta-skill-bootstrap.md` |
| 2026-05-28 | Local-only, single-user, single-corpus, YAGNI | `core-beliefs.md` |
