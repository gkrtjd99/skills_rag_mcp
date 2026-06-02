# AGENTS

Entry point for any agent joining this repository.
Read documents in the order below before writing code.

## Read Order

1. `ARCHITECTURE.md` — stable system structure and module boundaries.
2. `docs/product-specs/skill-rag.md` — what we are building and why.
3. `docs/design-docs/core-beliefs.md` — non-negotiable principles.
4. `docs/design-docs/mcp-interface.md` — `search_skills` / `get_skill` contract.
5. `docs/design-docs/meta-skill-bootstrap.md` — how the bootstrap skill is installed and behaves.
6. `docs/design-docs/index.md` — design decision log.
7. `docs/design-docs/implementation-history.md` — completed specs/plans, summarized.
8. `docs/superpowers/specs/` and `docs/superpowers/plans/` — active feature work, if any.
9. `docs/references/*-llms.txt` — quick references for uv, lancedb, sentence-transformers, mcp, tomlkit, opus-mt.

## Repository Map

- `src/skill_rag/` — Python package (agents, corpus, models, parser, loader, normalize, offline, embed, translate, sparse, index, retrieve, sync, mcp_server, collect, mcp_config, lifecycle, cli, evaluator).
- `bootstrap-skill/using-skill-rag/SKILL.md` — meta-skill installed into each harness via symlink.
- `Makefile` / `skill-rag install` — set up `~/.skills/`, symlinks, and MCP registration (`skill-rag uninstall` reverses it).
- `eval/fixtures/` — public benchmark corpus and queries.
- `eval/queries.jsonl` — personal-corpus evaluation queries with gold-standard skill names.
- `tests/` — unit + integration tests.
- `var/` — local-only LanceDB index (gitignored).
- External corpus: `~/.skills/` (read-write by the user; not committed).

## Done When

- `mcp__skill-rag__search_skills` returns `{status: "ok"|"no_match", hits, [message]}`.
- `mcp__skill-rag__get_skill` returns `{status: "ok"|"not_found", body|message}`.
- One bootstrap skill in `~/.skills/`, symlinked into Claude Code + Codex, auto-loads in both.
- File added to `~/.skills/` is reflected in the next `search_skills` call after 30 s.
- `recall@5 ≥ 0.8` on the public fixture eval
  (`eval/fixtures/queries.jsonl` against `eval/fixtures/skills/`).
- `p95` search latency `< 1 s` on a ~50-skill corpus.
- No cloud API calls at index or query time.

## Operating Rules

- `README.md` is Korean (canonical); `README.en.md` is the English translation.
  READMEs are the only documents allowed in Korean — everything else stays in English.
- Do not commit the corpus. Treat `~/.skills/` as a user-managed directory.
- Do not add cloud embedding providers. Local-only is a hard constraint (see `core-beliefs.md`).
- When adding a new dependency, update both `pyproject.toml` and `docs/references/<tool>-llms.txt`.
- When the indexing schema changes, bump the schema comment in `src/skill_rag/index.py` and document the migration in `docs/design-docs/`.
- Every behavioral change should be tracked in `docs/superpowers/specs/` and `docs/superpowers/plans/`.
