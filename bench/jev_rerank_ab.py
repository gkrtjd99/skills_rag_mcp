"""A/B: shipped hybrid gate vs. the opt-in rerank path, one arm per judge.

Run against a corpus the thresholds were not tuned on:

    uv run --extra rerank python bench/jev_rerank_ab.py \
        --corpus <dir> --dataset bench/heldout/claude-skills-45.jsonl \
        --judge jev --judge openai --out var/bench/out.json

Arms, all measured on the same index and queries:

- ``gate``     ``search_skills`` with rerank off: the default local path.
- ``ungated``  ``retrieve.shortlist``: the same hybrid ranking with every
               threshold disabled. It never answers no_match, so it is the
               recall ceiling of what a judge gets to see.
- ``<judge>``  ``search_skills`` with ``SKILL_RAG_RERANK=<judge>``: the shipped
               code path in ``skill_rag.rerank``, called for real. Any provider
               id or ``module:factory`` works. Cloud judges need their API key
               and send the dataset queries and shortlisted skill
               names/descriptions to that provider.

``--candidates`` and ``--fit-threshold`` default to the shipped defaults. The
threshold sweep at the end reuses the recorded probabilities; it is a
sensitivity readout on the same queries, not a tuned result.

Dataset rows are ``{"query", "expected"}`` with optional ``lang`` and ``kind``.
``resp_chars`` is the size of the JSON the agent receives, i.e. the context a
search costs. Write ``--out`` under ``var/`` (gitignored): it records local
paths.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
import tempfile
import time
from pathlib import Path

from skill_rag import corpus as corpus_mod
from skill_rag import index as index_mod
from skill_rag import mcp_server, rerank, retrieve
from skill_rag import sync as sync_mod

SWEEP = (0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8)
LOCAL_ARMS = ["gate", "ungated"]


def load_rows(path: Path) -> list[dict]:
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        obj = json.loads(line)
        expected = obj["expected"]
        if isinstance(expected, str):
            expected = [expected]
        rows.append(
            {
                "query": str(obj["query"]),
                "expected": list(expected),
                "lang": obj.get("lang", "?"),
                "kind": obj.get("kind", "positive" if expected else "no_match"),
            }
        )
    return rows


def load_replay(path: Path) -> dict[tuple[str, str], dict[str, float]]:
    """``(judge, query) -> {skill: probability}`` from an earlier ``--out`` file."""
    recorded = {}
    for r in json.loads(path.read_text(encoding="utf-8"))["records"]:
        fits = r.get("fits") or r.get("jev", {}).get("fits") or {}
        # Files written before judges were pluggable hold one flat Jev mapping.
        by_judge = fits if all(isinstance(v, dict) for v in fits.values()) and fits else {"jev": fits}
        for name, mapping in by_judge.items():
            recorded[(name, r["query"])] = mapping
        for name, mapping in (r.get("scan") or {}).items():
            recorded[(name + "/scan", r["query"])] = mapping
    return recorded


def kept_names(fits: dict[str, float], threshold: float, k: int) -> list[str]:
    kept = [n for n, p in fits.items() if p >= threshold]
    kept.sort(key=lambda n: fits[n], reverse=True)
    return kept[:k]


def pct(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    return ordered[max(0, math.ceil(len(ordered) * q) - 1)]


def score(records: list[dict], arm: str, k: int) -> dict:
    """Metrics for one arm over ``records`` (each has ``hits[arm]``)."""
    pos = [r for r in records if r["expected"]]
    neg = [r for r in records if not r["expected"]]
    top1 = hitk = 0
    rr = 0.0
    returned = 0
    for r in pos:
        names = r["hits"][arm][:k]
        returned += len(names)
        found = [n for n in r["expected"] if n in names]
        if found:
            hitk += 1
            rank = min(names.index(n) + 1 for n in found)
            rr += 1.0 / rank
            top1 += rank == 1
    correct_neg = sum(1 for r in neg if not r["hits"][arm])
    lat = [r["ms"][arm] for r in records if arm in r.get("ms", {})]
    chars = [r["resp_chars"][arm] for r in records if arm in r.get("resp_chars", {})]
    return {
        "pos_n": len(pos),
        "recall@1": top1 / len(pos) if pos else None,
        f"recall@{k}": hitk / len(pos) if pos else None,
        "mrr": rr / len(pos) if pos else None,
        "avg_hits_on_pos": returned / len(pos) if pos else None,
        "neg_n": len(neg),
        "no_match_acc": correct_neg / len(neg) if neg else None,
        "resp_chars": sum(chars) / len(chars) if chars else None,
        "p50_ms": pct(lat, 0.5),
        "p95_ms": pct(lat, 0.95),
    }


def fmt(v) -> str:
    if v is None:
        return "  -  "
    return f"{v:5.3f}" if isinstance(v, float) else f"{v:5d}"


def print_block(title: str, records: list[dict], arms: list[str], k: int) -> dict:
    out = {}
    print(f"\n## {title}  (n={len(records)})")
    cols = ["recall@1", f"recall@{k}", "avg_hits_on_pos", "no_match_acc", "resp_chars", "p50_ms", "p95_ms"]
    print(f"{'arm':<10}" + "".join(f"{c:>17}" for c in cols))
    for arm in arms:
        m = score(records, arm, k)
        out[arm] = m
        cells = []
        for c in cols:
            v = m[c]
            if c.endswith("_ms") or c == "resp_chars":
                cells.append(f"{v:17.1f}" if v is not None else f"{'-':>17}")
            else:
                cells.append(f"{fmt(v):>17}")
        print(f"{arm:<10}" + "".join(cells))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--corpus", type=Path, required=True)
    ap.add_argument("--dataset", type=Path, action="append", required=True)
    ap.add_argument("--k", type=int, default=5)
    ap.add_argument(
        "--judge",
        action="append",
        default=[],
        help="rerank provider to measure (repeatable): jev, openai, or module:factory",
    )
    ap.add_argument("--candidates", type=int, default=rerank.RERANK_CANDIDATES)
    ap.add_argument("--fit-threshold", type=float, default=rerank.RERANK_THRESHOLD)
    ap.add_argument("--max-hits", type=int, default=rerank.RERANK_MAX_HITS, help="0 = up to k")
    ap.add_argument("--scan-max", type=int, default=rerank.RERANK_SCAN_MAX, help="0 = no whole-corpus scan")
    ap.add_argument(
        "--replay",
        type=Path,
        default=None,
        help="reuse the probabilities recorded in an earlier --out file instead of "
        "calling any API; a query whose shortlist has an unrecorded skill fails over "
        "to the local gate and is counted as a fallback",
    )
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()

    rows: list[dict] = []
    for ds in args.dataset:
        for row in load_rows(ds.expanduser().resolve()):
            row["dataset"] = ds.name
            rows.append(row)

    rerank.RERANK_CANDIDATES = args.candidates
    rerank.RERANK_THRESHOLD = args.fit_threshold
    rerank.RERANK_MAX_HITS = args.max_hits
    rerank.RERANK_SCAN_MAX = args.scan_max
    rerank.RERANK_COOLDOWN_SECONDS = 0.0  # measure every query independently
    recorded = load_replay(args.replay) if args.replay else None
    judged: dict = {}
    real_judge = rerank.judge

    def recording_judge(query, candidates):
        if recorded is not None:
            mapping = recorded[(rerank.RERANK_PROVIDER, query)]
            fits = [mapping[c["name"]] for c in candidates]
        else:
            fits = real_judge(query, candidates)
        judged["fits"] = {c["name"]: p for c, p in zip(candidates, fits)}
        return fits

    rerank.judge = recording_judge
    real_scan = rerank.scan

    def recording_scan(query, candidates):
        if recorded is not None:
            mapping = recorded[(rerank.RERANK_PROVIDER + "/scan", query)]
            coarse = [mapping[c["name"]] for c in candidates]
        else:
            coarse = real_scan(query, candidates)
        judged["scan"] = {c["name"]: round(p, 4) for c, p in zip(candidates, coarse)}
        return coarse

    rerank.scan = recording_scan

    arms = LOCAL_ARMS + args.judge
    records: list[dict] = []
    fallbacks = {name: 0 for name in args.judge}
    tokens: dict[str, list[int]] = {name: [] for name in args.judge}
    models: dict[str, set] = {name: set() for name in args.judge}
    old_corpus = corpus_mod.CORPUS_PATH
    old_index = os.environ.get("SKILL_RAG_INDEX_PATH")
    try:
        with tempfile.TemporaryDirectory(prefix="skill-rag-ab-") as tmp:
            os.environ["SKILL_RAG_INDEX_PATH"] = str(Path(tmp) / "index.lance")
            corpus_mod.CORPUS_PATH = args.corpus.expanduser().resolve()
            sync_mod.reset_cache()
            sync_mod.sync_if_stale(ttl=0)
            print(f"corpus = {corpus_mod.CORPUS_PATH}  skills = {index_mod.indexed_count()}")
            rerank.RERANK_PROVIDER = ""
            mcp_server.search_skills("warm up the embedding model", k=1)

            for i, row in enumerate(rows, 1):
                q = row["query"]
                rec = {**row, "hits": {}, "ms": {}, "resp_chars": {}, "fits": {}, "scan": {}}

                rerank.RERANK_PROVIDER = ""
                t0 = time.monotonic()
                res = mcp_server.search_skills(q, k=args.k)
                rec["ms"]["gate"] = (time.monotonic() - t0) * 1000.0
                rec["hits"]["gate"] = [h["name"] for h in res.get("hits", [])]
                rec["resp_chars"]["gate"] = len(json.dumps(res, ensure_ascii=False))

                t0 = time.monotonic()
                shortlist = (
                    []
                    if retrieve.is_conversational(q)
                    else [c["name"] for c in retrieve.shortlist(q, max(args.k, args.candidates))]
                )
                rec["ms"]["ungated"] = (time.monotonic() - t0) * 1000.0
                rec["hits"]["ungated"] = shortlist[: args.k]
                rec["shortlist"] = shortlist

                for name in args.judge:
                    judged.clear()
                    rerank.RERANK_PROVIDER = name
                    t0 = time.monotonic()
                    res = mcp_server.search_skills(q, k=args.k)
                    rec["ms"][name] = (time.monotonic() - t0) * 1000.0
                    rec["hits"][name] = [h["name"] for h in res.get("hits", [])]
                    rec["resp_chars"][name] = len(json.dumps(res, ensure_ascii=False))
                    if "scan" in judged:
                        rec["scan"][name] = dict(judged["scan"])
                    if "fits" in judged:
                        rec["fits"][name] = dict(judged["fits"])
                        if recorded is None:
                            current = rerank.current_judge()
                            usage = getattr(current, "last_usage", None) or {}
                            spent = int(usage.get("input_tokens") or 0)
                            if "scan" in judged:
                                spent += int((getattr(current, "last_scan_usage", None) or {}).get("input_tokens") or 0)
                            tokens[name].append(spent)
                            models[name].add(str(usage.get("model")))
                    elif shortlist:
                        fallbacks[name] += 1  # judge failed; shipped path used the local gate
                records.append(rec)
                if i % 20 == 0:
                    print(f"  ... {i}/{len(rows)}", file=sys.stderr)
            sync_mod.reset_cache()
    finally:
        rerank.RERANK_PROVIDER = ""
        corpus_mod.CORPUS_PATH = old_corpus
        if old_index is None:
            os.environ.pop("SKILL_RAG_INDEX_PATH", None)
        else:
            os.environ["SKILL_RAG_INDEX_PATH"] = old_index

    summary: dict = {}
    summary["all"] = print_block("all", records, arms, args.k)
    for lang in sorted({r["lang"] for r in records}):
        subset = [r for r in records if r["lang"] == lang]
        summary[f"lang={lang}"] = print_block(f"lang={lang}", subset, arms, args.k)
    for kind in sorted({r["kind"] for r in records}):
        subset = [r for r in records if r["kind"] == kind]
        summary[f"kind={kind}"] = print_block(f"kind={kind}", subset, arms, args.k)

    pos = [r for r in records if r["expected"]]
    in_shortlist = sum(1 for r in pos if any(n in r["shortlist"] for n in r["expected"]))
    if pos:
        print(
            f"\nshortlist recall@{args.candidates} = {in_shortlist / len(pos):.3f} "
            f"({in_shortlist}/{len(pos)})  <- ceiling for every judge arm"
        )

    summary["sweep"] = {}
    for name in args.judge:
        used = tokens[name]
        print(
            f"\n## judge={name}: requests={len(used)} fallbacks_to_local_gate={fallbacks[name]} "
            f"model={sorted(models[name])} input_tokens total={sum(used)} "
            f"mean={sum(used) / len(used) if used else 0:.0f}"
        )
        print(f"{'threshold':<10}{'recall@1':>10}{f'recall@{args.k}':>10}{'avg_hits':>10}{'no_match':>10}")
        sweep = {}
        for t in SWEEP:
            swept = []
            for r in records:
                hits = kept_names(r["fits"][name], t, args.k) if name in r["fits"] else r["hits"][name]
                swept.append({**r, "hits": {name: hits}, "ms": {}, "resp_chars": {}})
            m = score(swept, name, args.k)
            sweep[str(t)] = m
            mark = "  <- shipped" if t == args.fit_threshold else ""
            print(
                f"{t:<10}{fmt(m['recall@1']):>10}{fmt(m[f'recall@{args.k}']):>10}"
                f"{fmt(m['avg_hits_on_pos']):>10}{fmt(m['no_match_acc']):>10}{mark}"
            )
        summary["sweep"][name] = sweep

    summary["usage"] = {
        name: {"requests": len(tokens[name]), "input_tokens": sum(tokens[name]), "fallbacks": fallbacks[name]}
        for name in args.judge
    }
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(
            json.dumps(
                {"args": {k: str(v) for k, v in vars(args).items()}, "summary": summary, "records": records},
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
