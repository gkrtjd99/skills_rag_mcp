"""Opt-in rerank: offline tests with every judge stubbed at the network edge."""

import importlib

import pytest

from skill_rag import index as index_mod
from skill_rag import judges, rerank, retrieve
from skill_rag.judges import JudgeConfig
from skill_rag.judges.jev import JevJudge
from skill_rag.judges.openai_decisions import OpenAIDecisionsJudge
from skill_rag.models import SkillRecord


@pytest.fixture(autouse=True)
def isolated_index(tmp_path, monkeypatch):
    monkeypatch.setenv("SKILL_RAG_INDEX_PATH", str(tmp_path / "index.lance"))
    monkeypatch.delenv("SKILL_RAG_RERANK", raising=False)
    importlib.reload(index_mod)
    importlib.reload(retrieve)
    importlib.reload(rerank)
    yield
    index_mod.reset()


def _seed():
    index_mod.upsert(
        [
            SkillRecord(
                name=name,
                description=description,
                path=f"/x/{name}/SKILL.md",
                body="b",
                content_hash=name,
            )
            for name, description in [
                ("brainstorming", "explore ideas and requirements before implementation"),
                ("tdd", "write failing tests first then implement"),
                ("deploy", "publish the website and return a preview url"),
            ]
        ]
    )


def _enable(monkeypatch, fits_by_name):
    """Turn rerank on with a judge that answers from ``fits_by_name``."""
    calls = []

    def fake_judge(query, candidates):
        calls.append((query, [c["name"] for c in candidates]))
        return [fits_by_name.get(c["name"], 0.0) for c in candidates]

    monkeypatch.setattr(rerank, "RERANK_PROVIDER", "jev")
    monkeypatch.setattr(rerank, "judge", fake_judge)
    return calls


class FakeJudge:
    """A third-party provider, loaded by ``module:factory`` path."""

    name = "fake"
    destination = ""

    def __init__(self, config):
        self.config = config

    def unavailable_reason(self):
        return None

    def fits(self, query, candidates):
        return [1.0 if c["name"] in query else 0.0 for c in candidates]


# --- policy: off by default, thresholds, ordering, response shape -----------


def test_disabled_by_default_uses_the_local_path(monkeypatch):
    monkeypatch.setattr(retrieve, "SCORE_THRESHOLD", 0.0)
    _seed()
    monkeypatch.setattr(
        rerank, "judge", lambda *a, **k: pytest.fail("judge called while disabled")
    )
    assert not rerank.enabled()
    assert rerank.readiness() == "off"
    assert rerank.search("write failing tests") == _local("write failing tests")


def test_unknown_provider_value_stays_disabled(monkeypatch):
    monkeypatch.setattr(rerank, "RERANK_PROVIDER", "1")
    assert not rerank.enabled()
    assert rerank.readiness() == "off (unknown provider '1')"


def test_shortlist_ignores_thresholds_and_keeps_full_description(monkeypatch):
    monkeypatch.setattr(retrieve, "SCORE_THRESHOLD", 0.99)
    monkeypatch.setattr(retrieve, "DENSE_ONLY_THRESHOLD", 0.99)
    monkeypatch.setattr(retrieve, "BM25_THRESHOLD", 0.99)
    monkeypatch.setattr(retrieve, "MAX_HIT_DESCRIPTION_CHARS", 10)
    _seed()
    assert retrieve.search("qz-nonsense-token")["status"] == "no_match"
    rows = retrieve.shortlist("qz-nonsense-token", 2)
    assert len(rows) == 2
    assert all(set(r) == {"name", "description", "agent"} for r in rows)
    assert all(not r["description"].endswith("…") for r in rows)


def test_shortlist_empty_for_empty_query_or_corpus():
    assert retrieve.shortlist("anything", 5) == []
    _seed()
    assert retrieve.shortlist("   ", 5) == []


def _local(query: str, k: int = 5) -> dict:
    """What a search returns when no judge decides: the local gate."""
    return retrieve.search(query, k=k)


def test_defaults_are_precision_first(monkeypatch):
    _seed()
    assert rerank.RERANK_THRESHOLD == 0.9 and rerank.RERANK_MAX_HITS == 1
    assert rerank.RERANK_SCAN_MAX == 0
    _enable(monkeypatch, {"tdd": 0.69, "deploy": 0.6})
    assert rerank.search("ship it") == retrieve.no_match_response()  # likely is not enough
    _enable(monkeypatch, {"tdd": 0.95, "deploy": 0.97, "brainstorming": 0.92})
    res = rerank.search("ship it", k=5)
    assert [h["name"] for h in res["hits"]] == ["deploy"]  # only the best one


def test_best_skill_below_the_threshold_is_offered_as_uncertain(monkeypatch):
    _seed()
    assert rerank.RERANK_UNCERTAIN_FROM == 0.7
    _enable(monkeypatch, {"tdd": 0.89, "deploy": 0.75, "brainstorming": 0.6})
    res = rerank.search("ship it")
    # The exact shape and wording the benchmark measured (bench/scale/agent2.py).
    assert res["status"] == "uncertain"
    assert [set(h) for h in res["hits"]] == [{"name", "description", "confidence"}]
    assert res["hits"][0]["name"] == "tdd" and res["hits"][0]["confidence"] == "low"
    assert res["message"] == (
        "No skill was confirmed for this request. These are uncertain candidates: load "
        "one only if its description clearly covers the task; otherwise proceed without a skill."
    )
    monkeypatch.setattr(rerank, "RERANK_UNCERTAIN_FROM", 0.9)  # at the threshold: off
    assert rerank.search("ship it") == retrieve.no_match_response()


def test_local_candidates_are_opt_in(monkeypatch):
    monkeypatch.setattr(retrieve, "SCORE_THRESHOLD", 0.0)
    _seed()
    assert rerank.LOCAL_CANDIDATES == 0  # default: the local gate
    assert rerank.search("write failing tests") == retrieve.search("write failing tests")
    monkeypatch.setattr(rerank, "LOCAL_CANDIDATES", 3)
    res = rerank.search("write failing tests")
    assert res["status"] == "uncertain" and len(res["hits"]) == 3
    assert all(h["confidence"] == "low" and "score" not in h for h in res["hits"])
    assert len(rerank.search("write failing tests", k=2)["hits"]) == 2


def test_max_hits_zero_returns_up_to_k(monkeypatch):
    _seed()
    monkeypatch.setattr(rerank, "RERANK_MAX_HITS", 0)
    _enable(monkeypatch, {"tdd": 0.95, "deploy": 0.97, "brainstorming": 0.92})
    assert len(rerank.search("ship it", k=2)["hits"]) == 2
    assert len(rerank.search("ship it", k=5)["hits"]) == 3


def test_enabled_keeps_only_fitting_skills_ordered_by_probability(monkeypatch):
    _seed()
    monkeypatch.setattr(rerank, "RERANK_THRESHOLD", 0.5)
    monkeypatch.setattr(rerank, "RERANK_MAX_HITS", 0)
    calls = _enable(monkeypatch, {"tdd": 0.61, "deploy": 0.97, "brainstorming": 0.04})
    res = rerank.search("ship it", k=5)
    assert res["status"] == "ok"
    assert [h["name"] for h in res["hits"]] == ["deploy", "tdd"]
    assert [h["score"] for h in res["hits"]] == [0.97, 0.61]
    assert set(res["hits"][0]) == {"name", "description", "score", "agent"}
    assert len(calls) == 1 and calls[0][0] == "ship it"


def test_judged_hits_carry_a_shorter_description(monkeypatch):
    _seed()
    monkeypatch.setattr(rerank, "RERANK_DESCRIPTION_CHARS", 20)
    _enable(monkeypatch, {"deploy": 0.9})
    hit = rerank.search("ship it")["hits"][0]
    assert len(hit["description"]) <= 20 and hit["description"].endswith("…")
    monkeypatch.setattr(rerank, "RERANK_DESCRIPTION_CHARS", 0)  # 0 disables the cap
    full = rerank.search("ship it")["hits"][0]["description"]
    assert full == "publish the website and return a preview url"


def test_enabled_overrides_a_local_gate_that_would_reject(monkeypatch):
    monkeypatch.setattr(retrieve, "SCORE_THRESHOLD", 0.99)
    monkeypatch.setattr(retrieve, "DENSE_ONLY_THRESHOLD", 0.99)
    monkeypatch.setattr(retrieve, "BM25_THRESHOLD", 0.99)
    _seed()
    assert retrieve.search("배포 미리보기 주소")["status"] == "no_match"
    _enable(monkeypatch, {"deploy": 0.9})
    res = rerank.search("배포 미리보기 주소")
    assert [h["name"] for h in res["hits"]] == ["deploy"]


def test_enabled_returns_no_match_when_nothing_fits(monkeypatch):
    monkeypatch.setattr(retrieve, "SCORE_THRESHOLD", 0.0)
    _seed()
    _enable(monkeypatch, {"tdd": 0.49})
    res = rerank.search("write failing tests")
    assert res == retrieve.no_match_response()


def test_k_caps_hits_and_widens_shortlist(monkeypatch):
    _seed()
    monkeypatch.setattr(rerank, "RERANK_THRESHOLD", 0.5)
    monkeypatch.setattr(rerank, "RERANK_MAX_HITS", 0)
    monkeypatch.setattr(rerank, "RERANK_CANDIDATES", 1)
    calls = _enable(monkeypatch, {"tdd": 0.9, "deploy": 0.8, "brainstorming": 0.7})
    res = rerank.search("anything", k=2)
    assert len(calls[0][1]) == 2  # shortlist is never narrower than k
    assert len(res["hits"]) == 2


def test_empty_corpus_and_empty_query_keep_local_messages(monkeypatch):
    calls = _enable(monkeypatch, {})
    assert rerank.search("anything") == retrieve.search("anything")
    _seed()
    assert rerank.search("  ") == retrieve.search("  ")
    assert calls == []


# --- whole-corpus scan ------------------------------------------------------


def _seed_many(n=6):
    index_mod.upsert(
        [
            SkillRecord(
                name=f"skill-{i}",
                description=f"does thing number {i} " + "x" * 400,
                path=f"/x/skill-{i}/SKILL.md",
                body="b",
                content_hash=str(i),
            )
            for i in range(n)
        ]
    )


@pytest.fixture
def scan_on(monkeypatch):
    monkeypatch.setattr(rerank, "RERANK_SCAN_MAX", 500)


def test_scan_picks_the_shortlist_when_the_corpus_is_larger_than_it(monkeypatch, scan_on):
    _seed_many(6)
    monkeypatch.setattr(rerank, "RERANK_CANDIDATES", 2)
    seen = {}

    def fake_scan(query, candidates):
        seen["scanned"] = [c["name"] for c in candidates]
        return [0.9 if c["name"] in {"skill-4", "skill-1"} else 0.1 for c in candidates]

    calls = _enable(monkeypatch, {"skill-4": 0.95, "skill-1": 0.2})
    monkeypatch.setattr(rerank, "scan", fake_scan)
    res = rerank.search("anything at all", k=1)
    assert sorted(seen["scanned"]) == [f"skill-{i}" for i in range(6)]  # every skill
    assert sorted(calls[0][1]) == ["skill-1", "skill-4"]  # only the scan's top 2 judged
    assert [h["name"] for h in res["hits"]] == ["skill-4"]


@pytest.mark.parametrize("scan_max", [0, 5])
def test_scan_is_skipped_when_disabled_or_corpus_too_large(monkeypatch, scan_max):
    _seed_many(6)
    monkeypatch.setattr(rerank, "RERANK_CANDIDATES", 2)
    monkeypatch.setattr(rerank, "RERANK_SCAN_MAX", scan_max)
    monkeypatch.setattr(rerank, "scan", lambda *a: pytest.fail("scan called"))
    calls = _enable(monkeypatch, {})
    rerank.search("anything at all", k=1)
    assert calls[0][1] == [c["name"] for c in retrieve.shortlist("anything at all", 2)]


def test_scan_is_skipped_when_every_skill_is_judged_anyway(monkeypatch, scan_on):
    _seed_many(3)
    monkeypatch.setattr(rerank, "scan", lambda *a: pytest.fail("scan called"))
    calls = _enable(monkeypatch, {})
    rerank.search("anything at all")
    assert len(calls[0][1]) == 3


def test_judge_without_scan_is_scanned_through_fits_on_short_descriptions(monkeypatch, scan_on):
    _seed_many(6)
    monkeypatch.setattr(rerank, "RERANK_CANDIDATES", 2)
    lengths = []

    class NoScan(FakeJudge):
        def fits(self, query, candidates):
            lengths.append([len(c["description"]) for c in candidates])
            return [0.9 if c["name"] == "skill-3" else 0.0 for c in candidates]

    monkeypatch.setattr(rerank, "RERANK_PROVIDER", f"{__name__}:FakeJudge")
    monkeypatch.setattr(rerank, "current_judge", lambda: NoScan(None))
    res = rerank.search("anything at all", k=1)  # shortlist = max(k, RERANK_CANDIDATES) = 2
    assert len(lengths[0]) == 6 and max(lengths[0]) == judges.SCAN_DESCRIPTION_CHARS
    assert len(lengths[1]) == 2 and min(lengths[1]) > 400  # full descriptions for the fit
    assert [h["name"] for h in res["hits"]] == ["skill-3"]


def test_scan_failure_falls_back_to_local_gate(monkeypatch, scan_on):
    monkeypatch.setattr(retrieve, "SCORE_THRESHOLD", 0.0)
    _seed_many(6)
    monkeypatch.setattr(rerank, "RERANK_CANDIDATES", 2)
    _enable(monkeypatch, {"skill-1": 0.9})

    def boom(query, candidates):
        raise RuntimeError("scan failed")

    monkeypatch.setattr(rerank, "scan", boom)
    assert rerank.search("does thing number 1") == _local("does thing number 1")


def test_jev_scan_uses_the_short_wording_in_batches(monkeypatch):
    from skill_rag.judges import jev

    monkeypatch.setattr(jev, "SCAN_BATCH", 2)
    requests = []

    class _Answer:
        def __init__(self, noul):
            self.noul = noul

    class _Client:
        def system_one(self, state, questions, **kwargs):
            requests.append((state, questions))
            names = [q["instructions"].split("? ")[1].split(":")[0] for q in questions.values()]

            class _Response:
                model = "jev-x"
                usage = type("U", (), {"input_tokens": 10 * len(questions)})()
                nouls = {f"s{i}": _Answer(int(n[-1]) / 10) for i, n in enumerate(names)}

            return _Response()

    judge = JevJudge(JudgeConfig())
    judge._client = _Client()
    candidates = [{"name": f"skill-{i}", "description": "d " * 300, "agent": "a"} for i in range(5)]
    assert judge.scan("do it", candidates) == [0.0, 0.1, 0.2, 0.3, 0.4]  # input order kept
    assert len(requests) == 3 and judge.last_scan_usage == {"model": "jev-x", "input_tokens": 50}
    first = requests[0][1]["s0"]
    assert set(first) == {"type", "instructions"}  # no criteria in a scan
    assert first["instructions"].startswith("Does `request` call for this skill? skill-")
    assert len(first["instructions"]) < 60 + judges.SCAN_DESCRIPTION_CHARS


def test_openai_scan_batches_and_keeps_order(monkeypatch):
    from skill_rag.judges import openai_decisions

    monkeypatch.setattr(openai_decisions, "SCAN_BATCH", 2)
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    posted = []

    def post(url, headers, payload, timeout):
        posted.append(payload)
        answers = [
            {"type": "predicate", "name": q["name"], "probability": int(q["instructions"].split("skill-")[1][0]) / 10}
            for q in payload["questions"]
        ]
        return {"model": "gpt-6-luna", "answers": answers, "usage": {"input_tokens": 7 * len(answers)}}

    judge = OpenAIDecisionsJudge(JudgeConfig(), post=post)
    candidates = [{"name": f"skill-{i}", "description": "d " * 300, "agent": "a"} for i in range(5)]
    assert judge.scan("do it", candidates) == [0.0, 0.1, 0.2, 0.3, 0.4]
    assert len(posted) == 3 and judge.last_scan_usage["input_tokens"] == 35
    text = posted[0]["questions"][0]["instructions"]
    assert text.startswith("Does the request call for this skill? skill-") and "Yes means" not in text


# --- failure handling ------------------------------------------------------


def test_judge_failure_falls_back_to_local_gate(monkeypatch):
    monkeypatch.setattr(retrieve, "SCORE_THRESHOLD", 0.0)
    _seed()
    monkeypatch.setattr(rerank, "RERANK_PROVIDER", "jev")

    def boom(query, candidates):
        raise RuntimeError("network down")

    monkeypatch.setattr(rerank, "judge", boom)
    assert rerank.search("write failing tests") == _local("write failing tests")


def test_failure_starts_a_cooldown_that_skips_the_judge(monkeypatch):
    monkeypatch.setattr(retrieve, "SCORE_THRESHOLD", 0.0)
    _seed()
    monkeypatch.setattr(rerank, "RERANK_PROVIDER", "jev")
    clock = {"now": 100.0}
    monkeypatch.setattr(rerank, "_monotonic", lambda: clock["now"])
    monkeypatch.setattr(rerank, "RERANK_COOLDOWN_SECONDS", 60.0)
    calls = []

    def flaky(query, candidates):
        calls.append(query)
        if len(calls) == 1:
            raise RuntimeError("402")
        return [0.9 if c["name"] == "deploy" else 0.0 for c in candidates]

    monkeypatch.setattr(rerank, "judge", flaky)
    local = _local("write failing tests")
    assert rerank.search("write failing tests") == local  # failure -> local gate
    clock["now"] = 159.0
    assert rerank.search("write failing tests") == local  # cooling down
    assert len(calls) == 1
    clock["now"] = 161.0
    res = rerank.search("write failing tests")  # cooldown over: judge again
    assert len(calls) == 2
    assert [h["name"] for h in res["hits"]] == ["deploy"]


def test_provider_that_cannot_be_built_falls_back(monkeypatch):
    # e.g. the optional SDK is not installed, or a custom path is wrong.
    monkeypatch.setattr(retrieve, "SCORE_THRESHOLD", 0.0)
    _seed()
    monkeypatch.setattr(rerank, "RERANK_PROVIDER", "no_such_package.mod:Factory")
    assert rerank.enabled()
    assert "unavailable: ModuleNotFoundError" in rerank.readiness()
    assert rerank.search("write failing tests") == _local("write failing tests")


@pytest.mark.parametrize("bad", [[0.9], [0.9, 0.1, 0.2, 0.3], [1.7, 0.0, 0.0], ["x", 0, 0]])
def test_malformed_judge_output_falls_back(monkeypatch, bad):
    monkeypatch.setattr(retrieve, "SCORE_THRESHOLD", 0.0)
    _seed()
    monkeypatch.setattr(rerank, "RERANK_PROVIDER", "jev")

    class Broken(FakeJudge):
        def fits(self, query, candidates):
            return bad

    monkeypatch.setattr(rerank, "current_judge", lambda: Broken(None))
    assert rerank.search("write failing tests") == _local("write failing tests")


# --- swapping the model ----------------------------------------------------


def test_builtin_providers_are_registered():
    assert set(judges.BUILTIN) == {"jev", "openai"}
    config = JudgeConfig(model="m", timeout=2.0)
    assert isinstance(judges.load("jev", config), JevJudge)
    assert isinstance(judges.load("openai", config), OpenAIDecisionsJudge)
    with pytest.raises(ValueError):
        judges.load("nope", config)


def test_custom_provider_is_loaded_from_a_module_path(monkeypatch):
    _seed()
    monkeypatch.setattr(rerank, "RERANK_PROVIDER", f"{__name__}:FakeJudge")
    monkeypatch.setattr(rerank, "RERANK_MODEL", "my-model")
    monkeypatch.setattr(rerank, "RERANK_TIMEOUT", 1.5)
    assert rerank.readiness() == f"{__name__}:FakeJudge (local)"
    assert rerank.current_judge().config == JudgeConfig(model="my-model", timeout=1.5)
    assert rerank.current_judge() is rerank.current_judge()  # built once
    res = rerank.search("please run tdd")
    assert [h["name"] for h in res["hits"]] == ["tdd"]
    assert res["hits"][0]["score"] == 1.0


CANDIDATES = [
    {"name": "tdd", "description": "write failing tests", "agent": "codex"},
    {"name": "deploy", "description": "x" * 5000, "agent": "local"},
]


def test_jev_judge_sends_only_query_names_and_descriptions():
    sent = {}

    class _Answer:
        def __init__(self, noul):
            self.noul = noul

    class _Response:
        model = "jev-1.14.0"
        usage = type("U", (), {"input_tokens": 321})()
        nouls = {"fit_0": _Answer(0.8), "fit_1": _Answer(0.1)}

    class _Client:
        def system_one(self, state, questions, **kwargs):
            sent.update(state=state, questions=questions, kwargs=kwargs)
            return _Response()

    judge = JevJudge(JudgeConfig(model="jev-1.14.0"))
    judge._client = _Client()
    assert judge.fits("run the tests", CANDIDATES) == [0.8, 0.1]
    assert judge.last_usage == {"model": "jev-1.14.0", "input_tokens": 321}
    assert sent["state"] == {"request": "run the tests"}
    assert sent["kwargs"] == {"model": "jev-1.14.0"}
    assert list(sent["questions"]) == ["fit_0", "fit_1"]
    first = sent["questions"]["fit_0"]
    assert first["type"] == "noul" and "'tdd'" in first["instructions"]
    assert "write failing tests" in first["instructions"]
    assert set(first["criteria"]) == {"true", "false"}
    # Long descriptions are bounded; nothing but name/description is included.
    assert len(sent["questions"]["fit_1"]["instructions"]) < 2000
    assert "codex" not in str(sent["questions"])


def test_jev_judge_reports_missing_sdk_then_missing_key(monkeypatch):
    from skill_rag.judges import jev

    judge = JevJudge(JudgeConfig())
    monkeypatch.setattr(jev.importlib.util, "find_spec", lambda name: None)
    assert "typesafe-sdk not installed" in judge.unavailable_reason()
    monkeypatch.setattr(jev.importlib.util, "find_spec", lambda name: object())
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    assert judge.unavailable_reason() == "TYPESAFE_API_KEY not set"
    monkeypatch.setenv("TYPESAFE_API_KEY", "test-key")
    assert judge.unavailable_reason() is None


def test_openai_judge_request_and_answers(monkeypatch):
    sent = {}

    def post(url, headers, payload, timeout):
        sent.update(url=url, headers=headers, payload=payload, timeout=timeout)
        return {
            "model": "gpt-6-luna",
            "answers": [  # deliberately out of order; matched by name
                {"type": "predicate", "name": "fit_1", "probability": 0.25},
                {"type": "predicate", "name": "fit_0", "probability": 0.75},
            ],
            "usage": {"input_tokens": 353},
        }

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://example.test/v1/")
    judge = OpenAIDecisionsJudge(JudgeConfig(timeout=3.0), post=post)
    assert judge.unavailable_reason() is None
    assert judge.fits("run the tests", CANDIDATES) == [0.75, 0.25]
    assert judge.last_usage == {"model": "gpt-6-luna", "input_tokens": 353}
    assert sent["url"] == "https://example.test/v1/decisions"
    assert sent["headers"] == {"Authorization": "Bearer test-key"}
    assert sent["timeout"] == 3.0
    payload = sent["payload"]
    assert payload["model"] == "gpt-6-luna"  # provider default when unset
    assert payload["input"] == "Request: run the tests"
    assert [q["name"] for q in payload["questions"]] == ["fit_0", "fit_1"]
    assert all(q["type"] == "predicate" for q in payload["questions"])
    assert "'tdd'" in payload["questions"][0]["instructions"]
    assert len(payload["questions"][1]["instructions"]) < 2200
    assert "codex" not in str(payload)


def test_openai_judge_refusal_is_not_a_fit_and_missing_answer_raises(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    answers = [
        {"type": "predicate", "name": "fit_0", "probability": 0.9},
        {"type": "refusal", "name": "fit_1"},
    ]
    judge = OpenAIDecisionsJudge(JudgeConfig(), post=lambda *a: {"answers": answers})
    assert judge.fits("q", CANDIDATES) == [0.9, 0.0]
    judge = OpenAIDecisionsJudge(JudgeConfig(), post=lambda *a: {"answers": answers[:1]})
    with pytest.raises(ValueError):
        judge.fits("q", CANDIDATES)
    monkeypatch.delenv("OPENAI_API_KEY")
    assert judge.unavailable_reason() == "OPENAI_API_KEY not set"


def test_readiness_names_where_data_goes(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(rerank, "RERANK_PROVIDER", "openai")
    assert rerank.readiness() == (
        "openai (sends query and shortlisted descriptions to OpenAI API)"
    )
    monkeypatch.delenv("OPENAI_API_KEY")
    assert rerank.readiness() == (
        "openai (unavailable: OPENAI_API_KEY not set; using local gate)"
    )


# --- a skill the request names outright -------------------------------------


@pytest.mark.parametrize(
    "query",
    [
        "tdd",
        "/tdd add a parser",
        "$tdd add a parser",
        "use the `tdd` skill for this",
        "use the tdd skill to add a parser",
        "TDD skill please",
        "tdd 스킬로 파서 추가해줘",
        "스킬 tdd를 써서 진행해줘",
        "skill: tdd",
    ],
)
def test_a_named_skill_is_returned_without_a_judge(monkeypatch, query):
    _seed()
    calls = _enable(monkeypatch, {})  # the judge would reject everything
    res, provider = rerank.search_traced(query)
    assert [h["name"] for h in res["hits"]] == ["tdd"] and res["status"] == "ok"
    assert res["hits"][0]["score"] == 1.0
    assert provider == "explicit" and calls == []


@pytest.mark.parametrize(
    "query",
    [
        "deploy the website to production",  # an ordinary word
        "improve my deploy skills",  # plural: the user's own skills
        "open src/deploy/main.py",  # a path, not a command
        "run the predeploy check",  # inside another word
        "what does tdd-lite do",  # inside a longer name
        "run the `tdd` package tests",  # code formatting is not a choice of skill
    ],
)
def test_a_bare_mention_is_not_an_explicit_choice(query):
    _seed()
    assert retrieve.explicit_matches(query) == []


def test_named_skills_keep_their_order_and_ignore_the_loaded_exclusion(monkeypatch):
    _seed()
    res = rerank.search("use the deploy skill, then the tdd skill", exclude=frozenset({"tdd"}))
    assert [h["name"] for h in res["hits"]] == ["deploy", "tdd"]
    assert [h["name"] for h in rerank.search("/deploy and /tdd", k=1)["hits"]] == ["deploy"]
    monkeypatch.setattr(rerank, "EXPLICIT", False)
    assert rerank.search("/deploy") == retrieve.search("/deploy")
