# Multimodel Docker Benchmark

Date: 2026-07-14
Status: Implemented and measured

## Decision

Add a disposable Docker benchmark for comparing local embedding models on the
same English/Korean fixture queries. Each model runs in a separate process with
its own LanceDB index. Model prefetch is network-enabled, but the timed phase
uses `--network=none` and local-files-only mode, proving query-time offline
operation.

The benchmark measures recall@5, MRR, English/Korean slices, index time, warm
query p50/p95, peak RSS, embedding dimension, cache bytes, and deterministic
query-token estimates. It reports CPU explicitly because Docker Desktop and
OrbStack do not expose the host's MPS device. Query translation is not part of
the primary comparison: native multilingual queries isolate embedding quality;
description translation can be evaluated as a separate ablation.

The follow-up natural-language decision check used 30 paraphrases (15 English,
15 Korean) at top-1. `multilingual-e5-base` reached 1.000 recall in both
languages versus BGE-M3's 0.933 English / 1.000 Korean, with lower p95 latency
and memory. That result authorizes switching the production default while
retaining `SKILL_RAG_MODEL` as an override.
