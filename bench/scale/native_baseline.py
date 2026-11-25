"""Baseline for docs/benchmarks/2026-11-25-native-baseline-protocol.md.

Every skill's name and description goes into the agent's context; no search.

    uv run python bench/scale/native_baseline.py test ALL ALL120       # OPENAI_API_KEY
    uv run python bench/scale/native_baseline.py test ALL --second
    uv run python bench/scale/native_baseline.py dev3 ALL
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import agent_dev as base

HERE, WORK = base.HERE, base.WORK
ANSWERS = WORK / "native"
SETS = {"test": ["agent2-test3", "agent2-test3neg"], "dev3": ["scan-dev3"], "test4": ["scan-test4"]}
CHARS = {"ALL": 0, "ALL120": 120}
PROMPT = (
    "You are an AI coding agent working on a user's request. The skills available to "
    "you are listed below, one per line as name: description. A skill is a set of "
    "instructions you can load in full with get_skill(name). Loading costs context, "
    "so load a skill only if its name and description show that it covers this "
    "specific task on the same product, platform, or technology. Decide which single "
    "skill to load, or none. Answer as JSON."
)


def corpus_names() -> list[str]:
    present = {p.name for p in (WORK / "corpus-350").iterdir()}
    manifest = json.loads((HERE / "manifest.json").read_text(encoding="utf-8"))["accepted"]
    return sorted(a["name"] for a in manifest if a["dir"] in present)


def listing(catalog: dict, names: list[str], chars: int) -> str:
    def text(name: str) -> str:
        description = " ".join(catalog[name]["description"].split())
        return base.cap(description, chars) if chars else description

    return "\n".join(f"- {n}: {text(n)}" for n in names)


def ask(model: str, developer: str, query: str) -> dict:
    key = hashlib.sha1(f"{model}\x00{developer}\x00{query}".encode()).hexdigest()
    path = ANSWERS / f"{key}.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    import httpx

    for attempt in range(6):
        try:
            response = _post(httpx, model, developer, query)
        except httpx.TransportError:  # dropped connection, TLS reset, timeout
            if attempt == 5:
                raise
            time.sleep(5 * (attempt + 1))
            continue
        if response.status_code in (429, 500, 502, 503) and attempt < 5:
            time.sleep(5 * (attempt + 1))
            continue
        response.raise_for_status()
        break
    body = response.json()
    text = next(
        part["text"]
        for item in body["output"]
        if item.get("type") == "message"
        for part in item["content"]
        if part.get("type") == "output_text"
    )
    usage = body.get("usage", {})
    answer = {
        "load": json.loads(text)["load"],
        "input_tokens": usage.get("input_tokens"),
        "cached_tokens": (usage.get("input_tokens_details") or {}).get("cached_tokens"),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(answer, ensure_ascii=False), encoding="utf-8")
    return answer


def _post(httpx, model: str, developer: str, query: str):
    return httpx.post(
        os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/") + "/responses",
        headers={"Authorization": f"Bearer {os.environ['OPENAI_API_KEY']}"},
        json={
            "model": model,
            # The list comes first and is identical for every request, so the provider can cache it.
            "input": [{"role": "developer", "content": developer}, {"role": "user", "content": f"User request: {query}"}],
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
        timeout=180,
    )


def run(set_name: str, arms: list[str], model: str) -> None:
    import report

    catalog = base.skills()
    names = corpus_names()
    known = set(names)
    recs = [r for d in SETS[set_name] for r in base.records(WORK / d)]
    pos = [r for r in recs if r["expected"]]
    neg = [r for r in recs if not r["expected"]]
    print(f"{set_name}, agent {model}; {len(pos)} matching, {len(neg)} no-match; {len(names)} skills")
    print(f"  {'arm':7} {'useful':>7} {'junk+':>6} {'junk-':>10} {'en':>6} {'ko':>6} {'off':>4} {'tokens':>7} {'cached':>7}")
    out = {}
    for arm in arms:
        developer = PROMPT + "\n\n" + listing(catalog, names, CHARS[arm])
        with ThreadPoolExecutor(4) as pool:
            answers = list(pool.map(lambda r: ask(model, developer, r["query"]), recs))
        loads = {r["query"]: (a["load"] if a["load"] in known else None) for r, a in zip(recs, answers)}
        off = sum(1 for a in answers if a["load"] and a["load"] not in known)
        pairs = sorted({(r["query"], loads[r["query"]]) for r in recs if loads[r["query"]] and loads[r["query"]] not in r["expected"]})
        with ThreadPoolExecutor(6) as pool:
            verdicts = dict(zip(pairs, pool.map(lambda p: report.adjudicate(p[0], catalog[p[1]]), pairs)))
        ok = lambda r: loads[r["query"]] in r["expected"] or verdicts.get((r["query"], loads[r["query"]]), False)
        rate = lambda group, test: sum(1 for r in group if test(r)) / len(group) if group else 0.0
        useful = lambda group: rate(group, lambda r: loads[r["query"]] and ok(r))
        row = {
            "useful": useful(pos),
            "junk_pos": rate(pos, lambda r: loads[r["query"]] and not ok(r)),
            "junk_neg": rate(neg, lambda r: loads[r["query"]] and not ok(r)),
            "useful_en": useful([r for r in pos if r["lang"] == "en"]),
            "useful_ko": useful([r for r in pos if r["lang"] == "ko"]),
            "off_list": off,
            "input_tokens": sum(a["input_tokens"] or 0 for a in answers) / len(answers),
            "cached_tokens": sum(a["cached_tokens"] or 0 for a in answers) / len(answers),
        }
        out[arm] = row
        print(
            f"  {arm:7} {row['useful']:7.3f} {row['junk_pos']:6.3f} {row['junk_neg']:6.3f} ({round(row['junk_neg'] * len(neg)):2d}) "
            f"{row['useful_en']:6.3f} {row['useful_ko']:6.3f} {off:4d} {row['input_tokens']:7.0f} {row['cached_tokens']:7.0f}"
        )
    (WORK / f"native-{set_name}-{model}.json").write_text(json.dumps(out, indent=1), encoding="utf-8")


if __name__ == "__main__":
    args = [a for a in sys.argv[2:] if a != "--second"]
    run(sys.argv[1], args, base.SECOND if "--second" in sys.argv else base.PRIMARY)
