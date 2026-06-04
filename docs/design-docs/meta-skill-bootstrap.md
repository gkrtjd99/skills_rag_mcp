# Meta-Skill Bootstrap

## Location

The repository ships a bootstrap template at:

- `bootstrap-skill/using-skill-rag/SKILL.md`

`skill-rag install` copies that template into the user corpus if it is missing:

- `~/.skills/using-skill-rag/SKILL.md`

Each supported harness then gets a symlink from its auto-load directory to the
installed corpus copy:

- `~/.claude/skills/using-skill-rag -> ~/.skills/using-skill-rag`
- `~/.codex/skills/using-skill-rag -> ~/.skills/using-skill-rag`

The installed corpus copy is the runtime source of truth. Editing it affects
all harnesses immediately because the harness entries are symlinks.

## Why Symlink

- One runtime copy for every harness.
- No drift between Claude Code and Codex.
- Harness auto-load mechanisms still see a normal skill directory.

If a harness blocks symlinks, copy the installed bootstrap directory manually
and refresh it when the canonical file changes.

## Why Excluded From Search

`loader.scan` skips `using-skill-rag` because the skill is always already in
the agent's context. Returning it from `search_skills` would waste a result
slot and could encourage self-referential calls.

## Behavior Contract

The skill body requires:

- Parent agent: call `search_skills` when a new task starts or the topic
  shifts — not on every user message. Inside a sustained interactive flow
  (interview/wizard/Q&A coaching) where the user is merely answering, do not
  re-search until a new task appears.
- Subagent: call only when the parent context describes substantive work.
- Caller: pass `agent=<harness name>` when known.
- Status handling: `ok`, `no_match`, `skip`, and `not_found` each have a
  terminal action.
- Anti-patterns: no per-turn searching inside an established interactive flow;
  no multi-call retries with reworded queries.

The MCP server's response shapes enforce the contract; the skill text makes it
explicit to the agent.
