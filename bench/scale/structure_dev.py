"""Dev experiments for docs/benchmarks/2026-11-24-structure-protocol.md.

    uv run --extra rerank python bench/scale/structure_dev.py record     # TYPESAFE_API_KEY, OPENAI_API_KEY
    uv run python bench/scale/structure_dev.py evaluate                  # OPENAI_API_KEY (adjudication)
"""

from __future__ import annotations

import itertools
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from cards_dev import corpus_skills  # noqa: E402

from skill_rag.judges import JudgeConfig, load

ROOT = Path(__file__).resolve().parents[2]
WORK = ROOT / "var" / "bench" / "scale"
BASE_RECORDS = WORK / "precision-dev"  # local shortlist + jev yes/no probabilities
OUT = WORK / "structure-dev"
ROTATIONS = (0, 5, 11)
LEVELS = [
    "Unrelated to the request.",
    "Related topic or product, but not the right skill for this request.",
    "The right skill for this request.",
]
GATES = {
    "acts": "Does `request` ask the assistant to act on the user's files, accounts, devices, or services, rather than only explain something?",
    "procedure": "Would a careful expert consult a specific documented procedure, tool manual, or command reference to do what `request` asks?",
    "prose": "Could a knowledgeable generalist fully satisfy `request` with a written answer alone, without tools, files, or special access?",
    "named": "Does `request` ask for a specific named tool, format, template, or method to be used, rather than general help?",
}
JUNK_NEG, JUNK_POS, ADOPT = 0.10, 0.05, 0.05


def record() -> None:
    skills = corpus_skills()
    paths = sorted(BASE_RECORDS.glob("*.json"))

    def one(path: Path) -> None:
        out = OUT / path.name
        if out.exists():
            return
        rec = json.loads(path.read_text(encoding="utf-8"))
        names = rec["local"]
        described = [{"name": n, "description": skills[n]["description"][:1500], "agent": ""} for n in names]
        jev = load("jev", JudgeConfig(timeout=90))
        questions: dict = {}
        for r in ROTATIONS:
            order = names[r:] + names[:r]
            questions[f"which::{r}"] = {
                "type": "choice",
                "instructions": "Which one of these skills is the right documented procedure to load for the task in `request`? The request may be written in any language.",
                "criteria": {n: skills[n]["description"][:1500] for n in order},
            }
        questions["any"] = {
            "type": "noul",
            "instructions": "Is one of the skills listed in `skills` the right documented procedure to load for the task in `request`, covering the same task on the same product or platform?",
        }
        for key, text in GATES.items():
            questions[f"gate::{key}"] = {"type": "noul", "instructions": text}
        for i, n in enumerate(names):
            questions[f"level::{i}"] = {
                "type": "score",
                "instructions": f"How well does the skill '{n}' fit the task in `request`? Skill description: {skills[n]['description'][:1500]}",
                "criteria": LEVELS,
            }
        state = {"request": rec["query"], "skills": [{"name": c["name"], "description": c["description"]} for c in described]}
        response = jev._get_client().system_one(state, questions)
        choice = {n: 0.0 for n in names}
        for r in ROTATIONS:
            for n, p in response.choices[f"which::{r}"].probabilities.items():
                choice[n] += float(p) / len(ROTATIONS)
        openai = load("openai", JudgeConfig(timeout=90))
        OUT.mkdir(parents=True, exist_ok=True)
        out.write_text(
            json.dumps(
                {
                    **{k: rec[k] for k in ("query", "expected", "lang", "kind", "local")},
                    "n": {n: rec["fits"][n] for n in names},
                    "c": choice,
                    "c_first_rotation_top": response.choices[f"which::{ROTATIONS[0]}"].choice,
                    "a": float(response.nouls["any"].noul),
                    "gate": {k: float(response.nouls[f"gate::{k}"].noul) for k in GATES},
                    "s": {n: float(response.scores[f"level::{i}"].score) for i, n in enumerate(names)},
                    "openai_n": dict(zip(names, openai.fits(rec["query"], described))),
                    "tokens": {"extra_jev": response.usage.input_tokens, "openai": openai.last_usage["input_tokens"]},
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

    with ThreadPoolExecutor(4) as pool:
        list(pool.map(one, paths))
    print(f"recorded {len(list(OUT.glob('*.json')))} dev queries")


def top(scores: dict[str, float], order: list[str]) -> str:
    return max(order, key=lambda n: scores[n])  # first in local order on ties


def gate_passes(r: dict) -> bool:
    g = r["gate"]
    return (g["acts"] + g["procedure"] + (1.0 - g["prose"])) / 3 >= 0.30 or g["named"] >= 0.50


def evaluate() -> None:
    import report  # the adjudicator of the scale protocol

    skills = corpus_skills()
    records = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(OUT.glob("*.json"))]
    pos = [r for r in records if r["expected"]]
    neg = [r for r in records if not r["expected"]]
    pairs = sorted(
        {
            (r["query"], top(r[key], r["local"]))
            for r in records
            for key in ("n", "c", "s", "openai_n")
            if top(r[key], r["local"]) not in r["expected"]
        }
    )
    with ThreadPoolExecutor(6) as pool:
        verdicts = dict(zip(pairs, pool.map(lambda p: report.adjudicate(p[0], skills[p[1]]), pairs)))
    print(f"dev: {len(pos)} matching, {len(neg)} no-match | adjudicated pairs {len(pairs)}, judged to fit {sum(verdicts.values())}\n")

    def ok(r: dict, name: str) -> bool:
        return name in r["expected"] or verdicts.get((r["query"], name), False)

    def rates(decide) -> dict:
        out = {r["query"]: decide(r) for r in records}
        return {
            "useful": sum(1 for r in pos if out[r["query"]] and ok(r, out[r["query"]])) / len(pos),
            "junk_pos": sum(1 for r in pos if out[r["query"]] and not ok(r, out[r["query"]])) / len(pos),
            "junk_neg": sum(1 for r in neg if out[r["query"]] and not ok(r, out[r["query"]])) / len(neg),
        }

    def best(configs: list[tuple[dict, dict]]):
        qualifying = [(c, m) for c, m in configs if m["junk_neg"] <= JUNK_NEG and m["junk_pos"] <= JUNK_POS]
        return max(qualifying, key=lambda cm: cm[1]["useful"], default=None)

    def line(label: str, found) -> None:
        if found is None:
            print(f"  {label:34s} no configuration within the junk limits")
            return
        c, m = found
        print(f"  {label:34s} useful {m['useful']:.3f}  junk+ {m['junk_pos']:.3f}  junk- {m['junk_neg']:.3f}  {c}")

    shipped = rates(lambda r: top(r["n"], r["local"]) if max(r["n"].values()) >= 0.9 else None)
    print("## shipped rule (jev, yes/no >= 0.9)")
    line("shipped", ({"tn": 0.9}, shipped))
    for t in (0.5, 0.7, 0.8, 0.95):
        m = rates(lambda r, t=t: top(r["n"], r["local"]) if max(r["n"].values()) >= t else None)
        print(f"  {'jev yes/no >= ' + str(t):34s} useful {m['useful']:.3f}  junk+ {m['junk_pos']:.3f}  junk- {m['junk_neg']:.3f}")

    # ---- Experiment 1a: threshold for the openai judge
    print("\n## 1a. openai judge, yes/no threshold")
    grid = []
    for t in (0.5, 0.6, 0.7, 0.8, 0.9, 0.95, 0.97, 0.98, 0.99, 0.995, 0.999):
        m = rates(lambda r, t=t: top(r["openai_n"], r["local"]) if max(r["openai_n"].values()) >= t else None)
        grid.append(({"t": t}, m))
        print(f"  t={t:<6} useful {m['useful']:.3f}  junk+ {m['junk_pos']:.3f}  junk- {m['junk_neg']:.3f}")
    line("openai selected", best(grid))

    # ---- Experiment 1b: score-list model
    import numpy as np
    from sklearn.linear_model import LogisticRegression
    from sklearn.model_selection import StratifiedKFold, cross_val_predict

    def features(r: dict) -> list[float]:
        values = sorted(r["n"].values(), reverse=True)
        lead = top(r["n"], r["local"])
        return [values[0], values[1], values[0] - values[1], sum(v >= 0.5 for v in values), float(np.mean(values[:5])), r["local"].index(lead)]

    x = np.array([features(r) for r in records])
    y = np.array([int(ok(r, top(r["n"], r["local"]))) for r in records])
    folds = StratifiedKFold(n_splits=5, shuffle=True, random_state=20261124)
    predicted = cross_val_predict(LogisticRegression(max_iter=1000), x, y, cv=folds, method="predict_proba")[:, 1]
    by_query = {r["query"]: p for r, p in zip(records, predicted)}
    print("\n## 1b. score-list model on jev probabilities (5-fold cross-validated predictions)")
    grid = []
    for t in [round(0.5 + 0.05 * i, 2) for i in range(10)]:
        m = rates(lambda r, t=t: top(r["n"], r["local"]) if by_query[r["query"]] >= t else None)
        grid.append(({"t": t}, m))
        print(f"  t={t:<5} useful {m['useful']:.3f}  junk+ {m['junk_pos']:.3f}  junk- {m['junk_neg']:.3f}")
    model = best(grid)
    line("score-list model selected", model)

    # ---- Experiment 1c: conformal threshold on no-match junk at 10%
    n_neg = len(neg)
    bound = (0.10 * (n_neg + 1) - 1) / n_neg
    print(f"\n## 1c. conformal risk control, no-match junk <= 10% (needs dev junk <= {bound:.3f})")
    for t in (0.5, 0.6, 0.7, 0.8, 0.85, 0.9, 0.95):
        m = rates(lambda r, t=t: top(r["n"], r["local"]) if max(r["n"].values()) >= t else None)
        if m["junk_neg"] <= bound:
            print(f"  lowest jev threshold meeting the bound: {t} (dev junk- {m['junk_neg']:.3f})")
            break
    else:
        print("  no threshold in the grid meets the bound")

    # ---- Experiment 2: four rule families, with and without the gate
    def s1(tc, tn, gate):
        def decide(r):
            j = top(r["c"], r["local"])
            return j if r["c"][j] >= tc and r["n"][j] >= tn and (not gate or gate_passes(r)) else None
        return decide

    def s2(tc, ta, gate):
        def decide(r):
            j = top(r["c"], r["local"])
            return j if r["c"][j] >= tc and r["a"] >= ta and (not gate or gate_passes(r)) else None
        return decide

    def s3(ts, gate):
        def decide(r):
            j = top(r["s"], r["local"])
            return j if r["s"][j] >= ts and (not gate or gate_passes(r)) else None
        return decide

    def s4(tn, tc, gate):
        def decide(r):
            j = top(r["n"], r["local"])
            if gate and not gate_passes(r):
                return None
            if r["n"][j] >= 0.9:
                return j
            return j if j == top(r["c"], r["local"]) and r["n"][j] >= tn and r["c"][j] >= tc else None
        return decide

    tcs = (0.5, 0.6, 0.7, 0.8, 0.9)
    families = {
        "S1 choose then check": [({"tc": a, "tn": b, "gate": g}, rates(s1(a, b, g))) for a, b, g in itertools.product(tcs, (0.3, 0.5, 0.7, 0.9), (False, True))],
        "S2 choose with existence": [({"tc": a, "ta": b, "gate": g}, rates(s2(a, b, g))) for a, b, g in itertools.product(tcs, (0.3, 0.5, 0.7, 0.9), (False, True))],
        "S3 graded score": [({"ts": a, "gate": g}, rates(s3(a, g))) for a, g in itertools.product((1.2, 1.4, 1.5, 1.6, 1.7, 1.8, 1.9), (False, True))],
        "S4 rescue the middle": [({"tn": a, "tc": b, "gate": g}, rates(s4(a, b, g))) for a, b, g in itertools.product((0.5, 0.6, 0.7, 0.8), tcs, (False, True))],
    }
    print("\n## 2. decision structures (best configuration of each family within the junk limits)")
    winners = {}
    for label, configs in families.items():
        winners[label] = best(configs)
        line(label, winners[label])
    print("\n  for context, ignoring the junk limits:")
    for label, decide in (
        ("Choice top, always returned", lambda r: top(r["c"], r["local"])),
        ("Score top, always returned", lambda r: top(r["s"], r["local"])),
        ("yes/no top, always returned", lambda r: top(r["n"], r["local"])),
    ):
        m = rates(decide)
        print(f"  {label:34s} useful {m['useful']:.3f}  junk+ {m['junk_pos']:.3f}  junk- {m['junk_neg']:.3f}")
    gate_pos = sum(gate_passes(r) for r in pos) / len(pos)
    gate_neg = sum(gate_passes(r) for r in neg) / len(neg)
    print(f"  gate passes for {gate_pos:.3f} of matching and {gate_neg:.3f} of no-match requests")
    print(f"  companion 'any fits' >= 0.5 for {sum(r['a'] >= 0.5 for r in pos) / len(pos):.3f} of matching and {sum(r['a'] >= 0.5 for r in neg) / len(neg):.3f} of no-match requests")

    print("\n## adoption (needs at least +0.05 useful over the shipped rule)")
    candidates = {**winners, "1b score-list model": model}
    adopted = None
    for label, found in candidates.items():
        if found is None:
            print(f"  {label:34s} -")
            continue
        gain = found[1]["useful"] - shipped["useful"]
        print(f"  {label:34s} {gain:+.3f}")
        if gain >= ADOPT and (adopted is None or found[1]["useful"] > adopted[1][1]["useful"]):
            adopted = (label, found)
    print(f"\n  -> {'ADOPT ' + adopted[0] + ' ' + json.dumps(adopted[1][0]) if adopted else 'nothing adopted'}")
    (WORK / "structure-dev-result.json").write_text(
        json.dumps({"shipped": shipped, "winners": {k: v for k, v in candidates.items()}, "adopted": adopted}, indent=1),
        encoding="utf-8",
    )


if __name__ == "__main__":
    {"record": record, "evaluate": evaluate}[sys.argv[1]]()
