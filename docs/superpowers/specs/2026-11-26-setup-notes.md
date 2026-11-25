# Setup Notes in `install` and `status`

Date: 2026-11-26
Status: Implemented

## Why

A plain install leaves the judge off. Measured at 350 skills, search without
a judge loaded a useful skill for 69.6% of matching requests, against 93.8%
for a harness that loads every description
(`docs/benchmarks/2026-11-25-native-baseline-results.md`). The READMEs say
so, but someone who runs `make install` and never sets `SKILL_RAG_RERANK`
ends up worse off than before installing and nothing tells them.

Upgrading has a second gap: `install` never overwrites an existing bootstrap
skill, so an agent keeps instructions that predate the `candidates` and
`uncertain` statuses.

## Decision

1. `rerank.notes(indexed)` returns plain sentences for:
   - no usable judge (off, unknown provider, or unavailable): the two measured
     figures and what to set;
   - a judge in the `candidates` style on a corpus above
     `SKILL_RAG_RERANK_SCAN_MAX`: the scan is off and that case was not
     measured;
   - fewer than 50 indexed skills: the approximate cost of the full list
     (about 100 tokens per skill) and that search saves little.
2. `lifecycle.bootstrap_outdated()` compares the installed
   `using-skill-rag/SKILL.md` with the checkout's template; `install` reports
   it as `bootstrap_outdated` (false when it has just refreshed).
3. `skill-rag status` and `skill-rag install` print each note as a `note`
   line and include them as `notes` in `--json`.
4. Notes are advice only. Nothing is blocked, changed, or sent anywhere.

## Limits

`install` and `status` see the environment of the shell they run in, which
may differ from the MCP server's. A judge configured only in the MCP
registration is reported as off by the CLI. The figures in the first note
are from one corpus size and a simulated agent.
