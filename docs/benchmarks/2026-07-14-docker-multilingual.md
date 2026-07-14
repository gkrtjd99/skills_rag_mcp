# Docker multilingual embedding benchmark

Measured on the repository fixture (`n=17`: English 10, Korean 7) in
separate Linux/arm64 OrbStack CPU containers. Query translation was disabled;
English and Korean originals were sent directly to each multilingual embedder.
The timed phase had no network access.

The published rows are controlled single-pass runs (17 warm queries after
indexing) with no explicit per-container CPU or memory cap; the reusable
matrix runner defaults to 4 CPUs and 8 GiB (`--cpus=4 --memory=8g`) for
repeatable reruns.
All models used the repository's raw-text input path; E5-specific
`query:`/`passage:` prefixes were not added, so this is an as-is pipeline
comparison.

| Model | Dim | EN recall@5 | KO recall@5 | MRR | Query p50/p95 | Process peak RSS | cgroup peak |
|---|---:|---:|---:|---:|---:|---:|---:|
| paraphrase-multilingual-MiniLM-L12-v2 | 384 | 1.000 | 0.571 | 0.824 | 75.0 / 87.1 ms | 1,643 MiB | 1,874 MiB |
| multilingual-e5-base | 768 | 1.000 | 1.000 | 1.000 | 72.4 / 90.8 ms | 1,667 MiB | 2,495 MiB |
| bge-m3 | 1024 | 1.000 | 1.000 | 1.000 | 158.6 / 204.1 ms | 2,524 MiB | 3,467 MiB |

Token accounting was identical across these 17 fixture queries: the model
tokenizers consumed 209 query-input tokens total (12.29/query average), while
the repository's sparse tokenizer counted 150 (8.82/query). These are local
input-token counts for diagnostics, not billable API tokens.

All runs used CPU because macOS MPS is not exposed inside the Linux
container. Approximate model snapshot sizes are 449 MiB, 1.04 GiB, and
2.12 GiB respectively; the runner also records the actual cache size in each
JSON result. The temporary Docker volumes and benchmark image were removed
after the runs.

## Conclusion

`multilingual-e5-base` is the current quality/latency/memory balance: it matched
BGE-M3 on this bilingual fixture while using less peak memory and substantially
less query latency. Keep BGE-M3 as a quality reference, and do not add query
translation to the primary path; it would add another model's latency and
translation errors without improving these measured bilingual results.

This is a small fixture, not a universal model ranking. Re-run
`make benchmark-docker` with a representative private corpus before treating
the default choice as final for a different skill collection.

## Natural-language decision check

Before changing the default, 30 additional natural-language paraphrases were
run at top-1 (15 English and 15 Korean, six intents per fixture skill) using
the same raw-text pipeline and the existing 0.45 dense threshold:

| Model | EN recall@1 | KO recall@1 | MRR | Query p50/p95 | Process peak RSS | cgroup peak |
|---|---:|---:|---:|---:|---:|---:|
| multilingual-e5-base | 1.000 | 1.000 | 1.000 | 107.5 / 164.7 ms | 1,656 MiB | 1,924 MiB |
| bge-m3 | 0.933 | 1.000 | 0.967 | 261.0 / 287.3 ms | 2,509 MiB | 3,750 MiB |

E5-base therefore becomes the default. The BGE-M3 result missed one English
unit-testing paraphrase and used roughly 2x the query p95 and 1.5x the process
RSS. Existing BGE indexes are disposable derived state; the full-schema
dimension check recreates the table and the next sync rebuilds it at E5's
768-dimensional vectors.
