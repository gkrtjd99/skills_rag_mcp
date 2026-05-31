from skill_rag.collect import agent_for_path


def test_claude_path_is_claude_code():
    assert agent_for_path("/Users/x/.claude/plugins/p/skills/foo/SKILL.md") == "claude-code"


def test_codex_path_is_codex():
    assert agent_for_path("/Users/x/.codex/skills/foo/SKILL.md") == "codex"


def test_skills_only_path_is_local():
    assert agent_for_path("/Users/x/.skills/foo/SKILL.md") == "local"


def test_antigravity_path():
    assert agent_for_path("/Users/x/.antigravity/skills/foo/SKILL.md") == "antigravity"
