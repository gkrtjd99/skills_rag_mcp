"""Whole-corpus scan with the agent in the loop: docs/benchmarks/2026-11-25-scan-protocol.md.

    uv run python bench/scale/prepare.py dev3                               # OPENAI_API_KEY, gh
    uv run --extra rerank python bench/scale/scan_agent.py record dev3      # TYPESAFE_API_KEY
    uv run python bench/scale/scan_agent.py evaluate dev3                   # OPENAI_API_KEY
    uv run python bench/scale/scan_agent.py confirm dev3 S                  # second agent
"""

from __future__ import annotations

import hashlib
import json
import os
import statistics
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import agent_dev as base

HERE, WORK = base.HERE, base.WORK
CORPUS = WORK / "corpus-350"
SHORTLIST = 16
CONFIRMED_AT, UNCERTAIN_FROM = 0.9, 0.7
ARMS = {"L": ("local", True), "S": ("scan", True), "S9": ("scan", False)}  # shortlist, band


def records_dir(tag: str) -> Path:
    return WORK / f"scan-{tag}"


def record(tag: str) -> None:
    from skill_rag import corpus as corpus_mod
    from skill_rag import index as index_mod
    from skill_rag import retrieve
    from skill_rag import sync as sync_mod
    from skill_rag.judges import JudgeConfig, load

    rows = [json.loads(line) for line in (HERE / f"{tag}-queries.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    with tempfile.TemporaryDirectory(prefix="skill-rag-scan-") as tmp:
        os.environ["SKILL_RAG_INDEX_PATH"] = str(Path(tmp) / "index.lance")
        corpus_mod.CORPUS_PATH = CORPUS.resolve()
        sync_mod.reset_cache()
        sync_mod.sync_if_stale(ttl=0)
        total = len(index_mod.list_indexed())
        local = {r["query"]: (retrieve.shortlist(r["query"], SHORTLIST), retrieve.shortlist(r["query"], total)) for r in rows}
        sync_mod.reset_cache()

    def one(r: dict) -> None:
        path = records_dir(tag) / f"{hashlib.sha1(r['query'].encode()).hexdigest()}.json"
        if path.exists():
            return
        top_local, everything = local[r["query"]]
        judge = load("jev", JudgeConfig(timeout=60))
        t0 = time.monotonic()
        coarse = judge.scan(r["query"], everything)
        scan_ms = (time.monotonic() - t0) * 1000
        # Stable sort, as rerank._shortlist: equal probabilities keep the hybrid order.
        order = sorted(range(len(everything)), key=lambda i: coarse[i], reverse=True)
        top_scan = [everything[i] for i in order[:SHORTLIST]]
        union = {c["name"]: c for c in top_local + top_scan}
        t0 = time.monotonic()
        fits = dict(zip(union, judge.fits(r["query"], list(union.values()))))
        fit_ms = (time.monotonic() - t0) * 1000
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {
                    **r,
                    "local": [c["name"] for c in top_local],
                    "scan": [c["name"] for c in top_scan],
                    "fits": fits,
                    "scan_tokens": judge.last_scan_usage["input_tokens"],
                    "ms": {"scan": scan_ms, "fit": fit_ms},
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

    def retried(r: dict) -> None:
        for attempt in range(4):
            try:
                return one(r)
            except Exception:
                if attempt == 3:
                    raise

    with ThreadPoolExecutor(3) as pool:
        list(pool.map(retried, rows))
    print(f"recorded {len(list(records_dir(tag).glob('*.json')))} of {len(rows)} {tag} requests")


def pick(rec: dict, source: str, band: bool) -> tuple[str | None, bool]:
    """(skill to return, whether it is confirmed) under the shipped rule."""
    names = rec[source]
    best = max(names, key=lambda n: rec["fits"][n])  # max keeps the first on ties
    p = rec["fits"][best]
    if p >= CONFIRMED_AT:
        return best, True
    if band and p >= UNCERTAIN_FROM:
        return best, False
    return None, False


def result_for(arm: str, rec: dict, catalog: dict) -> dict | None:
    name, sure = pick(rec, *ARMS[arm])
    if not name:
        return None
    description = base.cap(catalog[name]["description"], 120)
    if sure:
        return {"status": "ok", "hits": [{"name": name, "description": description, "score": round(rec["fits"][name], 4)}]}
    return {
        "status": "uncertain",
        "hits": [{"name": name, "description": description, "confidence": "low"}],
        "message": base.UNCERTAIN_MESSAGE,
    }


def evaluate_with(model: str, arms: list[str], tag: str, suffix: str = "") -> dict:
    import report

    recs = base.records(records_dir(tag))
    catalog = base.skills()
    base.result_for = result_for  # collect() builds results through the module attribute
    out = base.collect(model, arms, recs, catalog)

    def no_agent(source: str) -> dict:
        arm_out = {}
        for r in recs:
            name, _ = pick(r, source, True)
            shown = {"status": "ok", "hits": [{"name": name, "description": base.cap(catalog[name]["description"], 120)}]} if name else None
            arm_out[r["query"]] = (shown, name, False)
        return arm_out

    out = {"L0": no_agent("local"), "S0": no_agent("scan"), **out}
    by_query = {r["query"]: r for r in recs}
    pairs = sorted(
        {
            (q, h["name"])
            for arm_out in out.values()
            for q, (result, _, _) in arm_out.items()
            if result
            for h in result["hits"]
            if h["name"] not in by_query[q]["expected"]
        }
    )
    with ThreadPoolExecutor(6) as pool:
        verdicts = dict(zip(pairs, pool.map(lambda p: report.adjudicate(p[0], catalog[p[1]]), pairs)))
    ok = lambda r, name: name in r["expected"] or verdicts.get((r["query"], name), False)
    rows = {arm: base.score(arm_out, recs, ok) for arm, arm_out in out.items()}
    pos = [r for r in recs if r["expected"]]
    neg = len(recs) - len(pos)
    print(f"{tag}, agent {model}; {len(pos)} matching, {neg} no-match; adjudicated shown pairs: {len(pairs)}")
    for source in ("local", "scan"):
        inside = sum(1 for r in pos if r["expected"][0] in r[source]) / len(pos)
        print(f"  expected skill in the {source} shortlist: {inside:.3f}")
    print(f"  scan: {statistics.mean(r['scan_tokens'] for r in recs):.0f} input tokens, p50 {statistics.median(r['ms']['scan'] for r in recs):.0f} ms; fit p50 {statistics.median(r['ms']['fit'] for r in recs):.0f} ms")
    print(f"  {'arm':4} {'useful':>7} {'junk+':>6} {'junk-':>10} {'en':>6} {'ko':>6} {'shown':>6} {'shown-':>6} {'chars':>6}")
    for arm, c in rows.items():
        print(
            f"  {arm:4} {c['useful']:7.3f} {c['junk_pos']:6.3f} {c['junk_neg']:6.3f} ({round(c['junk_neg'] * neg):2d}) "
            f"{c['useful_en']:6.3f} {c['useful_ko']:6.3f} {c['shown']:6.3f} {c['shown_neg']:6.3f} {c['chars']:6.0f}"
        )
    (WORK / f"scan-{tag}{suffix}.json").write_text(json.dumps(rows, indent=1), encoding="utf-8")
    return rows


def select(rows: dict) -> None:
    bar = rows["L"]["useful"] + 0.05
    cands = {
        a: c for a, c in rows.items()
        if a in ("S", "S9") and c["junk_neg"] <= 0.10 and c["junk_pos"] <= 0.05 and c["useful"] >= bar
    }
    print(f"\nbar {bar:.3f}; candidates {sorted(cands)}")
    if cands:
        best = max(c["useful"] for c in cands.values())
        near = [a for a, c in cands.items() if c["useful"] >= best - 0.01]
        chosen = max(near, key=lambda a: cands[a]["useful"]) if len(near) == 1 else min(near, key=lambda a: cands[a]["junk_neg"])
        print(f"  -> selected {chosen}")


if __name__ == "__main__":
    command, tag = sys.argv[1], sys.argv[2]
    if command == "record":
        record(tag)
    elif command == "evaluate":
        select(evaluate_with(base.PRIMARY, list(ARMS), tag))
    elif command == "confirm":
        evaluate_with(base.SECOND, ["L", *sys.argv[3:]], tag, "-second")
    elif command == "test":
        evaluate_with(base.PRIMARY, ["L", *sys.argv[3:]], tag)
