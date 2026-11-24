"""Dev comparison for docs/benchmarks/2026-11-24-cards-protocol.md.

    uv run python bench/scale/cards_dev.py cards                     # OPENAI_API_KEY; one card per corpus skill
    uv run --extra rerank python bench/scale/cards_dev.py record     # TYPESAFE_API_KEY; judge with card evidence
    uv run python bench/scale/cards_dev.py evaluate                  # OPENAI_API_KEY (adjudication)
"""

from __future__ import annotations

import itertools
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from skill_rag.judges import JudgeConfig, load
from skill_rag.parser import parse_skill_file

ROOT = Path(__file__).resolve().parents[2]
HERE = ROOT / "bench" / "scale"
WORK = ROOT / "var" / "bench" / "scale"
BASE_RECORDS = WORK / "precision-dev"  # description evidence, recorded earlier
CARDS = WORK / "cards"
CARD_MODEL = "gpt-6.1-terra"
CARD_BODY_CHARS = 8000
CARD_PROMPT = (
    "You are writing a card that helps decide whether an agent skill is the right "
    "one to load for a user's request. Read the skill and return JSON with: "
    "use_when: up to 3 short clauses naming the concrete tasks the skill is for; "
    "not_for: up to 2 short clauses naming nearby tasks, products, or situations "
    "it is not for, mentioning what to use instead only if the skill says so; "
    "terms: up to 8 product, tool, or file-format names the skill is about, as "
    "written in the skill. State only what the skill text supports. Keep the "
    "whole card under 60 words."
)
VARIANTS = ("description", "card", "description+card")
THRESHOLDS = (0.5, 0.6, 0.7, 0.8, 0.9, 0.95)
MARGINS = (0.0, 0.1, 0.2)
SHORTLIST = 16


def corpus_skills() -> dict[str, dict]:
    manifest = json.loads((HERE / "manifest.json").read_text(encoding="utf-8"))["accepted"]
    present = {p.name for p in (WORK / "corpus-350").iterdir()}
    skills = {}
    for a in manifest:
        if a["dir"] in present:
            parsed = parse_skill_file(WORK / "pool" / a["dir"] / "SKILL.md")
            skills[parsed.name] = {"dir": a["dir"], "name": parsed.name, "description": parsed.description, "body": parsed.body}
    return skills


def card_text(card: dict) -> str:
    parts = []
    if card.get("use_when"):
        parts.append("Use when: " + "; ".join(card["use_when"]) + ".")
    if card.get("not_for"):
        parts.append("Not for: " + "; ".join(card["not_for"]) + ".")
    if card.get("terms"):
        parts.append("Terms: " + ", ".join(card["terms"]) + ".")
    return " ".join(parts)


def make_card(skill: dict) -> dict:
    path = CARDS / f"{skill['dir']}.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    import httpx

    strings = {"type": "array", "items": {"type": "string"}}
    response = httpx.post(
        os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/") + "/responses",
        headers={"Authorization": f"Bearer {os.environ['OPENAI_API_KEY']}"},
        json={
            "model": CARD_MODEL,
            "input": [
                {"role": "developer", "content": CARD_PROMPT},
                {
                    "role": "user",
                    "content": f"Skill name: {skill['name']}\nDescription: {skill['description']}\n\n{skill['body'][:CARD_BODY_CHARS]}",
                },
            ],
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "card",
                    "strict": True,
                    "schema": {
                        "type": "object",
                        "properties": {"use_when": strings, "not_for": strings, "terms": strings},
                        "required": ["use_when", "not_for", "terms"],
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
    card = json.loads(text)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(card, ensure_ascii=False), encoding="utf-8")
    return card


def cards() -> None:
    skills = corpus_skills()
    with ThreadPoolExecutor(6) as pool:
        made = list(pool.map(make_card, skills.values()))
    lengths = sorted(len(card_text(c)) for c in made)
    print(f"cards: {len(made)}; text length median {lengths[len(lengths) // 2]}, max {lengths[-1]}")


def evidence(variant: str, skill: dict) -> str:
    card = card_text(json.loads((CARDS / f"{skill['dir']}.json").read_text(encoding="utf-8")))
    if variant == "card":
        return card
    return f"{skill['description']} {card}"


def record() -> None:
    skills = corpus_skills()
    base = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(BASE_RECORDS.glob("*.json"))]

    def one(job) -> None:
        variant, rec, source_path = job
        path = WORK / "cards-dev" / variant / source_path.name
        if path.exists():
            return
        judge = load("jev", JudgeConfig(timeout=60))
        names = list(dict.fromkeys(rec["local"] + rec["scan"]))
        candidates = [{"name": n, "description": evidence(variant, skills[n]), "agent": ""} for n in names]
        fits = dict(zip(names, judge.fits(rec["query"], candidates)))
        path.parent.mkdir(parents=True, exist_ok=True)
        out = {k: rec[k] for k in ("query", "expected", "lang", "kind", "local", "scan")}
        out["fits"] = fits
        out["tokens"] = {"fit_per_candidate": judge.last_usage["input_tokens"] / len(candidates)}
        path.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")

    paths = sorted(BASE_RECORDS.glob("*.json"))
    jobs = [(v, rec, p) for v in VARIANTS[1:] for rec, p in zip(base, paths)]
    with ThreadPoolExecutor(4) as pool:
        list(pool.map(one, jobs))
    for v in VARIANTS[1:]:
        print(f"{v}: {len(list((WORK / 'cards-dev' / v).glob('*.json')))} dev queries recorded")


def load_records(variant: str) -> list[dict]:
    directory = BASE_RECORDS if variant == "description" else WORK / "cards-dev" / variant
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted(directory.glob("*.json"))]


def decide(rec: dict, source: str, threshold: float, margin: float) -> list[str]:
    kept = sorted((n for n in rec[source] if rec["fits"][n] >= threshold), key=lambda n: rec["fits"][n], reverse=True)
    if not kept or (margin and len(kept) > 1 and rec["fits"][kept[0]] - rec["fits"][kept[1]] < margin):
        return []
    return kept[:1]


def evaluate() -> None:
    import report  # the adjudicator of the scale protocol

    skills = corpus_skills()
    by_variant = {v: load_records(v) for v in VARIANTS}
    pairs = sorted(
        {
            (r["query"], n)
            for records in by_variant.values()
            for r in records
            for source in ("local", "scan")
            for n in sorted(r[source], key=lambda n: r["fits"][n], reverse=True)[:1]
            if r["fits"][n] >= min(THRESHOLDS) and n not in r["expected"]
        }
    )
    with ThreadPoolExecutor(6) as pool:
        verdicts = dict(zip(pairs, pool.map(lambda p: report.adjudicate(p[0], skills[p[1]]), pairs)))
    print(f"adjudicated first-hit pairs: {len(pairs)}, judged to fit: {sum(verdicts.values())}\n")

    selected = {}
    grid_out = {}
    for variant, records in by_variant.items():
        pos = [r for r in records if r["expected"]]
        neg = [r for r in records if not r["expected"]]
        ok = lambda r, n: n in r["expected"] or verdicts.get((r["query"], n), False)
        rows = []
        for source, threshold, margin in itertools.product(("local", "scan"), THRESHOLDS, MARGINS):
            out = {r["query"]: decide(r, source, threshold, margin) for r in records}
            first = lambda r: out[r["query"]][0] if out[r["query"]] else None
            rows.append(
                {
                    "source": source,
                    "threshold": threshold,
                    "margin": margin,
                    "useful": sum(1 for r in pos if first(r) and ok(r, first(r))) / len(pos),
                    "junk_pos": sum(1 for r in pos if first(r) and not ok(r, first(r))) / len(pos),
                    "junk_neg": sum(1 for r in neg if first(r) and not ok(r, first(r))) / len(neg),
                    "hits": sum(len(v) for v in out.values()) / len(records),
                    "requests": 1 + (source == "scan"),
                    "tokens": sum(r["tokens"]["fit_per_candidate"] for r in records) / len(records) * SHORTLIST,
                }
            )
        grid_out[variant] = rows
        qualifying = [c for c in rows if c["junk_neg"] <= 0.10 and c["junk_pos"] <= 0.05]
        print(f"## evidence = {variant}  (dev: {len(pos)} matching, {len(neg)} no-match)")
        print(f"  {'source':6} {'thr':>5} {'useful':>7} {'junk+':>6} {'junk-':>6} {'hits':>5} {'tokens':>7}")
        for c in rows:
            if c["margin"] == 0:
                print(f"  {c['source']:6} {c['threshold']:5.2f} {c['useful']:7.3f} {c['junk_pos']:6.3f} {c['junk_neg']:6.3f} {c['hits']:5.2f} {c['tokens']:7.0f}")
        if qualifying:
            best = max(c["useful"] for c in qualifying)
            chosen = min((c for c in qualifying if c["useful"] >= best - 0.01), key=lambda c: (c["hits"], c["requests"], c["tokens"]))
            selected[variant] = chosen
            print(f"  -> best qualifying: {chosen['source']} thr={chosen['threshold']} margin={chosen['margin']} useful={chosen['useful']:.3f} junk+={chosen['junk_pos']:.3f} junk-={chosen['junk_neg']:.3f}\n")
        else:
            print("  -> no configuration qualifies\n")
    base = selected.get("description")
    best_card = max((selected[v] for v in VARIANTS[1:] if v in selected), key=lambda c: c["useful"], default=None)
    if base and best_card:
        gain = best_card["useful"] - base["useful"]
        print(f"best card configuration vs best description configuration: {gain:+.3f} useful rate -> {'ADOPT' if gain >= 0.05 else 'do not adopt'}")
    (WORK / "cards-dev-grid.json").write_text(json.dumps({"grid": grid_out, "selected": selected}, indent=1), encoding="utf-8")


if __name__ == "__main__":
    {"cards": cards, "record": record, "evaluate": evaluate}[sys.argv[1]]()
