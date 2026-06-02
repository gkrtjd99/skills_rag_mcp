# Meta-Skill Bootstrap

## Location

The bootstrap skill lives in two places, both pointing to the same file:

- Source of truth: `~/.skills/using-skill-rag/SKILL.md`
- Each harness's auto-load dir: `~/.<harness>/skills/using-skill-rag/` →
  symlink to the above.

`skill-rag install` (via `make install`) creates the directories and the symlinks. To update
the skill, edit the canonical file; all harnesses see it immediately.

## Why Symlink

- One file to maintain.
- No drift between harnesses.
- Harness's own auto-load mechanism discovers it as a normal skill.

If a harness blocks symlinks, fall back to copy and re-run `skill-rag install`
to refresh.

## Why Excluded from Search

`loader.scan` skips the `using-skill-rag` directory because the skill is
always already in the agent's context. Surfacing it in `search_skills`
results would waste a slot.

## Behavior Contract

The skill body (`bootstrap-skill/using-skill-rag/SKILL.md`) spells out:

- Parent agent: call `search_skills` before responding to any user message.
- Subagent: call only if the parent context describes substantive work.
- Status handling: `ok`/`no_match`/`not_found` each have a terminal action.
- Anti-patterns: no multi-call retries with reworded queries.

The MCP server's response shapes enforce the contract; the skill text
makes the contract explicit to the agent.
