"""The shipped default on a second corpus: docs/benchmarks/2026-11-25-second-corpus-protocol.md.

Reuses bench/scale/ scripts, pointed at bench/scale2/ and var/bench/scale2/.

    uv run python bench/scale2.py candidates                 # skills.sh listing
    uv run python bench/scale2.py pool                       # gh
    uv run python bench/scale2.py split
    uv run python bench/scale2.py queries                    # OPENAI_API_KEY
    uv run --extra rerank python bench/scale2.py record      # TYPESAFE_API_KEY
    uv run python bench/scale2.py run                        # OPENAI_API_KEY
    uv run python bench/scale2.py restore                    # re-download the pinned pool
"""

from __future__ import annotations

import json
import random
import sys
import urllib.request
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OLD = ROOT / "bench" / "scale"
HERE = ROOT / "bench" / "scale2"
WORK = ROOT / "var" / "bench" / "scale2"
sys.path.insert(0, str(OLD))

import agent_dev  # noqa: E402
import candidates_agent  # noqa: E402
import native_baseline  # noqa: E402
import prepare  # noqa: E402
import report  # noqa: E402
import scan_agent  # noqa: E402

SEED = 20261201
TAG = "b1"
PAGES = range(3, 13)
N_CORPUS, N_TARGETS, N_OUTSIDE = 350, 50, 50
ARM = "C:scan:8:0.5"
EARLIER_SETS = ("test2", "dev2", "test3", "dev3", "test4")

for module in (agent_dev, scan_agent, native_baseline, report, prepare):
    module.HERE, module.WORK = HERE, WORK
candidates_agent.WORK = WORK
agent_dev.RECORDS, agent_dev.ANSWERS = WORK / "unused", WORK / "agent"
scan_agent.CORPUS = WORK / f"corpus-{N_CORPUS}"
native_baseline.ANSWERS = WORK / "native"
native_baseline.SETS = {TAG: [f"scan-{TAG}"]}
prepare.CANDIDATES, prepare.MANIFEST = HERE / "candidates.json", HERE / "manifest.json"


def first_pool() -> tuple[set[str], set[str], set[tuple[str, str]]]:
    """(repositories, lower-case skill names, listed entries) used by anything so far."""
    manifest = json.loads((OLD / "manifest.json").read_text(encoding="utf-8"))["accepted"]
    sources = {a["source"] for a in manifest}
    names = {a["name"].lower() for a in manifest}
    for tag in EARLIER_SETS:
        for n in json.loads((OLD / f"{tag}-split.json").read_text(encoding="utf-8"))["negatives"]:
            sources.add(n["source"])
            names.add(n["name"].lower())
    listed = set()
    for name in ("candidates-2026-11-24.json", "candidates-2026-11-25.json"):
        listed |= {(c["source"], c["skill_id"]) for c in json.loads((OLD / name).read_text(encoding="utf-8"))["candidates"]}
    return sources, names, listed


def candidates(pages=PAGES) -> None:
    sources, _, listed = first_pool()
    path = HERE / "candidates.json"
    saved = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"pages": [], "candidates": []}
    seen = {(c["source"], c["skill_id"]) for c in saved["candidates"]}
    for page in pages:
        if page in saved["pages"]:
            continue
        request = urllib.request.Request(f"https://skills.sh/api/skills/all-time/{page}", headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(request, timeout=60) as response:
            entries = json.load(response)["skills"]
        for e in entries:
            key = (e["source"], e["skillId"])
            if key in listed or key in seen or e["source"] in sources:
                continue
            seen.add(key)
            saved["candidates"].append({"list": f"all-time/{page}", "source": e["source"], "skill_id": e["skillId"], "installs": e["installs"]})
        saved["pages"].append(page)
    saved.update(snapshot="2026-11-25", origin="https://skills.sh/api/skills/all-time/<page>")
    HERE.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(saved, indent=1), encoding="utf-8")
    print(f"{len(saved['candidates'])} candidates from {len({c['source'] for c in saved['candidates']})} repositories, pages {saved['pages']}")


def eligible() -> list[dict]:
    _, names, _ = first_pool()
    accepted = json.loads(prepare.MANIFEST.read_text(encoding="utf-8"))["accepted"]
    return [a for a in accepted if a["name"].lower() not in names]


def split() -> None:
    pool = eligible()
    print(f"eligible {len(pool)}")
    if len(pool) < N_CORPUS:
        sys.exit("fewer than 350 eligible skills; stop (see the protocol)")
    order = [a["name"] for a in pool]
    random.Random(SEED).shuffle(order)
    corpus, outside = order[:N_CORPUS], order[N_CORPUS : N_CORPUS + N_OUTSIDE]
    by_name = {a["name"]: a for a in pool}
    directory = scan_agent.CORPUS
    if directory.exists():
        for link in directory.iterdir():
            link.unlink()
    directory.mkdir(parents=True, exist_ok=True)
    for name in corpus:
        (directory / by_name[name]["dir"]).symlink_to(WORK / "pool" / by_name[name]["dir"], target_is_directory=True)
    (HERE / "split.json").write_text(
        json.dumps({"seed": SEED, "targets": corpus[:N_TARGETS], "corpus": corpus, "outside": outside}, indent=1), encoding="utf-8"
    )
    print(f"corpus {len(corpus)} from {len({by_name[n]['source'] for n in corpus})} repositories, targets {N_TARGETS}, no-match sources {len(outside)}")


def queries() -> None:
    by_name = {a["name"]: a for a in eligible()}
    parts = json.loads((HERE / "split.json").read_text(encoding="utf-8"))
    path = lambda n: WORK / "pool" / by_name[n]["dir"] / "SKILL.md"
    jobs = [(n, path(n), 2, "positive") for n in parts["targets"]] + [(n, path(n), 1, "no_match_heldout") for n in parts["outside"]]
    rows, dropped = prepare._generated_rows(jobs, TAG)
    (HERE / f"{TAG}-queries.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    print(f"wrote {len(rows)} requests {dict(Counter(r['kind'] for r in rows))}; dropped for naming the skill: {dropped}")


def run() -> None:
    candidates_agent.evaluate_with(agent_dev.PRIMARY, ["L", ARM], TAG)
    candidates_agent.evaluate_with(agent_dev.SECOND, [ARM], TAG, "-second")
    native_baseline.run(TAG, ["ALL"], agent_dev.PRIMARY)


if __name__ == "__main__":
    command = sys.argv[1]
    if command == "candidates":
        candidates(range(int(sys.argv[2]), int(sys.argv[3]) + 1) if len(sys.argv) > 3 else PAGES)
    else:
        {
            "pool": prepare.build_pool,
            "restore": prepare.restore_pool,
            "split": split,
            "queries": queries,
            "record": lambda: scan_agent.record(TAG),
            "run": run,
        }[command]()
