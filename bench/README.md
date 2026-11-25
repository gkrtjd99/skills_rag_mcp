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

## Held-out gate vs. opt-in rerank

`bench/jev_rerank_ab.py` compares the default gate, the ungated shortlist, and
one arm per `--judge` (the shipped `SKILL_RAG_RERANK` path) on any corpus and
query file. It runs on the host (not Docker). Cloud judges call their API with
`TYPESAFE_API_KEY` / `OPENAI_API_KEY`; with no `--judge`, or with `--replay`,
nothing is sent.

```bash
uv run --extra rerank python bench/jev_rerank_ab.py \
  --corpus <flat dir of skills> \
  --dataset bench/heldout/claude-skills-45.jsonl \
  --judge jev --judge openai \
  --out var/bench/heldout-45.json
```

`bench/heldout/claude-skills.jsonl` (110 queries) targets a 40-skill Claude
Code corpus; `claude-skills-45.jsonl` (133 queries) targets the same corpus
plus `claude-api`, `openai-docs`, `gemini-api-dev`, `uv`, and
`typescript-advanced-types`. Gold labels depend on which skills are present,
so use the file that matches the corpus. The flat `--corpus` directory must
contain those skills; skills installed in nested folders need to be symlinked
into one directory first. `--replay <earlier --out file>` re-scores recorded
probabilities without spending credits. The table reports `resp_chars`, the
size of the JSON an agent receives per search. Keep `--out` under `var/`; it
records local paths.

## Scale benchmark

`bench/scale/` measures the same arms as the corpus grows, on skills and
queries nobody on the project wrote. The rules are in
`docs/benchmarks/2026-11-24-scale-protocol.md` and were committed before any
data was fetched; results are in `docs/benchmarks/2026-11-24-scale-results.md`.

```bash
uv run python bench/scale/prepare.py pool      # download the SKILL.md versions pinned in manifest.json (needs gh)
uv run python bench/scale/prepare.py split     # seeded split, corpora of 50/100/200/350
uv run python bench/scale/prepare.py queries   # model-written queries (needs OPENAI_API_KEY)
for n in 50 100 200 350; do
  uv run --extra rerank python bench/jev_rerank_ab.py \
    --corpus var/bench/scale/corpus-$n --dataset bench/scale/queries.jsonl \
    --judge jev --judge openai --out var/bench/scale/out-$n.json
done
uv run python bench/scale/report.py            # adjudication + bootstrap intervals
```

Downloaded skills live only under `var/bench/scale/` and are never installed or
executed. `manifest.json` records each accepted skill's repository, path, and
blob SHA; `split.json` and `queries.jsonl` are the exact inputs of the
published run.

Later work on the same pool, each with its protocol committed first
(`docs/benchmarks/2026-11-24-first-stage-protocol.md`,
`docs/benchmarks/2026-11-24-precision-protocol.md`; results in
`docs/benchmarks/2026-11-24-precision-results.md`):

```bash
uv run python bench/scale/prepare.py dev-queries      # dev positives (new targets)
uv run python bench/scale/prepare.py dev-negatives    # dev no-match requests
uv run python bench/scale/shortlist_recall.py --corpus var/bench/scale/corpus-350 \
  --dataset bench/scale/dev-queries.jsonl             # first stage only, no API
uv run --extra rerank python bench/scale/precision_dev.py record    # judge once per dev query
uv run python bench/scale/precision_dev.py evaluate                 # score decision rules offline
uv run python bench/scale/prepare.py test2            # fresh test set, built after the config is fixed
uv run python bench/scale/report.py --prefix test2after
```

`queries.jsonl` (first test set) is retired; do not tune against it or
`test2-queries.jsonl`. New decisions need new dev data and, for final numbers,
a new test set.

`bench/scale/cards_dev.py` holds the skill-card experiment
(`docs/benchmarks/2026-11-24-cards-protocol.md`), which ended in a negative
result (`docs/benchmarks/2026-11-24-cards-results.md`).

`bench/scale/structure_dev.py` holds the decision-structure experiments
(`docs/benchmarks/2026-11-24-structure-protocol.md`), also a negative result
(`docs/benchmarks/2026-11-24-structure-results.md`).

`bench/scale/retrieval_dev.py` holds the embedder and synthetic-request
experiment (`docs/benchmarks/2026-11-24-retrieval-protocol.md`, results in
`docs/benchmarks/2026-11-24-retrieval-results.md`).

`bench/scale/agent_dev.py` holds the agent-in-the-loop experiment
(`docs/benchmarks/2026-11-25-agent-protocol.md`): a model plays the caller and
decides what to load. Not adopted; results in
`docs/benchmarks/2026-11-25-agent-results.md`.
