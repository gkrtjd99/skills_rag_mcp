# skill-rag - Product Spec

## What

A local RAG over a user's skill corpus at `~/.skills/`, exposed to AI agents
through an MCP server. Agents call `search_skills` to find relevant skills and
`get_skill` to fetch the body of only the skills that apply.

## Why

Agent harnesses tend to load many skills up front and often duplicate the same
skills under separate per-harness directories. That wastes context and creates
drift. skill-rag keeps one user-global corpus and makes skill loading lazy.

## Users

A single developer running multiple local agent harnesses (Claude Code, Codex,
Antigravity, etc.) on the same machine.

## Guarantees

- The skill-rag path loads only the bootstrap skill by default. Other skill
  bodies are fetched on demand; a harness's independent native skill loader may
  still load its own skills as a fallback.
- A direct `~/.skills/<name>/SKILL.md` file is reflected by the next
  `search_skills` call after the 30 s sync TTL expires.
- `search_skills` and `get_skill` return explicit terminal statuses that a
  conforming bootstrap skill cannot loop on.
- Retrieval supports English and Korean queries through local
  multilingual-e5-base dense
  embeddings with E5 query/passage prompts, Korean-aware BM25, and a small
  deterministic Korean intent bridge. Optional index-time ko<->en description
  translation is available but disabled by default because native E5 retrieval
  is the measured primary path.
- Warm retrieval reuses the LanceDB table, indexed metadata, and BM25
  structure in-process; search responses cap descriptions to avoid spending
  agent context on repeated metadata.
- No cloud API calls happen during indexing or querying.
- `make install` and `skill-rag uninstall` provide a symmetric setup/teardown
  path for bootstrap links, collected symlinks, the local index, and MCP
  registration.

## Out of Scope

- Multi-user or shared corpora.
- Cloud embedding, translation, reranking, or LLM-based relevance scoring.
- Real-time filesystem watchers.
- Languages beyond Korean and English translation support.
- Native-skill exclusion by caller harness. `agent` is currently attribution
  metadata only.
- Preserving backwards compatibility with pre-`~/.skills` corpus layouts.

## Success Metrics

- `recall@5 >= 0.8` on the public fixture eval shipped in this repository.
- The default model must reach at least `recall@1 >= 0.95` independently on
  the English and Korean natural-language fixture.
- Negative query sets report no-match accuracy separately from positive recall;
  unrelated queries must not be counted as retrieval misses.
- `p95 < 1 s` search latency on a roughly 50-skill corpus.
- The public no-match fixture reports no-match accuracy separately and reaches
  1.0 with the default retrieval profile.
- No cloud API calls in indexing or query paths.
