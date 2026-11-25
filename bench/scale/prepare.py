"""Prepare the scale benchmark: skill pool, split, corpora, queries.

Rules live in docs/benchmarks/2026-11-24-scale-protocol.md; this file only
implements them. Steps cache under var/bench/scale/ and are safe to rerun.

    uv run python bench/scale/prepare.py pool      # needs `gh` signed in; the versions pinned in manifest.json
    uv run python bench/scale/prepare.py split
    uv run python bench/scale/prepare.py queries   # needs OPENAI_API_KEY
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import random
import re
import subprocess
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from skill_rag.parser import parse_skill_file

ROOT = Path(__file__).resolve().parents[2]
HERE = ROOT / "bench" / "scale"
WORK = ROOT / "var" / "bench" / "scale"
CANDIDATES = HERE / "candidates-2026-11-24.json"
MANIFEST = HERE / "manifest.json"
SPLIT = HERE / "split.json"
QUERIES = HERE / "queries.jsonl"

SEED = 20261124
SOURCE_CAP = 20
N_TARGETS = 50
N_HELDOUT = 50
SIZES = (50, 100, 200, 400)
MIN_DESCRIPTION = 40
MIN_BODY = 200
GEN_MODEL = "gpt-6.2-sol"
GEN_BODY_CHARS = 6000
GEN_PROMPT = (
    'Below is the body of an "agent skill": instructions an AI coding agent loads '
    "when a user's request calls for them. Write requests that a real user might "
    "type to an AI agent for which loading this skill would clearly be the right "
    "move. Each request is one or two sentences and describes the user's own "
    "concrete task or problem. Do not mention the skill, its name, or that a "
    "skill exists. Do not copy distinctive phrases from the text. Korean requests "
    "must read as natural Korean; technical terms may stay in English. Return "
    "exactly the number of requests asked for in each language."
)
GITHUB_SOURCE = re.compile(r"[A-Za-z0-9_-]+/[A-Za-z0-9_.-]+")


def gh_json(endpoint: str):
    out = subprocess.run(["gh", "api", endpoint], capture_output=True, text=True, timeout=120)
    return json.loads(out.stdout) if out.returncode == 0 and out.stdout.strip() else None


def cached(path: Path, produce):
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    value = produce()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")
    return value


def skill_md_entry(tree: dict | None, skill_id: str) -> dict | None:
    if not tree:
        return None
    files = [
        e for e in tree.get("tree", [])
        if e.get("type") == "blob" and e["path"].endswith("/SKILL.md")
    ]
    for same in (lambda a, b: a == b, lambda a, b: a.lower() == b.lower()):
        hits = [e for e in files if same(e["path"].split("/")[-2], skill_id)]
        if hits:
            return min(hits, key=lambda e: (len(e["path"]), e["path"]))
    return None


def restore_pool() -> None:
    """Download exactly the SKILL.md versions the committed manifest pins.

    Reads manifest.json and never writes it, so the committed split and query
    labels keep referring to the same skill texts whatever upstream does.
    """
    accepted = json.loads(MANIFEST.read_text(encoding="utf-8"))["accepted"]

    def fetch(a: dict) -> str | None:
        blob = cached(
            WORK / "blobs" / f"{a['blob_sha']}.json",
            lambda: gh_json(f"repos/{a['source']}/git/blobs/{a['blob_sha']}") or {},
        )
        if "content" not in blob:
            (WORK / "blobs" / f"{a['blob_sha']}.json").unlink(missing_ok=True)  # do not cache a failure
            return f"{a['source']} {a['path']}: blob {a['blob_sha']} could not be fetched"
        data = base64.b64decode(blob["content"])
        if hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest() != a["blob_sha"]:
            return f"{a['source']} {a['path']}: content does not match blob {a['blob_sha']}"
        skill_md = WORK / "pool" / a["dir"] / "SKILL.md"
        skill_md.parent.mkdir(parents=True, exist_ok=True)
        skill_md.write_bytes(data)
        return None

    with ThreadPoolExecutor(8) as pool:
        problems = [p for p in pool.map(fetch, accepted) if p]
    print(f"restored {len(accepted) - len(problems)} of {len(accepted)} pinned skills")
    if problems:
        sys.exit("pool is incomplete; the published results cannot be reproduced from it:\n" + "\n".join(problems))


def pool() -> None:
    if MANIFEST.exists():
        restore_pool()
    else:
        build_pool()


def build_pool() -> None:
    """Discover a new pool from each repository's current HEAD and write a new manifest."""
    candidates = json.loads(CANDIDATES.read_text(encoding="utf-8"))["candidates"]
    github = [c for c in candidates if GITHUB_SOURCE.fullmatch(c["source"])]
    sources = sorted({c["source"] for c in github})

    def tree_for(source: str):
        key = source.replace("/", "__")
        return cached(
            WORK / "trees" / f"{key}.json",
            lambda: gh_json(f"repos/{source}/git/trees/HEAD?recursive=1") or {},
        )

    with ThreadPoolExecutor(8) as pool:
        trees = dict(zip(sources, pool.map(tree_for, sources)))

    def blob_for(job):
        source, sha = job
        return cached(
            WORK / "blobs" / f"{sha}.json",
            lambda: gh_json(f"repos/{source}/git/blobs/{sha}") or {},
        )

    entries = {(c["source"], c["skill_id"]): skill_md_entry(trees[c["source"]], c["skill_id"]) for c in github}
    jobs = sorted({(s, e["sha"]) for (s, _), e in entries.items() if e})
    with ThreadPoolExecutor(8) as pool:
        blobs = {sha: blob for (_, sha), blob in zip(jobs, pool.map(blob_for, jobs))}

    accepted: list[dict] = []
    rejected: Counter = Counter()
    ids: set[str] = set()
    names: set[str] = set()
    per_source: Counter = Counter()
    pool_dir = WORK / "pool"
    for c in candidates:
        source, skill_id = c["source"], c["skill_id"]
        if not GITHUB_SOURCE.fullmatch(source):
            rejected["1 not a GitHub source"] += 1
            continue
        if skill_id.lower() in ids:
            rejected["2 skill id already accepted"] += 1
            continue
        if per_source[source] >= SOURCE_CAP:
            rejected["3 source cap reached"] += 1
            continue
        entry = entries[(source, skill_id)]
        blob = blobs.get(entry["sha"]) if entry else None
        if not entry or not blob or "content" not in blob:
            rejected["4 SKILL.md not found or not fetched"] += 1
            continue
        text = base64.b64decode(blob["content"]).decode("utf-8", "replace")
        directory = f"{len(accepted):03d}-{re.sub(r'[^A-Za-z0-9_.-]', '_', skill_id)}"
        skill_md = pool_dir / directory / "SKILL.md"
        skill_md.parent.mkdir(parents=True, exist_ok=True)
        skill_md.write_text(text, encoding="utf-8")
        record = parse_skill_file(skill_md)
        reason = None
        if record is None:
            reason = "5 parser rejected the file"
        elif len(record.description) < MIN_DESCRIPTION or len(record.body) < MIN_BODY:
            reason = "6 description or body too short"
        elif record.name.lower() in names:
            reason = "7 frontmatter name already accepted"
        if reason:
            rejected[reason] += 1
            skill_md.unlink()
            skill_md.parent.rmdir()
            continue
        ids.add(skill_id.lower())
        names.add(record.name.lower())
        per_source[source] += 1
        accepted.append(
            {
                "name": record.name,
                "source": source,
                "skill_id": skill_id,
                "path": entry["path"],
                "blob_sha": entry["sha"],
                "dir": directory,
                "list": c["list"],
            }
        )
    MANIFEST.write_text(
        json.dumps({"accepted": accepted, "rejected": dict(sorted(rejected.items()))}, indent=1),
        encoding="utf-8",
    )
    print(f"accepted {len(accepted)} from {len(per_source)} sources; rejected {dict(sorted(rejected.items()))}")


def split() -> None:
    accepted = json.loads(MANIFEST.read_text(encoding="utf-8"))["accepted"]
    by_name = {a["name"]: a for a in accepted}
    order = [a["name"] for a in accepted]
    random.Random(SEED).shuffle(order)
    targets = order[:N_TARGETS]
    heldout = order[N_TARGETS : N_TARGETS + N_HELDOUT]
    distractors = order[N_TARGETS + N_HELDOUT :]
    largest = N_TARGETS + len(distractors)
    sizes = [s for s in SIZES if s <= largest]
    if SIZES[-1] > largest:
        sizes.append(largest // 50 * 50)
    sizes = sorted(set(sizes))
    for size in sizes:
        corpus = WORK / f"corpus-{size}"
        if corpus.exists():
            for link in corpus.iterdir():
                link.unlink()
        corpus.mkdir(parents=True, exist_ok=True)
        for name in targets + distractors[: size - N_TARGETS]:
            directory = by_name[name]["dir"]
            (corpus / directory).symlink_to(WORK / "pool" / directory, target_is_directory=True)
    SPLIT.write_text(
        json.dumps(
            {"seed": SEED, "sizes": sizes, "targets": targets, "heldout": heldout, "distractors": distractors},
            indent=1,
        ),
        encoding="utf-8",
    )
    print(f"targets {len(targets)}, held-out {len(heldout)}, distractors {len(distractors)}, sizes {sizes}")


def generate(body: str, n: int) -> dict:
    import httpx

    schema = {
        "type": "object",
        "properties": {
            lang: {"type": "array", "items": {"type": "string"}, "minItems": n, "maxItems": n}
            for lang in ("en", "ko")
        },
        "required": ["en", "ko"],
        "additionalProperties": False,
    }
    response = httpx.post(
        os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/") + "/responses",
        headers={"Authorization": f"Bearer {os.environ['OPENAI_API_KEY']}"},
        json={
            "model": GEN_MODEL,
            "input": [
                {"role": "developer", "content": GEN_PROMPT},
                {"role": "user", "content": f"Write {n} request(s) in English and {n} in Korean.\n\n{body[:GEN_BODY_CHARS]}"},
            ],
            "text": {"format": {"type": "json_schema", "name": "requests", "strict": True, "schema": schema}},
        },
        timeout=120,
    )
    response.raise_for_status()
    texts = [
        part["text"]
        for item in response.json()["output"]
        if item.get("type") == "message"
        for part in item["content"]
        if part.get("type") == "output_text"
    ]
    return json.loads(texts[0])


def mentions(text: str, name: str) -> bool:
    flat = re.sub(r"[-_\s]+", " ", text.lower())
    return re.sub(r"[-_\s]+", " ", name.lower()) in flat


def make_queries() -> None:
    accepted = {a["name"]: a for a in json.loads(MANIFEST.read_text(encoding="utf-8"))["accepted"]}
    parts = json.loads(SPLIT.read_text(encoding="utf-8"))
    jobs = [(name, 2, "positive") for name in parts["targets"]] + [
        (name, 1, "no_match_heldout") for name in parts["heldout"]
    ]

    def run(job):
        name, n, _ = job
        record = parse_skill_file(WORK / "pool" / accepted[name]["dir"] / "SKILL.md")

        def attempt(tag: str):
            return cached(WORK / "gen" / f"{accepted[name]['dir']}{tag}.json", lambda: generate(record.body, n))

        first = attempt("")
        if not any(mentions(q, name) for lang in ("en", "ko") for q in first[lang]):
            return first, 0
        second = attempt(".retry")
        kept = {lang: [q for q in second[lang] if not mentions(q, name)] for lang in ("en", "ko")}
        return kept, sum(n - len(kept[lang]) for lang in ("en", "ko"))

    with ThreadPoolExecutor(6) as pool:
        results = list(pool.map(run, jobs))
    rows = []
    dropped = 0
    for (name, _, kind), (generated, lost) in zip(jobs, results):
        dropped += lost
        for lang in ("en", "ko"):
            for query in generated[lang]:
                rows.append(
                    {
                        "query": query,
                        "expected": [name] if kind == "positive" else [],
                        "lang": lang,
                        "kind": kind,
                        "from_skill": name,
                    }
                )
    QUERIES.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    kinds = Counter(r["kind"] for r in rows)
    print(f"wrote {len(rows)} queries {dict(kinds)}; dropped for naming the skill: {dropped}")


DEV_SEED = 20261125
DEV_SPLIT = HERE / "dev-split.json"
DEV_QUERIES = HERE / "dev-queries.jsonl"


def make_dev_queries() -> None:
    """Dev set for choosing first-stage settings; see 2026-11-24-first-stage-protocol.md."""
    accepted = {a["name"]: a for a in json.loads(MANIFEST.read_text(encoding="utf-8"))["accepted"]}
    parts = json.loads(SPLIT.read_text(encoding="utf-8"))
    dev_targets = random.Random(DEV_SEED).sample(parts["distractors"][:150], 50)
    DEV_SPLIT.write_text(json.dumps({"seed": DEV_SEED, "targets": dev_targets}, indent=1), encoding="utf-8")

    def run(name: str):
        record = parse_skill_file(WORK / "pool" / accepted[name]["dir"] / "SKILL.md")

        def attempt(tag: str):
            return cached(WORK / "gen" / f"{accepted[name]['dir']}.dev{tag}.json", lambda: generate(record.body, 2))

        first = attempt("")
        if not any(mentions(q, name) for lang in ("en", "ko") for q in first[lang]):
            return first, 0
        second = attempt(".retry")
        kept = {lang: [q for q in second[lang] if not mentions(q, name)] for lang in ("en", "ko")}
        return kept, sum(2 - len(kept[lang]) for lang in ("en", "ko"))

    with ThreadPoolExecutor(6) as pool:
        results = list(pool.map(run, dev_targets))
    rows = [
        {"query": query, "expected": [name], "lang": lang, "kind": "positive", "from_skill": name}
        for name, (generated, _) in zip(dev_targets, results)
        for lang in ("en", "ko")
        for query in generated[lang]
    ]
    DEV_QUERIES.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    print(f"wrote {len(rows)} dev queries; dropped for naming the skill: {sum(lost for _, lost in results)}")


def _generated_rows(jobs: list[tuple[str, Path, int, str]], tag: str) -> tuple[list[dict], int]:
    """``jobs`` are (name, SKILL.md path, requests per language, kind)."""

    def run(job):
        name, skill_md, n, _ = job
        record = parse_skill_file(skill_md)
        key = skill_md.parent.name

        def attempt(suffix: str):
            return cached(WORK / "gen" / f"{key}.{tag}{suffix}.json", lambda: generate(record.body, n))

        first = attempt("")
        if not any(mentions(q, name) for lang in ("en", "ko") for q in first[lang]):
            return first, 0
        second = attempt(".retry")
        kept = {lang: [q for q in second[lang] if not mentions(q, name)] for lang in ("en", "ko")}
        return kept, sum(n - len(kept[lang]) for lang in ("en", "ko"))

    with ThreadPoolExecutor(6) as pool:
        results = list(pool.map(run, jobs))
    rows = [
        {
            "query": query,
            "expected": [name] if kind == "positive" else [],
            "lang": lang,
            "kind": kind,
            "from_skill": name,
        }
        for (name, _, _, kind), (generated, _) in zip(jobs, results)
        for lang in ("en", "ko")
        for query in generated[lang]
    ]
    return rows, sum(lost for _, lost in results)


def make_dev_negatives() -> None:
    """Dev negatives for the precision protocol: distractors never placed in a corpus."""
    accepted = {a["name"]: a for a in json.loads(MANIFEST.read_text(encoding="utf-8"))["accepted"]}
    parts = json.loads(SPLIT.read_text(encoding="utf-8"))
    unused = parts["distractors"][max(parts["sizes"]) - N_TARGETS :]
    jobs = [(n, WORK / "pool" / accepted[n]["dir"] / "SKILL.md", 1, "no_match_heldout") for n in unused]
    rows, dropped = _generated_rows(jobs, "devneg")
    (HERE / "dev-negatives.jsonl").write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8"
    )
    print(f"wrote {len(rows)} dev negatives from {len(unused)} skills; dropped for naming the skill: {dropped}")


TEST2_SEED = 20261126


def make_test2() -> None:
    """Fresh test set of the precision protocol. Run once, after the configuration is committed."""
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))["accepted"]
    accepted = {a["name"]: a for a in manifest}
    parts = json.loads(SPLIT.read_text(encoding="utf-8"))
    dev_targets = set(json.loads(DEV_SPLIT.read_text(encoding="utf-8"))["targets"])
    rng = random.Random(TEST2_SEED)
    eligible = [n for n in parts["distractors"][: max(parts["sizes"]) - N_TARGETS] if n not in dev_targets]
    targets = rng.sample(eligible, 50)

    # Negatives: candidates that never entered the pool, same content rules.
    candidates = json.loads(CANDIDATES.read_text(encoding="utf-8"))["candidates"]
    pooled_ids = {a["skill_id"].lower() for a in manifest}
    pooled_names = {a["name"].lower() for a in manifest}
    outside = [
        c for c in candidates
        if GITHUB_SOURCE.fullmatch(c["source"]) and c["skill_id"].lower() not in pooled_ids
    ]
    rng.shuffle(outside)
    extra_dir = WORK / "outside"
    negatives: list[tuple[str, Path]] = []
    seen: set[str] = set()
    for c in outside:
        if len(negatives) == 50:
            break
        key = c["source"].replace("/", "__")
        tree = cached(WORK / "trees" / f"{key}.json", lambda: gh_json(f"repos/{c['source']}/git/trees/HEAD?recursive=1") or {})
        entry = skill_md_entry(tree, c["skill_id"])
        if not entry:
            continue
        blob = cached(WORK / "blobs" / f"{entry['sha']}.json", lambda: gh_json(f"repos/{c['source']}/git/blobs/{entry['sha']}") or {})
        if "content" not in blob:
            continue
        skill_md = extra_dir / f"{key}__{re.sub(r'[^A-Za-z0-9_.-]', '_', c['skill_id'])}" / "SKILL.md"
        skill_md.parent.mkdir(parents=True, exist_ok=True)
        skill_md.write_text(base64.b64decode(blob["content"]).decode("utf-8", "replace"), encoding="utf-8")
        record = parse_skill_file(skill_md)
        if (
            record is None
            or len(record.description) < MIN_DESCRIPTION
            or len(record.body) < MIN_BODY
            or record.name.lower() in pooled_names
            or record.name.lower() in seen
        ):
            continue
        seen.add(record.name.lower())
        negatives.append((record.name, skill_md, c["source"]))

    jobs = [(n, WORK / "pool" / accepted[n]["dir"] / "SKILL.md", 2, "positive") for n in targets] + [
        (name, path, 1, "no_match_heldout") for name, path, _ in negatives
    ]
    rows, dropped = _generated_rows(jobs, "test2")
    (HERE / "test2-queries.jsonl").write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8"
    )
    (HERE / "test2-split.json").write_text(
        json.dumps(
            {"seed": TEST2_SEED, "targets": targets, "negatives": [{"name": n, "source": s} for n, _, s in negatives]},
            indent=1,
        ),
        encoding="utf-8",
    )
    kinds = Counter(r["kind"] for r in rows)
    print(f"wrote {len(rows)} test-2 queries {dict(kinds)}; dropped for naming the skill: {dropped}")


# Later request sets built like test2: (seed, earlier sets of this kind whose
# skills must not be reused). See docs/benchmarks/2026-11-25-agent2-protocol.md.
FRESH = {"dev2": (20261128, []), "test3": (20261127, ["dev2"])}


def make_fresh(tag: str) -> None:
    """A request set on skills no earlier set used as targets or no-match sources."""
    seed, earlier = FRESH[tag]
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))["accepted"]
    accepted = {a["name"]: a for a in manifest}
    parts = json.loads(SPLIT.read_text(encoding="utf-8"))
    used_targets = set(json.loads(DEV_SPLIT.read_text(encoding="utf-8"))["targets"])
    used_negatives: set[str] = set()
    for name in ["test2", *earlier]:
        done = json.loads((HERE / f"{name}-split.json").read_text(encoding="utf-8"))
        used_targets |= set(done["targets"])
        used_negatives |= {n["name"].lower() for n in done["negatives"]}
    rng = random.Random(seed)
    eligible = [n for n in parts["distractors"][: max(parts["sizes"]) - N_TARGETS] if n not in used_targets]
    targets = rng.sample(eligible, 50)

    candidates = json.loads(CANDIDATES.read_text(encoding="utf-8"))["candidates"]
    pooled_ids = {a["skill_id"].lower() for a in manifest}
    pooled_names = {a["name"].lower() for a in manifest}
    outside = [
        c for c in candidates
        if GITHUB_SOURCE.fullmatch(c["source"]) and c["skill_id"].lower() not in pooled_ids
    ]
    rng.shuffle(outside)
    negatives: list[tuple[str, Path, str, str]] = []
    seen: set[str] = set()
    for c in outside:
        if len(negatives) == 50:
            break
        key = c["source"].replace("/", "__")
        tree = cached(WORK / "trees" / f"{key}.json", lambda: gh_json(f"repos/{c['source']}/git/trees/HEAD?recursive=1") or {})
        entry = skill_md_entry(tree, c["skill_id"])
        if not entry:
            continue
        blob = cached(WORK / "blobs" / f"{entry['sha']}.json", lambda: gh_json(f"repos/{c['source']}/git/blobs/{entry['sha']}") or {})
        if "content" not in blob:
            continue
        skill_md = WORK / "outside" / f"{key}__{re.sub(r'[^A-Za-z0-9_.-]', '_', c['skill_id'])}" / "SKILL.md"
        skill_md.parent.mkdir(parents=True, exist_ok=True)
        skill_md.write_text(base64.b64decode(blob["content"]).decode("utf-8", "replace"), encoding="utf-8")
        record = parse_skill_file(skill_md)
        if (
            record is None
            or len(record.description) < MIN_DESCRIPTION
            or len(record.body) < MIN_BODY
            or record.name.lower() in pooled_names
            or record.name.lower() in used_negatives
            or record.name.lower() in seen
        ):
            continue
        seen.add(record.name.lower())
        negatives.append((record.name, skill_md, c["source"], entry["sha"]))

    jobs = [(n, WORK / "pool" / accepted[n]["dir"] / "SKILL.md", 2, "positive") for n in targets] + [
        (name, path, 1, "no_match_heldout") for name, path, _, _ in negatives
    ]
    rows, dropped = _generated_rows(jobs, tag)
    (HERE / f"{tag}-queries.jsonl").write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8"
    )
    (HERE / f"{tag}-split.json").write_text(
        json.dumps(
            {
                "seed": seed,
                "targets": targets,
                "negatives": [{"name": n, "source": s, "blob_sha": sha} for n, _, s, sha in negatives],
            },
            indent=1,
        ),
        encoding="utf-8",
    )
    kinds = Counter(r["kind"] for r in rows)
    print(f"wrote {len(rows)} {tag} queries {dict(kinds)}; dropped for naming the skill: {dropped}")


def make_test3_negatives() -> None:
    """No-match half of test3; see the addendum of 2026-11-25-agent2-protocol.md."""
    accepted = {a["name"]: a for a in json.loads(MANIFEST.read_text(encoding="utf-8"))["accepted"]}
    heldout = json.loads(SPLIT.read_text(encoding="utf-8"))["heldout"]
    jobs = [(n, WORK / "pool" / accepted[n]["dir"] / "SKILL.md", 1, "no_match_heldout") for n in heldout]
    rows, dropped = _generated_rows(jobs, "test3neg")
    (HERE / "test3neg-queries.jsonl").write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8"
    )
    print(f"wrote {len(rows)} test3 no-match queries from {len(heldout)} skills; dropped for naming the skill: {dropped}")


if __name__ == "__main__":
    if sys.argv[1] == "test3neg":
        make_test3_negatives()
        sys.exit()
    if sys.argv[1] in FRESH:
        make_fresh(sys.argv[1])
        sys.exit()
    {
        "pool": pool,  # the pinned pool when manifest.json exists
        "discover": build_pool,  # new benchmark only: overwrites manifest.json
        "split": split,
        "queries": make_queries,
        "dev-queries": make_dev_queries,
        "dev-negatives": make_dev_negatives,
        "test2": make_test2,
    }[sys.argv[1]]()
