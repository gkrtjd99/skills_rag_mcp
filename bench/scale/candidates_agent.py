"""Several candidates for the agent: docs/benchmarks/2026-11-25-candidates-protocol.md.

Uses the records written by scan_agent.py; asks no judge.

    uv run python bench/scale/candidates_agent.py evaluate dev3              # OPENAI_API_KEY
    uv run python bench/scale/candidates_agent.py confirm dev3 C:scan:8:0.1  # second agent
    uv run python bench/scale/candidates_agent.py test test4 C:scan:8:0.1    # primary agent
"""

from __future__ import annotations

import itertools
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import agent_dev as base
import scan_agent

WORK = base.WORK
MESSAGE = (
    "These are the closest skills, best first. Often none of them fits: load one only if "
    "its name and description clearly cover this task; otherwise proceed without a skill."
)
ARMS = [f"C:{s}:{n}:{f}" for s, n, f in itertools.product(("scan", "local"), (3, 8), (0.1, 0.5))] + ["N:8", "N:16"]
REFERENCE = ["L", "S"]


def result_for(arm: str, rec: dict, catalog: dict) -> dict | None:
    kind, *args = arm.split(":")
    if kind in scan_agent.ARMS:
        return scan_agent.result_for(arm, rec, catalog)
    describe = lambda n: base.cap(catalog[n]["description"], 120)
    if kind == "N":
        hits = [{"name": n, "description": describe(n)} for n in rec["local"][: int(args[0])]]
    else:
        source, n, floor = args[0], int(args[1]), float(args[2])
        # sorted is stable: equal probabilities keep the shortlist order.
        names = sorted((x for x in rec[source] if rec["fits"][x] >= floor), key=lambda x: rec["fits"][x], reverse=True)[:n]
        hits = [{"name": x, "description": describe(x), "score": round(rec["fits"][x], 2)} for x in names]
    return {"status": "candidates", "hits": hits, "message": MESSAGE} if hits else None


def evaluate_with(model: str, arms: list[str], tag: str, suffix: str = "") -> dict:
    import report

    recs = base.records(scan_agent.records_dir(tag))
    catalog = base.skills()
    base.result_for = result_for  # collect() builds results through the module attribute
    out = base.collect(model, arms, recs, catalog)
    by_query = {r["query"]: r for r in recs}
    # Only what the agent chose to load needs a verdict; a long candidate list would
    # otherwise send hundreds of never-loaded pairs to the adjudicator.
    pairs = sorted(
        {
            (q, load)
            for arm_out in out.values()
            for q, (_, load, _) in arm_out.items()
            if load and load not in by_query[q]["expected"]
        }
    )
    with ThreadPoolExecutor(6) as pool:
        verdicts = dict(zip(pairs, pool.map(lambda p: report.adjudicate(p[0], catalog[p[1]]), pairs)))
    ok = lambda r, name: name in r["expected"] or verdicts.get((r["query"], name), False)
    rows = {}
    for arm, arm_out in out.items():
        row = base.score(arm_out, recs, ok)
        row.pop("declined_right")  # defined for single confirmed hits only
        rows[arm] = row
    pos = sum(1 for r in recs if r["expected"])
    neg = len(recs) - pos
    print(f"{tag}, agent {model}; {pos} matching, {neg} no-match; adjudicated loads: {len(pairs)}")
    print(f"  {'arm':16} {'useful':>7} {'junk+':>6} {'junk-':>10} {'en':>6} {'ko':>6} {'shown':>6} {'shown-':>6} {'chars':>6} {'off':>3}")
    for arm, c in rows.items():
        print(
            f"  {arm:16} {c['useful']:7.3f} {c['junk_pos']:6.3f} {c['junk_neg']:6.3f} ({round(c['junk_neg'] * neg):2d}) "
            f"{c['useful_en']:6.3f} {c['useful_ko']:6.3f} {c['shown']:6.3f} {c['shown_neg']:6.3f} {c['chars']:6.0f} {c['off_list']:3d}"
        )
    (WORK / f"candidates-{tag}{suffix}.json").write_text(json.dumps(rows, indent=1), encoding="utf-8")
    return rows


def select(rows: dict) -> None:
    bar = rows["L"]["useful"] + 0.05
    cands = {
        a: c for a, c in rows.items()
        if a not in REFERENCE and c["junk_neg"] <= 0.10 and c["junk_pos"] <= 0.05 and c["useful"] >= bar
    }
    print(f"\nbar {bar:.3f}; candidates {sorted(cands)}")
    if not cands:
        return
    best = max(c["useful"] for c in cands.values())

    def preference(arm: str):
        kind, *args = arm.split(":")
        if kind == "N":
            return (0, int(args[0]), 0.0)
        return (1 if args[0] == "scan" else 0, int(args[1]), -float(args[2]))

    print(f"  -> selected {min((a for a, c in cands.items() if c['useful'] >= best - 0.01), key=preference)}")


if __name__ == "__main__":
    command, tag = sys.argv[1], sys.argv[2]
    if command == "evaluate":
        select(evaluate_with(base.PRIMARY, REFERENCE + ARMS, tag))
    elif command == "confirm":
        evaluate_with(base.SECOND, ["L", *sys.argv[3:]], tag, "-second")
    elif command == "test":
        evaluate_with(base.PRIMARY, ["L", *sys.argv[3:]], tag)
