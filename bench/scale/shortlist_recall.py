"""First-stage check: is the expected skill in the ungated shortlist?

Local only: no judge, no API call. Configure the first stage through the usual
environment variables (SKILL_RAG_MAX_SEQ_LENGTH, SKILL_RAG_DENSE_BODY_CHARS,
...) and compare runs.

    uv run python bench/scale/shortlist_recall.py \
        --corpus var/bench/scale/corpus-350 --dataset bench/scale/dev-queries.jsonl
"""

from __future__ import annotations

import argparse
import json
import os
import tempfile
import time
from pathlib import Path

from skill_rag import corpus as corpus_mod
from skill_rag import embed, index as index_mod, retrieve
from skill_rag import sync as sync_mod

KS = (8, 16, 24, 32)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--corpus", type=Path, required=True)
    ap.add_argument("--dataset", type=Path, required=True)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    rows = [
        json.loads(line)
        for line in args.dataset.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    rows = [r for r in rows if r["expected"]]
    with tempfile.TemporaryDirectory(prefix="skill-rag-shortlist-") as tmp:
        os.environ["SKILL_RAG_INDEX_PATH"] = str(Path(tmp) / "index.lance")
        corpus_mod.CORPUS_PATH = args.corpus.expanduser().resolve()
        sync_mod.reset_cache()
        embed.encode_one("warm up")  # model load is not index time
        t0 = time.monotonic()
        sync_mod.sync_if_stale(ttl=0)
        index_seconds = time.monotonic() - t0
        skills = index_mod.indexed_count()
        retrieve.shortlist("warm up the caches", max(KS))
        ranks: list[tuple[str, int | None]] = []
        t0 = time.monotonic()
        for r in rows:
            names = [c["name"] for c in retrieve.shortlist(r["query"], max(KS))]
            found = [names.index(n) for n in r["expected"] if n in names]
            ranks.append((r.get("lang", "?"), min(found) if found else None))
        query_ms = (time.monotonic() - t0) * 1000.0 / len(rows)
        sync_mod.reset_cache()

    def recall(k: int, lang: str | None = None) -> float:
        subset = [rank for lg, rank in ranks if lang is None or lg == lang]
        return sum(1 for rank in subset if rank is not None and rank < k) / len(subset)

    result = {
        "max_seq_length": embed.MAX_SEQ_LENGTH,
        "dense_body_chars": corpus_mod.DENSE_BODY_CHARS,
        "skills": skills,
        "queries": len(rows),
        "index_seconds": round(index_seconds, 1),
        "query_ms": round(query_ms, 1),
        **{f"recall@{k}": round(recall(k), 3) for k in KS},
        **{f"recall@16_{lang}": round(recall(16, lang), 3) for lang in sorted({lg for lg, _ in ranks})},
    }
    if args.json:
        print(json.dumps(result))
    else:
        print("  ".join(f"{k}={v}" for k, v in result.items()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
