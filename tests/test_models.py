from skill_rag.models import SearchHit, SkillRecord


def test_skill_record_embed_text_normalizes_hangul_latin_boundary():
    r = SkillRecord(
        name="deploy",
        description="ship",
        path="/x/deploy/SKILL.md",
        body="vercel에 배포",
        content_hash="h",
    )
    assert "vercel 에" in r.embed_text()


def test_skill_record_embed_text_includes_body():
    # The body carries trigger phrases and examples that the one-line
    # description omits, so it must be part of the embedded text.
    r = SkillRecord(
        name="brainstorming",
        description="explore ideas",
        path="/tmp/.skills/brainstorming/SKILL.md",
        body="Use when starting a new feature before writing code.",
        content_hash="abc",
    )
    text = r.embed_text()
    assert text.startswith("brainstorming\nexplore ideas")
    assert "Use when starting a new feature" in text


def test_skill_record_has_agent_default():
    r = SkillRecord(
        name="a", description="d", path="/p", body="b", content_hash="h"
    )
    assert r.agent == "unknown"


def test_search_hit_fields():
    h = SearchHit(name="x", description="y", score=0.9)
    assert h.name == "x"
    assert h.description == "y"
    assert h.score == 0.9


def test_embed_text_includes_translation():
    from skill_rag.models import SkillRecord

    r = SkillRecord(
        name="n", description="Deploy to Vercel", path="p", body="",
        content_hash="h", description_translated="버셀에 배포",
    )
    text = r.embed_text()
    assert "Deploy to Vercel" in text
    assert "버셀에 배포" in text


def test_embed_text_omits_empty_translation():
    from skill_rag.models import SkillRecord

    r = SkillRecord(
        name="n", description="Deploy to Vercel", path="p", body="", content_hash="h",
    )
    # No translation field set -> appears exactly once (from description only).
    assert r.embed_text().count("Deploy to Vercel") == 1
