# Design Decision Log

| Date | Decision | Current doc |
| --- | --- | --- |
| 2026-05-28 | Centralize corpus at `~/.skills/` and expose lazy MCP skill loading. | `../../ARCHITECTURE.md`, `mcp-interface.md` |
| 2026-05-29 | Add portable fixture eval as the repository benchmark. | `../product-specs/skill-rag.md`, `../../eval/fixtures/` |
| 2026-05-31 | Add hybrid dense+BM25 retrieval, Korean normalization, and source-agent attribution. | `../../ARCHITECTURE.md`, `mcp-interface.md`, `../../src/skill_rag/index.py` |
| 2026-06-02 | Replace one-way install script with symmetric Makefile/CLI lifecycle. | `meta-skill-bootstrap.md`, `../../src/skill_rag/lifecycle.py` |
| 2026-06-02 | Add local ko<->en description translation at index time. | `../../ARCHITECTURE.md`, `../../src/skill_rag/translate.py` |
| 2026-06-02 | LanceDB schema v6: add `translation_status`; schema drift drops/rebuilds the derived index. | `../../ARCHITECTURE.md`, `../../src/skill_rag/index.py` |
| 2026-06-02 | Consolidate completed superpowers specs/plans into current-state docs and history. | `implementation-history.md` |
| 2026-06-05 | Search per task, not per message: reframe bootstrap + add `skip` status for conversational replies inside interactive flows. | `mcp-interface.md`, `meta-skill-bootstrap.md`, `../../src/skill_rag/retrieve.py` |
| 2026-07-14 | Harden offline verification, full-schema cache migration, corpus parsing, and evaluation percentiles. | `../../docs/superpowers/specs/2026-07-14-reliability-hardening.md` |
| 2026-07-14 | Add disposable Docker multilingual model benchmark and choose native query evaluation. | `../../docs/superpowers/specs/2026-07-14-multimodel-docker-benchmark.md`, `../../docs/benchmarks/2026-07-14-docker-multilingual.md` |
| 2026-07-14 | Switch the default embedding model from BGE-M3 to multilingual-e5-base after a 30-query native bilingual dynamic benchmark. | `../../docs/superpowers/specs/2026-07-14-e5-default-switch.md`, `../../docs/benchmarks/2026-07-14-docker-multilingual.md` |
| 2026-07-14 | Tie the local gold evaluation to the five Codex system skills and separate it from arbitrary personal-corpus evaluation. | `../../docs/superpowers/specs/2026-07-14-codex-gold-eval.md`, `../../Makefile` |
| 2026-07-14 | Stabilize release hygiene, isolate test clocks, serialize sync, and add positive/negative evaluation gates. | `../../docs/superpowers/specs/2026-07-14-maintenance-release.md`, `../../CHANGELOG.md` |
| 2026-07-15 | Calibrate no-match behavior, use E5 query/passage prompts, cache warm retrieval, add Korean intent hints, cap MCP metadata, and make local translation opt-in. | `../../docs/superpowers/specs/2026-07-15-fast-multilingual-retrieval.md`, `../../ARCHITECTURE.md`, `mcp-interface.md` |

Detailed dated implementation plans are intentionally not kept as active docs.
Active future work belongs under `docs/superpowers/specs/` and
`docs/superpowers/plans/`.
