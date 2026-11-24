# Store-Only Skills: adopt and restore

Date: 2026-11-24
Status: Implemented

## Problem

`collect` links to skills where the harness installed them. The harness keeps
listing every skill's description in each session (about 32,000 characters for
a 45-skill corpus), so skill-rag adds a bootstrap skill and search responses
on top of the native cost instead of replacing it. The measured gain of the
judge path (search responses of about 235 characters) is small next to that.
Skills installed per project have the same cost plus duplication across
projects.

## Decision

Let the store be a skill's only home, explicitly and reversibly.

- `skill-rag adopt [names] [--from DIR]` moves skill directories into
  `~/.skills/`. Default sources are `~/.claude/skills` and `~/.codex/skills`;
  `--from` accepts any skill root, including a project's `.claude/skills`.
- `skill-rag restore [names]` moves them back.
- `get_skill` returns `path`, the skill directory, because an adopted skill is
  not installed anywhere the agent's harness knows about and its bundled files
  would otherwise be unreachable.

## Rules

- Only direct children of a source that contain `SKILL.md` are candidates. No
  recursion: plugin caches and app-managed nested folders are not ours to move.
- Symlinked entries are skipped; something else owns them. The one exception
  is the store's own `collect` link to the same directory, which adopt replaces
  with the real directory.
- Never overwrite: an existing store entry blocks adopt; a reoccupied origin
  blocks restore. Both are reported, not forced.
- Each move is written to the install state (`adopted: name -> {origin,
  store}`) before the move, so an interrupted adopt is still restorable.
- `uninstall` restores adopted skills before removing anything. A skill that
  cannot be restored stays in the store even under `--purge`, and the state
  file is kept so a later `restore` works.
- adopt asks for confirmation unless `--yes` or `--dry-run`.

## Consequences

- The harness lists only the bootstrap skill after a restart. Whether a skill
  gets used now depends on the agent calling `search_skills`; a prompt hook
  that calls it deterministically is separate work.
- Adopted skills lose harness-native features: `/skill-name` invocation and
  per-skill tool permissions.
- Adopted skills report `agent: "local"`, since attribution is path-based.
- External installers that track their own copies (for example a skills CLI
  with a lock file) may reinstall a skill that was moved away.
- Project scoping is gone for adopted project skills: they are offered in
  every project. A project overlay index is separate work.

## Not changed

The default `install` still only collects by symlink. Nothing moves unless the
user runs `adopt`.

`install --no-collect` skips that collection. On the test machine the default
collection would have linked 303 skills, most of them from plugin caches,
which is not what a store meant to hold chosen skills should contain.
