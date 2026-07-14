# Codex System-Skill Gold Evaluation

## Problem

`eval/queries.jsonl` was labeled as a personal-corpus dataset but contained
gold names from several unrelated corpora. A fresh install of the external
skill library could not contain `harness-init`, `imagegen`, `plugin-creator`,
or `openai-docs`, so the measured recall mixed retrieval quality with corpus
membership failures.

## Decision

- Use the five stable Codex system skills under `~/.codex/skills/.system` as
  the canonical local gold corpus: `imagegen`, `openai-docs`,
  `plugin-creator`, `skill-creator`, and `skill-installer`.
- Rewrite `eval/queries.jsonl` with four natural-language queries per skill.
- Add `make eval-codex`, which evaluates that dataset against the system-skill
  directory directly.
- Keep `make eval-personal` configurable through
  `SKILL_RAG_EVAL_CORPUS` and `SKILL_RAG_EVAL_DATASET`; arbitrary personal
  corpora must provide matching gold names instead of reusing the Codex set.

## Non-goals

- Do not commit any user corpus or system-skill bodies.
- Do not treat the external community library as a universal gold set.
- Do not change native Codex skill loading or MCP registration behavior.
