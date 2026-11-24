"""Dev exploration for docs/benchmarks/2026-11-24-precision-protocol.md.

Phase 1 (`record`) calls the judge once per dev query and stores every
probability a decision rule could need. Phase 2 (`evaluate`) scores decision
rules offline against those records and applies the selection rule.

    uv run --extra rerank python bench/scale/precision_dev.py record     # TYPESAFE_API_KEY
    uv run python bench/scale/precision_dev.py evaluate                  # OPENAI_API_KEY (adjudication)
"""

from __future__ import annotations

import hashlib
import itertools
import json
import os
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from skill_rag import corpus as corpus_mod
from skill_rag import index as index_mod
from skill_rag import retrieve
from skill_rag import sync as sync_mod
from skill_rag.judges import JudgeConfig, load
from skill_rag.parser import parse_skill_file

ROOT = Path(__file__).resolve().parents[2]
HERE = ROOT / "bench" / "scale"
WORK = ROOT / "var" / "bench" / "scale"
RECORDS = WORK / "precision-dev"
CORPUS = WORK / "corpus-350"
SHORTLIST = 16
VERIFY_TOP = 3
VERIFY_BODY_CHARS = 1500
THRESHOLDS = (0.5, 0.6, 0.7, 0.8, 0.9, 0.95)
MARGINS = (0.0, 0.1, 0.2)
VERIFY_AT = (0.5, 0.7, 0.9)


def verify_question(name: str, description: str, body: str) -> dict:
    return {
        "type": "noul",
        "instructions": (
            f"Would loading the skill '{name}' genuinely help with the task in `request`: "
            "the same task on the same product, platform, or technology? Sharing a topic "
            f"or vocabulary is not enough. Skill description: {description[:1500]} "
            f"Opening of its instructions: {body[:VERIFY_BODY_CHARS]}"
        ),
    }


def dev_rows() -> list[dict]:
    rows = []
    for name in ("dev-queries.jsonl", "dev-negatives.jsonl"):
        for line in (HERE / name).read_text(encoding="utf-8").splitlines():
            if line.strip():
                rows.append(json.loads(line))
    return rows


def record_path(query: str) -> Path:
    return RECORDS / f"{hashlib.sha1(query.encode()).hexdigest()}.json"


def record() -> None:
    rows = dev_rows()
    with tempfile.TemporaryDirectory(prefix="skill-rag-precision-") as tmp:
        os.environ["SKILL_RAG_INDEX_PATH"] = str(Path(tmp) / "index.lance")
        corpus_mod.CORPUS_PATH = CORPUS.resolve()
        sync_mod.reset_cache()
        sync_mod.sync_if_stale(ttl=0)
        indexed = index_mod.list_indexed()
        bodies = {r["name"]: parse_skill_file(Path(r["path"])).body for r in indexed}
        total = len(indexed)
        local = {}
        for r in rows:
            everything = retrieve.shortlist(r["query"], total)
            local[r["query"]] = (retrieve.shortlist(r["query"], SHORTLIST), everything)
        sync_mod.reset_cache()

    def one(r: dict) -> None:
        path = record_path(r["query"])
        if path.exists():
            return
        judge = load("jev", JudgeConfig(timeout=60))
        top_local, everything = local[r["query"]]
        t0 = time.monotonic()
        coarse = judge.scan(r["query"], everything)
        scan_ms = (time.monotonic() - t0) * 1000
        order = sorted(range(len(everything)), key=lambda i: coarse[i], reverse=True)
        top_scan = [everything[i] for i in order[:SHORTLIST]]
        union = {c["name"]: c for c in top_local + top_scan}
        candidates = list(union.values())
        t0 = time.monotonic()
        fits = dict(zip(union, judge.fits(r["query"], candidates)))
        fit_ms = (time.monotonic() - t0) * 1000
        fit_tokens = judge.last_usage["input_tokens"]

        def leaders(shortlist):
            return sorted((c["name"] for c in shortlist), key=lambda n: fits[n], reverse=True)[:VERIFY_TOP]

        to_verify = list(dict.fromkeys(leaders(top_local) + leaders(top_scan)))
        questions = {
            f"v{i}": verify_question(n, union[n]["description"], bodies[n]) for i, n in enumerate(to_verify)
        }
        t0 = time.monotonic()
        response = judge._get_client().system_one({"request": r["query"]}, questions)
        verify_ms = (time.monotonic() - t0) * 1000
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {
                    **r,
                    "local": [c["name"] for c in top_local],
                    "scan": [c["name"] for c in top_scan],
                    "fits": fits,
                    "verify": {n: float(response.nouls[f"v{i}"].noul) for i, n in enumerate(to_verify)},
                    "tokens": {
                        "scan": judge.last_scan_usage["input_tokens"],
                        "fit_per_candidate": fit_tokens / len(candidates),
                        "verify_per_candidate": response.usage.input_tokens / len(to_verify),
                    },
                    "ms": {"scan": scan_ms, "fit": fit_ms, "verify": verify_ms},
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

    with ThreadPoolExecutor(4) as pool:
        list(pool.map(one, rows))
    print(f"recorded {len(list(RECORDS.glob('*.json')))} dev queries")


def decide(rec: dict, source: str, threshold: float, margin: float, verify: str, verify_at: float) -> list[str]:
    kept = sorted((n for n in rec[source] if rec["fits"][n] >= threshold), key=lambda n: rec["fits"][n], reverse=True)
    if not kept:
        return []
    if margin and len(kept) > 1 and rec["fits"][kept[0]] - rec["fits"][kept[1]] < margin:
        return []
    if verify == "none":
        return kept
    for name in kept[: 1 if verify == "top1" else VERIFY_TOP]:
        if rec["verify"].get(name, 0.0) >= verify_at:
            return [name]
    return []


def evaluate() -> None:
    import report  # the adjudicator of the scale protocol

    records = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(RECORDS.glob("*.json"))]
    manifest = json.loads((HERE / "manifest.json").read_text(encoding="utf-8"))["accepted"]
    skills = {}
    for a in manifest:
        parsed = parse_skill_file(WORK / "pool" / a["dir"] / "SKILL.md")
        skills[a["name"]] = {"name": parsed.name, "description": parsed.description, "body": parsed.body}
    pairs = sorted(
        {
            (r["query"], n)
            for r in records
            for source in ("local", "scan")
            for n in sorted(r[source], key=lambda n: r["fits"][n], reverse=True)[:VERIFY_TOP]
            if r["fits"][n] >= min(THRESHOLDS) and n not in r["expected"]
        }
    )
    with ThreadPoolExecutor(6) as pool:
        verdicts = dict(zip(pairs, pool.map(lambda p: report.adjudicate(p[0], skills[p[1]]), pairs)))
    print(f"adjudicated pairs: {len(pairs)}, judged to fit: {sum(verdicts.values())}")
    pos = [r for r in records if r["expected"]]
    neg = [r for r in records if not r["expected"]]
    print(f"dev positives {len(pos)}, dev negatives {len(neg)}\n")

    def ok(r: dict, name: str) -> bool:
        return name in r["expected"] or verdicts.get((r["query"], name), False)

    rows = []
    grid = itertools.product(("local", "scan"), THRESHOLDS, MARGINS, ("none", "top1", "top3"), VERIFY_AT)
    for source, threshold, margin, verify, verify_at in grid:
        if verify == "none" and verify_at != VERIFY_AT[0]:
            continue
        out = {r["query"]: decide(r, source, threshold, margin, verify, verify_at) for r in records}
        useful = sum(1 for r in pos if out[r["query"]] and ok(r, out[r["query"]][0])) / len(pos)
        junk_pos = sum(1 for r in pos if out[r["query"]] and not ok(r, out[r["query"]][0])) / len(pos)
        junk_neg = sum(1 for r in neg if out[r["query"]] and not ok(r, out[r["query"]][0])) / len(neg)
        strict = sum(1 for r in pos if out[r["query"]][:1] == r["expected"]) / len(pos)
        nothing_neg = sum(1 for r in neg if not out[r["query"]]) / len(neg)
        hits = sum(len(v) for v in out.values()) / len(records)
        requests = 1 + (source == "scan") + (verify != "none")
        tokens = sum(
            (r["tokens"]["scan"] if source == "scan" else 0)
            + r["tokens"]["fit_per_candidate"] * SHORTLIST
            + (r["tokens"]["verify_per_candidate"] * (1 if verify == "top1" else VERIFY_TOP) if verify != "none" else 0)
            for r in records
        ) / len(records)
        rows.append(
            {
                "source": source, "threshold": threshold, "margin": margin, "verify": verify,
                "verify_at": verify_at if verify != "none" else None,
                "useful": useful, "junk_pos": junk_pos, "junk_neg": junk_neg, "strict_recall1": strict,
                "nothing_on_neg": nothing_neg, "hits": hits, "requests": requests, "tokens": tokens,
            }
        )

    def show(title: str, selection: list[dict]) -> None:
        print(title)
        print(f"  {'source':6} {'thr':>5} {'margin':>6} {'verify':>10} {'useful':>7} {'junk+':>6} {'junk-':>6} {'strict@1':>8} {'none-':>6} {'hits':>5} {'req':>3} {'tokens':>7}")
        for c in selection:
            v = c["verify"] if c["verify"] == "none" else f"{c['verify']}@{c['verify_at']}"
            print(
                f"  {c['source']:6} {c['threshold']:5.2f} {c['margin']:6.1f} {v:>10} {c['useful']:7.3f} {c['junk_pos']:6.3f} "
                f"{c['junk_neg']:6.3f} {c['strict_recall1']:8.3f} {c['nothing_on_neg']:6.3f} {c['hits']:5.2f} {c['requests']:3d} {c['tokens']:7.0f}"
            )
        print()

    plain = [c for c in rows if c["margin"] == 0 and c["verify"] == "none"]
    show("threshold only (no margin, no verification):", plain)
    qualifying = [c for c in rows if c["junk_neg"] <= 0.10 and c["junk_pos"] <= 0.05]
    order = lambda c: (-c["useful"], c["hits"], c["requests"], c["tokens"])
    if qualifying:
        best = max(c["useful"] for c in qualifying)
        chosen = min((c for c in qualifying if c["useful"] >= best - 0.01), key=lambda c: (c["hits"], c["requests"], c["tokens"]))
        show(f"qualifying configurations: {len(qualifying)}; top 12 by useful rate:", sorted(qualifying, key=order)[:12])
        show("SELECTED (rule 2):", [chosen])
    else:
        fallback = [c for c in rows if c["useful"] >= 0.60]
        chosen = min(fallback, key=lambda c: (c["junk_neg"], -c["useful"]))
        show("no configuration qualifies; lowest junk on negatives with useful >= 0.60 (rule 3):", [chosen])
    (WORK / "precision-dev-grid.json").write_text(json.dumps({"rows": rows, "selected": chosen}, indent=1), encoding="utf-8")


if __name__ == "__main__":
    {"record": record, "evaluate": evaluate}[sys.argv[1]]()
