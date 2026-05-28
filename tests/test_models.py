from skill_rag.models import SearchHit, SkillRecord


def test_skill_record_embed_text():
    r = SkillRecord(
        name="brainstorming",
        description="explore ideas",
        path="/tmp/.skills/brainstorming/SKILL.md",
        body="# body",
        content_hash="abc",
    )
    assert r.embed_text() == "brainstorming\nexplore ideas"


def test_search_hit_fields():
    h = SearchHit(name="x", description="y", score=0.9)
    assert h.name == "x"
    assert h.description == "y"
    assert h.score == 0.9
