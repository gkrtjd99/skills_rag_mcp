# Docker multilingual embedding benchmark

Run models in isolated Linux/CPU containers. The prefetch phase may access
Hugging Face; the timed benchmark phase runs with `--network=none` and
`SKILL_RAG_LOCAL_FILES_ONLY=1`. A temporary Docker volume holds model weights
between phases and is removed unless `--keep-cache` is supplied.

```bash
uv run python bench/run_matrix.py \
  intfloat/multilingual-e5-base \
  BAAI/bge-m3
```

Results are written to `var/benchmark-results/{model}.json`, `summary.json`,
and `summary.md`. Metrics include recall@5, MRR, English/Korean slices, index
time, warm-query p50/p95, peak RSS, embedding dimension, cache bytes, and
model-tokenizer query input tokens. The JSON also contains a separate sparse
token estimate for debugging; neither is a billable API token count.

For mixed positive/negative datasets, an empty `expected` list means the query
should produce no hits. The evaluator reports `no_match_accuracy` separately
from positive-query recall.

The default comparison uses the original English and Korean queries directly.
Query translation is intentionally not applied: a multilingual embedder should
be measured on native multilingual input, while translation would add a second
model's latency and error surface. Description translation can be tested as a
separate ablation, but requires prefetching the MarianMT weights before
enabling `SKILL_RAG_TRANSLATE=1` in the timed container.

Docker Desktop/OrbStack CPU results are not directly comparable to host MPS or
CUDA results; the report records the device explicitly.

The matrix runner accepts repository-relative `--dataset`, `--corpus`, and
`--k` options. The stricter bilingual run is therefore reproducible in Docker:

```bash
uv run python bench/run_matrix.py \
  --dataset eval/fixtures/natural-queries.jsonl \
  --corpus eval/fixtures/skills \
  --k 1 \
  intfloat/multilingual-e5-base BAAI/bge-m3
```

For the stricter natural-language decision check, use the 30-query bilingual
set at top-1:

```bash
uv run skill-rag eval \
  --dataset eval/fixtures/natural-queries.jsonl \
  --corpus eval/fixtures/skills \
  --k 1
```
