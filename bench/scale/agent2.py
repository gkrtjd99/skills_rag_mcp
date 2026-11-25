"""Second agent-in-the-loop experiment: docs/benchmarks/2026-11-25-agent2-protocol.md.

    uv run python bench/scale/prepare.py dev2                              # OPENAI_API_KEY, gh
    uv run --extra rerank python bench/scale/agent2.py record dev2         # TYPESAFE_API_KEY
    uv run python bench/scale/agent2.py evaluate dev2                      # OPENAI_API_KEY
    uv run python bench/scale/agent2.py confirm dev2 B:0.8:M1              # second agent
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import agent_dev as base

HERE, WORK = base.HERE, base.WORK
CORPUS = WORK / "corpus-350"
SHORTLIST = 16
M0 = base.UNCERTAIN_MESSAGE
M1 = (
    "No skill was confirmed for this request. Listed below: unconfirmed candidates only. "
    "Most unconfirmed candidates are wrong. Load one only if its name and description state "
    "this exact task on the same product or tool; if the match depends on reading the "
    "description generously, proceed without a skill."
)
MESSAGES = {"M0": M0, "M1": M1}
ARMS = ["A1", "B:0.7:M0", "B:0.7:M1", "B:0.8:M0", "B:0.8:M1", "G1", "K:300:M0", "K:120:M1"]


def records_dir(tag: str) -> Path:
    return WORK / f"agent2-{tag}"


def record(tag: str) -> None:
    from skill_rag import corpus as corpus_mod
    from skill_rag import retrieve
    from skill_rag import sync as sync_mod
    from skill_rag.judges import JudgeConfig, load

    rows = [json.loads(line) for line in (HERE / f"{tag}-queries.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    with tempfile.TemporaryDirectory(prefix="skill-rag-agent2-") as tmp:
        os.environ["SKILL_RAG_INDEX_PATH"] = str(Path(tmp) / "index.lance")
        corpus_mod.CORPUS_PATH = CORPUS.resolve()
        sync_mod.reset_cache()
        sync_mod.sync_if_stale(ttl=0)
        local = {r["query"]: (retrieve.shortlist(r["query"], SHORTLIST), retrieve.search(r["query"], k=5)) for r in rows}
        sync_mod.reset_cache()

    def one(r: dict) -> None:
        path = records_dir(tag) / f"{hashlib.sha1(r['query'].encode()).hexdigest()}.json"
        if path.exists():
            return
        candidates, gate = local[r["query"]]
        judge = load("jev", JudgeConfig(timeout=60))
        fits = dict(zip((c["name"] for c in candidates), judge.fits(r["query"], candidates)))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps({**r, "local": [c["name"] for c in candidates], "fits": fits, "gate": gate}, ensure_ascii=False),
            encoding="utf-8",
        )

    def retried(r: dict) -> None:
        for attempt in range(4):
            try:
                return one(r)
            except Exception:
                if attempt == 3:
                    raise

    with ThreadPoolExecutor(4) as pool:
        list(pool.map(retried, rows))
    print(f"recorded {len(list(records_dir(tag).glob('*.json')))} of {len(rows)} {tag} requests")


def result_for(arm: str, rec: dict, catalog: dict) -> dict | None:
    def uncertain(names: list[str], chars: int, message: str) -> dict | None:
        if not names:
            return None
        hits = [{"name": n, "description": base.cap(catalog[n]["description"], chars), "confidence": "low"} for n in names]
        return {"status": "uncertain", "hits": hits, "message": MESSAGES[message]}

    kind, *args = arm.split(":")
    if kind == "G1":
        gate = rec["gate"]
        if gate["status"] != "ok":
            return None
        return {"status": "ok", "hits": [{k: h[k] for k in ("name", "description", "score")} for h in gate["hits"]]}
    if kind == "K":
        return uncertain(rec["local"][:3], int(args[0]), args[1])
    top = base.confirmed(rec)
    if top:
        hit = {"name": top, "description": base.cap(catalog[top]["description"], base.CONFIRMED_CHARS), "score": round(rec["fits"][top], 4)}
        return {"status": "ok", "hits": [hit]}
    if kind == "A1":
        return None
    lo = float(args[0])
    band = [n for n in rec["local"] if lo <= rec["fits"][n] < base.CONFIRMED_AT]
    return uncertain([max(band, key=lambda n: rec["fits"][n])] if band else [], 120, args[1])


def evaluate_with(model: str, arms: list[str], tag: str, suffix: str = "") -> dict:
    import report

    recs = base.records(records_dir(tag))
    catalog = base.skills()
    base.result_for = result_for  # collect() builds results through the module attribute
    out = base.collect(model, arms, recs, catalog)

    def fixed(pick) -> dict:
        arm_out = {}
        for r in recs:
            name = pick(r)
            shown = {"status": "ok", "hits": [{"name": name, "description": base.cap(catalog[name]["description"], 120)}]} if name else None
            arm_out[r["query"]] = (shown, name, False)
        return arm_out

    out = {
        "A0": fixed(base.confirmed),
        "G0": fixed(lambda r: r["gate"]["hits"][0]["name"] if r["gate"]["status"] == "ok" else None),
        **out,
    }
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
    pos = sum(1 for r in recs if r["expected"])
    neg = len(recs) - pos
    print(f"{tag}, agent {model}; {pos} matching, {neg} no-match; adjudicated shown pairs: {len(pairs)}")
    print(f"  {'arm':10} {'useful':>7} {'junk+':>6} {'junk-':>10} {'en':>6} {'ko':>6} {'shown':>6} {'shown-':>6} {'chars':>6} {'declR':>6} {'off':>3}")
    for arm, c in rows.items():
        print(
            f"  {arm:10} {c['useful']:7.3f} {c['junk_pos']:6.3f} {c['junk_neg']:6.3f} ({round(c['junk_neg'] * neg):2d}) {c['useful_en']:6.3f} {c['useful_ko']:6.3f} "
            f"{c['shown']:6.3f} {c['shown_neg']:6.3f} {c['chars']:6.0f} {c['declined_right']:6.3f} {c['off_list']:3d}"
        )
    (WORK / f"agent2-{tag}{suffix}.json").write_text(json.dumps(rows, indent=1), encoding="utf-8")
    return rows


def qualifies(c: dict) -> bool:
    return c["junk_neg"] <= 0.10 and c["junk_pos"] <= 0.05


def select(rows: dict) -> None:
    bar = rows["A0"]["useful"] + 0.05
    b = {a: c for a, c in rows.items() if a.startswith("B:") and qualifies(c) and c["useful"] >= bar}
    print(f"\nB: bar {bar:.3f}; candidates {sorted(b)}")
    if b:
        best = max(c["useful"] for c in b.values())
        near = [a for a, c in b.items() if c["useful"] >= best - 0.01]
        chosen = min(near, key=lambda a: (b[a]["chars"], -float(a.split(":")[1]), a.split(":")[2] != "M1"))
        print(f"  -> selected {chosen}")
    g1 = rows["G1"]
    k = {
        a: c
        for a, c in rows.items()
        if a.startswith("K:") and qualifies(c) and (not qualifies(g1) or c["useful"] >= g1["useful"] + 0.05)
    }
    print(f"K: G1 {'qualifies' if qualifies(g1) else 'does not qualify'} (useful {g1['useful']:.3f}); candidates {sorted(k)}")
    if k:
        print(f"  -> selected {max(k, key=lambda a: k[a]['useful'])}")


if __name__ == "__main__":
    command, tag = sys.argv[1], sys.argv[2]
    if command == "record":
        record(tag)
    elif command == "evaluate":
        select(evaluate_with(base.PRIMARY, ARMS, tag))
    elif command == "confirm":
        evaluate_with(base.SECOND, ["A1", "G1", *sys.argv[3:]], tag, "-second")
    elif command == "test":  # both arms' baselines plus the adopted configurations, primary agent
        evaluate_with(base.PRIMARY, ["A1", "G1", *sys.argv[3:]], tag)
