"""Run one local embedding model benchmark inside the disposable container."""

from __future__ import annotations

import argparse
import json
import os
import platform
import resource
import time
from pathlib import Path


def _rss_mb() -> float:
    # Linux reports KiB; the benchmark always runs in the Linux container.
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0


def _tree_bytes(root: Path) -> int:
    total = 0
    if not root.exists():
        return 0
    for path in root.rglob("*"):
        if path.is_file():
            try:
                total += path.stat().st_size
            except OSError:
                pass
    return total


def _cgroup_value(name: str) -> int | None:
    for path in (Path("/sys/fs/cgroup") / name, Path("/sys/fs/cgroup/memory") / name):
        try:
            value = path.read_text().strip()
            return None if value == "max" else int(value)
        except (OSError, ValueError):
            continue
    return None


def _language(text: str) -> str:
    return "ko" if any("가" <= c <= "힣" for c in text) else "en"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True)
    parser.add_argument("--dataset", default="/app/eval/fixtures/queries.jsonl")
    parser.add_argument("--corpus", default="/app/eval/fixtures/skills")
    parser.add_argument("--output", required=True)
    parser.add_argument("--k", type=int, default=5)
    args = parser.parse_args()

    # Set all runtime configuration before importing skill_rag modules.
    os.environ["SKILL_RAG_MODEL"] = args.model
    os.environ["SKILL_RAG_CORPUS_PATH"] = args.corpus
    os.environ["SKILL_RAG_INDEX_PATH"] = "/tmp/skill-rag-benchmark-index.lance"
    os.environ["SKILL_RAG_LOCAL_FILES_ONLY"] = "1"
    os.environ["SKILL_RAG_TRANSLATE"] = "0"

    from skill_rag import embed, sync
    from skill_rag.evaluator import evaluate, load_cases
    from skill_rag import retrieve
    from skill_rag.sparse import tokenize

    cache = Path(os.environ.get("HF_HOME", "/root/.cache/huggingface"))
    cache_before = _tree_bytes(cache)
    rss_before = _rss_mb()
    index_start = time.perf_counter()
    sync.run_sync()
    index_ms = (time.perf_counter() - index_start) * 1000.0
    # Force model metadata access after the first load and before querying.
    model = embed._load_model(args.model)
    cases = load_cases(Path(args.dataset))
    report = evaluate(cases, k=args.k, search_fn=retrieve.search)
    by_language = {}
    for lang in ("en", "ko"):
        subset = [case for case in cases if _language(case.query) == lang]
        if subset:
            by_language[lang] = evaluate(subset, k=args.k, search_fn=retrieve.search).to_dict()
    query_tokens = sum(len(tokenize(case.query)) for case in cases)
    try:
        encoded_queries = model.tokenizer(
            [case.query for case in cases],
            truncation=True,
            max_length=int(getattr(model, "max_seq_length", 512) or 512),
        )["input_ids"]
        model_query_tokens = sum(len(ids) for ids in encoded_queries)
    except Exception:
        model_query_tokens = None

    result = {
        "model": args.model,
        "device": "cuda" if getattr(__import__("torch"), "cuda").is_available() else "cpu",
        "platform": platform.platform(),
        "python": platform.python_version(),
        "embedding_dimension": embed.model_dim(args.model),
        "max_seq_length": getattr(model, "max_seq_length", None),
        "index_ms": round(index_ms, 3),
        "recall_at_k": report.recall_at_k,
        "mrr": report.mrr,
        "p50_query_ms": report.p50_ms,
        "p95_query_ms": report.p95_ms,
        "n_queries": report.n,
        "query_token_estimate": query_tokens,
        "query_token_estimate_avg": query_tokens / len(cases) if cases else 0,
        "model_query_tokens": model_query_tokens,
        "by_language": by_language,
        "rss_before_mb": round(rss_before, 2),
        "rss_peak_mb": round(_rss_mb(), 2),
        "hf_cache_delta_bytes": _tree_bytes(cache) - cache_before,
        "hf_cache_bytes": _tree_bytes(cache),
        "cgroup_memory_peak_mb": (_cgroup_value("memory.peak") or 0) / 1048576,
        "cgroup_memory_limit_mb": (_cgroup_value("memory.max") or 0) / 1048576,
        "misses": report.misses,
    }
    Path(args.output).write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")


if __name__ == "__main__":
    main()
