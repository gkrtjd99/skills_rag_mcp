"""Score the scale benchmark: strict and adjudicated metrics with bootstrap CIs.

Reads var/bench/scale/out-<size>.json written by bench/jev_rerank_ab.py.
Rules live in docs/benchmarks/2026-11-24-scale-protocol.md.

    uv run python bench/scale/report.py            # needs OPENAI_API_KEY for adjudication
    uv run python bench/scale/report.py --strict   # no API calls
"""

from __future__ import annotations

import hashlib
import json
import os
import random
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from skill_rag.parser import parse_skill_file

ROOT = Path(__file__).resolve().parents[2]
HERE = ROOT / "bench" / "scale"
WORK = ROOT / "var" / "bench" / "scale"
SEED = 20261124
RESAMPLES = 2000
ADJ_MODEL = "gpt-6.2-sol"
ADJ_BODY_CHARS = 2000
ADJ_PROMPT = (
    "You are checking a skill recommendation. You get a user's request and one "
    "agent skill (name, description, and the opening of its instructions). "
    "Decide whether loading this skill would genuinely help with this specific "
    "request: it must cover the same task on the same product, platform, or "
    "technology. Sharing a topic or vocabulary is not enough. Answer as JSON."
)


def adjudicate(query: str, skill: dict) -> bool:
    key = hashlib.sha1(f"{query}\x00{skill['name']}".encode()).hexdigest()
    path = WORK / "adjudication" / f"{key}.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))["fits"]
    import httpx

    response = httpx.post(
        os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/") + "/responses",
        headers={"Authorization": f"Bearer {os.environ['OPENAI_API_KEY']}"},
        json={
            "model": ADJ_MODEL,
            "input": [
                {"role": "developer", "content": ADJ_PROMPT},
                {
                    "role": "user",
                    "content": (
                        f"Request: {query}\n\nSkill name: {skill['name']}\n"
                        f"Description: {skill['description']}\n\n"
                        f"Instructions (opening):\n{skill['body'][:ADJ_BODY_CHARS]}"
                    ),
                },
            ],
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "verdict",
                    "strict": True,
                    "schema": {
                        "type": "object",
                        "properties": {"fits": {"type": "boolean"}},
                        "required": ["fits"],
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
    fits = bool(json.loads(text)["fits"])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"query": query, "skill": skill["name"], "fits": fits}, ensure_ascii=False), encoding="utf-8")
    return fits


def interval(flags: list[bool]) -> tuple[float, float, float]:
    """Mean and 95% percentile-bootstrap interval of a list of booleans."""
    if not flags:
        return (float("nan"),) * 3
    rng = random.Random(SEED)
    n = len(flags)
    means = sorted(sum(rng.choices(flags, k=n)) / n for _ in range(RESAMPLES))
    return sum(flags) / n, means[int(0.025 * RESAMPLES)], means[int(0.975 * RESAMPLES) - 1]


def cell(stat: tuple[float, float, float]) -> str:
    return f"{stat[0]:.3f} ({stat[1]:.2f}-{stat[2]:.2f})"


def main() -> int:
    strict_only = "--strict" in sys.argv
    # --prefix final scores var/bench/scale/final-<size>.json instead of out-<size>.json
    prefix = sys.argv[sys.argv.index("--prefix") + 1] if "--prefix" in sys.argv else "out"
    manifest = json.loads((HERE / "manifest.json").read_text(encoding="utf-8"))["accepted"]
    split = json.loads((HERE / "split.json").read_text(encoding="utf-8"))
    skills = {}
    for a in manifest:
        record = parse_skill_file(WORK / "pool" / a["dir"] / "SKILL.md")
        skills[a["name"]] = {"name": record.name, "description": record.description, "body": record.body}

    runs = {}
    for size in split["sizes"]:
        path = WORK / f"{prefix}-{size}.json"
        if path.exists():
            runs[size] = json.loads(path.read_text(encoding="utf-8"))["records"]
    arms = [a for a in ("gate", "jev", "openai") if runs and a in next(iter(runs.values()))[0]["hits"]]
    for records in runs.values():  # the negatives of a later test set are outside the pool
        for r in records:
            for arm in arms:
                assert all(n in skills for n in r["hits"][arm][:1])

    verdict: dict[tuple[str, str], bool] = {}
    if not strict_only:
        pairs = set()
        for records in runs.values():
            for r in records:
                for arm in arms:
                    hits = r["hits"][arm]
                    if hits and hits[0] not in r["expected"]:
                        pairs.add((r["query"], hits[0]))
        ordered = sorted(pairs)
        with ThreadPoolExecutor(6) as pool:
            results = list(pool.map(lambda p: adjudicate(p[0], skills[p[1]]), ordered))
        verdict = dict(zip(ordered, results))
        print(f"adjudicated pairs: {len(ordered)}, judged to fit: {sum(results)}\n")

    def fits(r: dict, arm: str) -> bool:
        hits = r["hits"][arm]
        return bool(hits) and verdict.get((r["query"], hits[0]), False)

    summary: dict = {}
    for scope, keep in (("all", lambda r: True), ("en", lambda r: r["lang"] == "en"), ("ko", lambda r: r["lang"] == "ko")):
        print(f"### {scope}\n")
        head = "| Skills | Arm | recall@1 | recall@5 | no-match | adj. recall@1 | adj. no-match | junk on positives | junk on negatives | hits | resp. chars | p50 ms |"
        print(head + "\n|" + "---:|" * 12)
        for size, records in runs.items():
            records = [r for r in records if keep(r)]
            pos = [r for r in records if r["expected"]]
            neg = [r for r in records if not r["expected"]]
            for arm in arms:
                top1 = [bool(r["hits"][arm]) and r["hits"][arm][0] in r["expected"] for r in pos]
                top5 = [any(n in r["expected"] for n in r["hits"][arm][:5]) for r in pos]
                none = [not r["hits"][arm] for r in neg]
                adj1 = [a or fits(r, arm) for a, r in zip(top1, pos)]
                adjn = [a or fits(r, arm) for a, r in zip(none, neg)]
                # Junk: the first returned skill does not fit (precision protocol).
                junk_pos = [bool(r["hits"][arm]) and not a for a, r in zip(adj1, pos)]
                junk_neg = [not a for a in adjn]
                returned = [len(r["hits"][arm]) for r in records]
                chars = [r["resp_chars"][arm] for r in records]
                lat = sorted(r["ms"][arm] for r in records)
                stats = {
                    "recall@1": interval(top1),
                    "recall@5": interval(top5),
                    "no_match": interval(none),
                    "adj_recall@1": interval(adj1),
                    "adj_no_match": interval(adjn),
                    "junk_pos": interval(junk_pos),
                    "junk_neg": interval(junk_neg),
                    "hits": sum(returned) / len(returned),
                    "resp_chars": sum(chars) / len(chars),
                    "p50_ms": lat[len(lat) // 2],
                    "n_pos": len(pos),
                    "n_neg": len(neg),
                }
                summary[f"{scope}/{size}/{arm}"] = stats
                adj = (
                    f"{cell(stats['adj_recall@1'])} | {cell(stats['adj_no_match'])} | "
                    f"{cell(stats['junk_pos'])} | {cell(stats['junk_neg'])}"
                    if not strict_only
                    else "- | - | - | -"
                )
                print(
                    f"| {size} | {arm} | {cell(stats['recall@1'])} | {stats['recall@5'][0]:.3f} | "
                    f"{cell(stats['no_match'])} | {adj} | {stats['hits']:.2f} | {stats['resp_chars']:.0f} | {stats['p50_ms']:.0f} |"
                )
        print()
    (WORK / f"report-{prefix}.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
