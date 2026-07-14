# E5 Default Model Switch

Date: 2026-07-14
Status: Implemented and measured

## Decision

Use `intfloat/multilingual-e5-base` as the default local embedding model.
Keep `SKILL_RAG_MODEL` as the explicit override for users who need BGE-M3 or
another sentence-transformers model. Query text remains native Korean or
English; no query translation is added.

## Evidence

Thirty natural-language paraphrases (15 English and 15 Korean) were evaluated
at top-1 against the public fixture corpus in separate Docker CPU containers.
E5-base achieved 30/30 hits, p95 query latency of 164.7 ms, and 1,656 MiB
process RSS. The previous BGE-M3 default achieved 29/30, 287.3 ms p95, and
2,509 MiB RSS. The existing 0.45 dense threshold was used unchanged.

## Migration

The LanceDB index is derived state. Changing the default from BGE-M3's 1,024
dimensions to E5's 768 dimensions is detected by the existing full-schema
check; the next `skill-rag sync` drops the stale table and rebuilds it. Users
can force the migration with `skill-rag reset && skill-rag sync`.

