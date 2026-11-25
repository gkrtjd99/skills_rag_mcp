"""Dev comparison for docs/benchmarks/2026-11-25-agent-protocol.md.

A model plays the agent that called search_skills and decides what to load.
Uses the judge probabilities recorded by precision_dev.py; asks no judge.

    uv run python bench/scale/agent_dev.py decide      # OPENAI_API_KEY; primary agent, every arm
    uv run python bench/scale/agent_dev.py evaluate    # OPENAI_API_KEY (adjudication)
    uv run python bench/scale/agent_dev.py confirm B:0.7:2:300   # second agent on A1 and one configuration
"""

from __future__ import annotations

import hashlib
import itertools
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from skill_rag.parser import parse_skill_file

ROOT = Path(__file__).resolve().parents[2]
HERE = ROOT / "bench" / "scale"
WORK = ROOT / "var" / "bench" / "scale"
RECORDS = WORK / "precision-dev"
ANSWERS = WORK / "agent"
PRIMARY = "gpt-6.1-terra"
SECOND = "gpt-6-astra"
CONFIRMED_AT = 0.9
CONFIRMED_CHARS = 120
AGENT_PROMPT = (
    "You are an AI coding agent working on a user's request. Before starting you "
    "searched a skill library; the search result is below. A skill is a set of "
    "instructions you can load in full with get_skill(name). Loading costs context, "
    "so load a skill only if its name and description show that it covers this "
    "specific task on the same product, platform, or technology. Hits marked "
    '"confidence": "low" are uncertain candidates that the search could not confirm. '
    "Decide which single skill to load, or none. Answer as JSON."
)
UNCERTAIN_MESSAGE = (
    "No skill was confirmed for this request. These are uncertain candidates: load "
    "one only if its description clearly covers the task; otherwise proceed without a skill."
)
ARMS = (
    ["A1"]
    + [f"B:{lo}:{m}:{d}" for lo, m, d in itertools.product((0.5, 0.7), (1, 2), (120, 300))]
    + [f"K:{n}" for n in (2, 3)]
)


def cap(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def skills() -> dict[str, dict]:
    manifest = json.loads((HERE / "manifest.json").read_text(encoding="utf-8"))["accepted"]
    out = {}
    for a in manifest:
        parsed = parse_skill_file(WORK / "pool" / a["dir"] / "SKILL.md")
        out[a["name"]] = {"name": parsed.name, "description": parsed.description, "body": parsed.body}
    return out


def records(directory: Path = RECORDS) -> list[dict]:
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted(directory.glob("*.json"))]


def confirmed(rec: dict) -> str | None:
    kept = [n for n in rec["local"] if rec["fits"][n] >= CONFIRMED_AT]
    return max(kept, key=lambda n: rec["fits"][n]) if kept else None  # max keeps the first on ties


def result_for(arm: str, rec: dict, catalog: dict) -> dict | None:
    """The search result the agent would see, or None when nothing is shown."""

    def uncertain(names: list[str], chars: int) -> dict | None:
        if not names:
            return None
        hits = [{"name": n, "description": cap(catalog[n]["description"], chars), "confidence": "low"} for n in names]
        return {"status": "uncertain", "hits": hits, "message": UNCERTAIN_MESSAGE}

    kind, *args = arm.split(":")
    if kind == "K":
        return uncertain(rec["local"][: int(args[0])], 300)
    top = confirmed(rec)
    if top:
        hit = {"name": top, "description": cap(catalog[top]["description"], CONFIRMED_CHARS), "score": round(rec["fits"][top], 4)}
        return {"status": "ok", "hits": [hit]}
    if kind == "A1":
        return None
    lo, m, d = float(args[0]), int(args[1]), int(args[2])
    band = sorted((n for n in rec["local"] if lo <= rec["fits"][n] < CONFIRMED_AT), key=lambda n: rec["fits"][n], reverse=True)
    return uncertain(band[:m], d)


def ask(model: str, query: str, result: dict) -> str | None:
    user = f"User request: {query}\n\nsearch_skills result:\n{json.dumps(result, ensure_ascii=False)}"
    key = hashlib.sha1(f"{model}\x00{AGENT_PROMPT}\x00{user}".encode()).hexdigest()
    path = ANSWERS / f"{key}.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))["load"]
    import httpx

    response = httpx.post(
        os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/") + "/responses",
        headers={"Authorization": f"Bearer {os.environ['OPENAI_API_KEY']}"},
        json={
            "model": model,
            "input": [{"role": "developer", "content": AGENT_PROMPT}, {"role": "user", "content": user}],
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "decision",
                    "strict": True,
                    "schema": {
                        "type": "object",
                        "properties": {"load": {"type": ["string", "null"]}},
                        "required": ["load"],
                        "additionalProperties": False,
                    },
                }
            },
        },
        timeout=120,
    )
    response.raise_for_status()
    text = next(
        part["text"]
        for item in response.json()["output"]
        if item.get("type") == "message"
        for part in item["content"]
        if part.get("type") == "output_text"
    )
    load = json.loads(text)["load"]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"load": load}, ensure_ascii=False), encoding="utf-8")
    return load


def collect(model: str, arms: list[str], recs: list[dict], catalog: dict) -> dict:
    """{arm: {query: (shown result or None, loaded name or None, named something not shown)}}"""
    jobs = {}
    for arm in arms:
        for rec in recs:
            result = result_for(arm, rec, catalog)
            if result:
                jobs[(rec["query"], json.dumps(result, ensure_ascii=False, sort_keys=True))] = (rec["query"], result)

    def run(job):
        for attempt in range(4):
            try:
                return ask(model, *job)
            except Exception:
                if attempt == 3:
                    raise

    keys = list(jobs)
    with ThreadPoolExecutor(6) as pool:
        answers = dict(zip(keys, pool.map(run, [jobs[k] for k in keys])))
    out = {}
    for arm in arms:
        out[arm] = {}
        for rec in recs:
            result = result_for(arm, rec, catalog)
            if not result:
                out[arm][rec["query"]] = (None, None, False)
                continue
            answer = answers[(rec["query"], json.dumps(result, ensure_ascii=False, sort_keys=True))]
            shown = {h["name"] for h in result["hits"]}
            out[arm][rec["query"]] = (result, answer if answer in shown else None, bool(answer) and answer not in shown)
    return out


def decide() -> None:
    recs, catalog = records(), skills()
    out = collect(PRIMARY, ARMS, recs, catalog)
    for arm in ARMS:
        loads = sum(1 for _, load, _ in out[arm].values() if load)
        print(f"{arm:14} shown {sum(1 for r, _, _ in out[arm].values() if r):3d}  loaded {loads:3d}")


def score(arm_out: dict, recs: list[dict], ok) -> dict:
    pos = [r for r in recs if r["expected"]]
    neg = [r for r in recs if not r["expected"]]
    load = lambda r: arm_out[r["query"]][1]
    shown = lambda r: arm_out[r["query"]][0]
    rate = lambda group, test: sum(1 for r in group if test(r)) / len(group) if group else 0.0
    chars = lambda r: sum(len(h["name"]) + len(h["description"]) for h in shown(r)["hits"]) if shown(r) else 0
    return {
        "useful": rate(pos, lambda r: load(r) and ok(r, load(r))),
        "junk_pos": rate(pos, lambda r: load(r) and not ok(r, load(r))),
        "junk_neg": rate(neg, lambda r: load(r) and not ok(r, load(r))),
        "useful_en": rate([r for r in pos if r["lang"] == "en"], lambda r: load(r) and ok(r, load(r))),
        "useful_ko": rate([r for r in pos if r["lang"] == "ko"], lambda r: load(r) and ok(r, load(r))),
        "shown": rate(recs, lambda r: bool(shown(r))),
        "shown_neg": rate(neg, lambda r: bool(shown(r))),
        "chars": sum(chars(r) for r in recs) / len(recs),
        "declined_right": rate(
            pos, lambda r: shown(r) and shown(r)["status"] == "ok" and not load(r) and ok(r, shown(r)["hits"][0]["name"])
        ),
        "off_list": sum(1 for r in recs if arm_out[r["query"]][2]),
    }


def evaluate_with(model: str, arms: list[str], recs: list[dict], tag: str) -> dict:
    import report  # the adjudicator of the scale protocol

    catalog = skills()
    out = collect(model, arms, recs, catalog)
    a0 = {r["query"]: (None, confirmed(r), False) for r in recs}
    for q, (_, name, _) in a0.items():
        if name:
            a0[q] = ({"status": "ok", "hits": [{"name": name, "description": cap(catalog[name]["description"], CONFIRMED_CHARS)}]}, name, False)
    out = {"A0": a0, **out}
    by_query = {r["query"]: r for r in recs}
    pairs = sorted(
        {
            (q, name)
            for arm_out in out.values()
            for q, (result, _, _) in arm_out.items()
            if result
            for name in (h["name"] for h in result["hits"])
            if name not in by_query[q]["expected"]
        }
    )
    with ThreadPoolExecutor(6) as pool:
        verdicts = dict(zip(pairs, pool.map(lambda p: report.adjudicate(p[0], catalog[p[1]]), pairs)))
    ok = lambda r, name: name in r["expected"] or verdicts.get((r["query"], name), False)
    rows = {arm: score(arm_out, recs, ok) for arm, arm_out in out.items()}
    pos = sum(1 for r in recs if r["expected"])
    print(f"agent {model}; {pos} matching, {len(recs) - pos} no-match; adjudicated shown pairs: {len(pairs)}")
    print(f"  {'arm':14} {'useful':>7} {'junk+':>6} {'junk-':>6} {'en':>6} {'ko':>6} {'shown':>6} {'shown-':>6} {'chars':>6} {'declR':>6} {'off':>3}")
    for arm, c in rows.items():
        print(
            f"  {arm:14} {c['useful']:7.3f} {c['junk_pos']:6.3f} {c['junk_neg']:6.3f} {c['useful_en']:6.3f} {c['useful_ko']:6.3f} "
            f"{c['shown']:6.3f} {c['shown_neg']:6.3f} {c['chars']:6.0f} {c['declined_right']:6.3f} {c['off_list']:3d}"
        )
    (WORK / f"agent-{tag}.json").write_text(json.dumps(rows, indent=1), encoding="utf-8")
    return rows


def select(rows: dict, family: str) -> str | None:
    base = rows["A0"]["useful"]
    qualifying = {a: c for a, c in rows.items() if a.startswith(family) and c["junk_neg"] <= 0.10 and c["junk_pos"] <= 0.05}
    candidates = {a: c for a, c in qualifying.items() if c["useful"] >= base + 0.05}
    print(f"family {family}: {len(qualifying)} qualify, {len(candidates)} reach A0 + 5 points ({base + 0.05:.3f})")
    if not candidates:
        return None
    best = max(c["useful"] for c in candidates.values())
    chosen = min((a for a, c in candidates.items() if c["useful"] >= best - 0.01), key=lambda a: candidates[a]["chars"])
    print(f"  -> selected {chosen}")
    return chosen


def evaluate() -> None:
    rows = evaluate_with(PRIMARY, ARMS, records(), "dev")
    print()
    for family in ("B", "K"):
        select(rows, family)


def confirm() -> None:
    evaluate_with(SECOND, ["A1", sys.argv[2]], records(), "dev-second")


if __name__ == "__main__":
    {"decide": decide, "evaluate": evaluate, "confirm": confirm}[sys.argv[1]]()
