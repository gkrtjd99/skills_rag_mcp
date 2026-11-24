"""Dev experiment for docs/benchmarks/2026-11-24-retrieval-protocol.md.

    uv run python bench/scale/retrieval_dev.py synth        # OPENAI_API_KEY; synthetic requests per skill
    SKILL_RAG_LOCAL_FILES_ONLY=0 uv run python bench/scale/retrieval_dev.py shortlists   # local; downloads bge-m3 once
    uv run --extra rerank python bench/scale/retrieval_dev.py judge   # TYPESAFE_API_KEY; only pairs not judged before
    uv run python bench/scale/retrieval_dev.py evaluate               # OPENAI_API_KEY (adjudication)
"""

from __future__ import annotations

import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from skill_rag.parser import parse_skill_file

ROOT = Path(__file__).resolve().parents[2]
HERE = ROOT / "bench" / "scale"
WORK = ROOT / "var" / "bench" / "scale"
OUT = WORK / "retrieval-dev"
SYNTH_MODEL = "gpt-6.1-terra"
EMBEDDERS = {"E": "intfloat/multilingual-e5-base", "B": "BAAI/bge-m3"}
CONTENTS = {"0": None, "1": "description", "2": "body"}
CONDITIONS = [f"{e}{c}" for e in EMBEDDERS for c in CONTENTS]
ORDER_OF_COST = ["E1", "E2", "B0", "B1", "B2"]
SHORTLIST = 16
DENSE_LIMIT = 64  # max(16 * 4, 20), as in the rerank path
RRF_K = 60
JUNK_NEG, JUNK_POS, ADOPT = 0.10, 0.05, 0.05


def synth_prompt(variant: str) -> str:
    given = "the name and description" if variant == "description" else "the name, description, and instructions"
    return (
        f"You are given {given} of an agent skill. Write 5 requests in English and 5 in Korean "
        "that a user might type to an AI agent when this skill is what they need. "
        "Each is one sentence describing the user's own task, in varied wording, "
        "without the skill's name. Use only what the text says the skill covers."
    )


def corpus_records() -> dict:
    manifest = json.loads((HERE / "manifest.json").read_text(encoding="utf-8"))["accepted"]
    present = {p.name for p in (WORK / "corpus-350").iterdir()}
    return {
        a["dir"]: parse_skill_file(WORK / "pool" / a["dir"] / "SKILL.md")
        for a in manifest
        if a["dir"] in present
    }


def make_synth(job) -> dict:
    variant, directory, record = job
    path = WORK / "synth" / variant / f"{directory}.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    import httpx

    text = f"Skill name: {record.name}\nDescription: {record.description}"
    if variant == "body":
        text += f"\n\n{record.body[:8000]}"
    strings = {"type": "array", "items": {"type": "string"}, "minItems": 5, "maxItems": 5}
    response = httpx.post(
        os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/") + "/responses",
        headers={"Authorization": f"Bearer {os.environ['OPENAI_API_KEY']}"},
        json={
            "model": SYNTH_MODEL,
            "input": [{"role": "developer", "content": synth_prompt(variant)}, {"role": "user", "content": text}],
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "requests",
                    "strict": True,
                    "schema": {
                        "type": "object",
                        "properties": {"en": strings, "ko": strings},
                        "required": ["en", "ko"],
                        "additionalProperties": False,
                    },
                }
            },
        },
        timeout=120,
    )
    response.raise_for_status()
    body = response.json()
    out = json.loads(
        next(
            part["text"]
            for item in body["output"]
            if item.get("type") == "message"
            for part in item["content"]
            if part.get("type") == "output_text"
        )
    )
    out["input_tokens"] = (body.get("usage") or {}).get("input_tokens")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    return out


def synth() -> None:
    records = corpus_records()
    jobs = [(v, d, r) for v in ("description", "body") for d, r in records.items()]
    with ThreadPoolExecutor(6) as pool:
        made = list(pool.map(make_synth, jobs))
    for variant in ("description", "body"):
        part = [m for (v, _, _), m in zip(jobs, made) if v == variant]
        print(f"{variant}: {len(part)} skills, input tokens {sum(m.get('input_tokens') or 0 for m in part)}")


def dev_rows() -> list[dict]:
    rows = []
    for name in ("dev-queries.jsonl", "dev-negatives.jsonl"):
        rows += [json.loads(line) for line in (HERE / name).read_text(encoding="utf-8").splitlines() if line.strip()]
    return rows


def shortlists() -> None:
    import numpy as np

    from skill_rag.embed import encode
    from skill_rag.normalize import expand_for_retrieval, normalize_for_dense
    from skill_rag.sparse import BM25, tokenize

    records = corpus_records()
    directories = sorted(records)
    names = [records[d].name for d in directories]
    rows = dev_rows()
    queries = [expand_for_retrieval(normalize_for_dense(r["query"])) for r in rows]
    OUT.mkdir(parents=True, exist_ok=True)
    timing = {}
    for e_key, model in EMBEDDERS.items():
        t0 = time.monotonic()
        passages = encode([records[d].dense_text() for d in directories], name=model, mode="passage")
        base_index_s = time.monotonic() - t0
        query_vectors = encode(queries, name=model, mode="query")
        for c_key, variant in CONTENTS.items():
            condition = f"{e_key}{c_key}"
            synthetic = [[] for _ in directories]
            extra_s = 0.0
            dense = passages @ query_vectors.T  # skills x queries
            if variant:
                for i, d in enumerate(directories):
                    made = json.loads((WORK / "synth" / variant / f"{d}.json").read_text(encoding="utf-8"))
                    synthetic[i] = made["en"] + made["ko"]
                flat = [normalize_for_dense(s) for group in synthetic for s in group]
                t0 = time.monotonic()
                vectors = encode(flat, name=model, mode="query")  # query-like text, matched query to query
                extra_s = time.monotonic() - t0
                owner = np.repeat(np.arange(len(directories)), [len(g) for g in synthetic])
                scores = vectors @ query_vectors.T
                for i in range(len(directories)):
                    dense[i] = np.maximum(dense[i], scores[owner == i].max(axis=0))
            bm25 = BM25([tokenize(records[d].embed_text() + "\n" + "\n".join(synthetic[i])) for i, d in enumerate(directories)])
            result = {}
            t0 = time.monotonic()
            for q_index, (row, query) in enumerate(zip(rows, queries)):
                dense_order = list(np.argsort(-dense[:, q_index], kind="stable")[:DENSE_LIMIT])
                dense_rank = {i: rank for rank, i in enumerate(dense_order)}
                sparse_scores = bm25.scores(tokenize(query))
                sparse_order = [i for i in sorted(range(len(names)), key=lambda i: -sparse_scores[i]) if sparse_scores[i] > 0]
                sparse_rank = {i: rank for rank, i in enumerate(sparse_order)}
                fused = lambda i: (1.0 / (RRF_K + dense_rank[i]) if i in dense_rank else 0.0) + (
                    1.0 / (RRF_K + sparse_rank[i]) if i in sparse_rank else 0.0
                )
                order = sorted(range(len(names)), key=fused, reverse=True)
                result[row["query"]] = [names[i] for i in order[:SHORTLIST]]
            timing[condition] = {
                "index_seconds": round(base_index_s + extra_s, 1),
                "fusion_ms_per_query": round((time.monotonic() - t0) * 1000 / len(rows), 1),
            }
            (OUT / f"shortlist-{condition}.json").write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
            positives = [r for r in rows if r["expected"]]
            recall = sum(r["expected"][0] in result[r["query"]] for r in positives) / len(positives)
            print(f"{condition}: top-16 recall {recall:.3f}  {timing[condition]}")
    (OUT / "timing.json").write_text(json.dumps(timing, indent=1), encoding="utf-8")


def load_fits() -> dict:
    path = OUT / "fits.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    fits: dict = {}
    for record in (WORK / "precision-dev").glob("*.json"):
        r = json.loads(record.read_text(encoding="utf-8"))
        fits[r["query"]] = dict(r["fits"])
    return fits


def judge() -> None:
    from skill_rag.judges import JudgeConfig, load

    by_name = {r.name: r for r in corpus_records().values()}
    fits = load_fits()
    needed: dict[str, set] = {}
    for condition in CONDITIONS:
        for query, names in json.loads((OUT / f"shortlist-{condition}.json").read_text(encoding="utf-8")).items():
            needed.setdefault(query, set()).update(n for n in names if n not in fits.get(query, {}))
    jobs = [(q, sorted(missing)) for q, missing in needed.items() if missing]
    print(f"requests needing new judgments: {len(jobs)}, pairs: {sum(len(m) for _, m in jobs)}")

    def one(job):
        query, missing = job
        jev = load("jev", JudgeConfig(timeout=90))
        candidates = [{"name": n, "description": by_name[n].description, "agent": ""} for n in missing]
        return query, dict(zip(missing, jev.fits(query, candidates))), jev.last_usage["input_tokens"]

    with ThreadPoolExecutor(4) as pool:
        results = list(pool.map(one, jobs))
    for query, new, _ in results:
        fits.setdefault(query, {}).update(new)
    (OUT / "fits.json").write_text(json.dumps(fits, ensure_ascii=False), encoding="utf-8")
    print(f"input tokens for new judgments: {sum(t for _, _, t in results)}")


def evaluate() -> None:
    import report  # the adjudicator of the scale protocol

    rows = dev_rows()
    fits = load_fits()
    by_name = {r.name: {"name": r.name, "description": r.description, "body": r.body} for r in corpus_records().values()}
    lists = {c: json.loads((OUT / f"shortlist-{c}.json").read_text(encoding="utf-8")) for c in CONDITIONS}
    timing = json.loads((OUT / "timing.json").read_text(encoding="utf-8"))

    def first(condition: str, row: dict):
        names = lists[condition][row["query"]]
        lead = max(names, key=lambda n: fits[row["query"]][n])
        return lead if fits[row["query"]][lead] >= 0.9 else None

    pairs = sorted({(r["query"], first(c, r)) for c in CONDITIONS for r in rows if first(c, r) and first(c, r) not in r["expected"]})
    with ThreadPoolExecutor(6) as pool:
        verdicts = dict(zip(pairs, pool.map(lambda p: report.adjudicate(p[0], by_name[p[1]]), pairs)))
    ok = lambda r, n: n in r["expected"] or verdicts.get((r["query"], n), False)
    pos = [r for r in rows if r["expected"]]
    neg = [r for r in rows if not r["expected"]]
    print(f"dev: {len(pos)} matching, {len(neg)} no-match | shipped decision: jev yes/no >= 0.9, one skill\n")
    print(f"{'cond':5} {'in top16':>8} {'en':>6} {'ko':>6} | {'useful':>7} {'en':>6} {'ko':>6} {'junk+':>6} {'junk-':>6} | {'index s':>7}")
    stats = {}
    for c in CONDITIONS:
        inside = lambda rs: sum(r["expected"][0] in lists[c][r["query"]] for r in rs) / len(rs)
        useful = lambda rs: sum(1 for r in rs if first(c, r) and ok(r, first(c, r))) / len(rs)
        lang = lambda rs, code: [r for r in rs if r["lang"] == code]
        s = {
            "recall": inside(pos), "recall_en": inside(lang(pos, "en")), "recall_ko": inside(lang(pos, "ko")),
            "useful": useful(pos), "useful_en": useful(lang(pos, "en")), "useful_ko": useful(lang(pos, "ko")),
            "junk_pos": sum(1 for r in pos if first(c, r) and not ok(r, first(c, r))) / len(pos),
            "junk_neg": sum(1 for r in neg if first(c, r) and not ok(r, first(c, r))) / len(neg),
        }
        stats[c] = s
        print(
            f"{c:5} {s['recall']:8.3f} {s['recall_en']:6.3f} {s['recall_ko']:6.3f} | {s['useful']:7.3f} {s['useful_en']:6.3f} "
            f"{s['useful_ko']:6.3f} {s['junk_pos']:6.3f} {s['junk_neg']:6.3f} | {timing[c]['index_seconds']:7.1f}"
        )
    base = stats["E0"]["useful"]
    candidates = [c for c in ORDER_OF_COST if stats[c]["junk_neg"] <= JUNK_NEG and stats[c]["junk_pos"] <= JUNK_POS and stats[c]["useful"] - base >= ADOPT]
    print(f"\ngain in useful rate over E0: " + ", ".join(f"{c} {stats[c]['useful'] - base:+.3f}" for c in ORDER_OF_COST))
    if candidates:
        best = max(stats[c]["useful"] for c in candidates)
        chosen = next(c for c in ORDER_OF_COST if c in candidates and stats[c]["useful"] >= best - 0.01)
        print(f"-> ADOPT {chosen}" + ("  (body-based: unresolved by this benchmark, see protocol)" if chosen.endswith("2") else ""))
    else:
        print("-> nothing adopted")
    (OUT / "result.json").write_text(json.dumps(stats, indent=1), encoding="utf-8")


if __name__ == "__main__":
    {"synth": synth, "shortlists": shortlists, "judge": judge, "evaluate": evaluate}[sys.argv[1]]()
