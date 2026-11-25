# Uncertain Candidates and Explicitly Named Skills

Date: 2026-11-25
Status: Implemented; uncertain band measured with a simulated agent, explicit
names covered by tests only

## Why

With a judge, 13% of matching dev requests lost the right skill because its
probability fell below 0.9 although it was among the candidates. Four changes
to the judge did not recover them. The caller of `search_skills` is a stronger
model than the judge and reads the result anyway, so the uncertain cases can
be handed to it. Separately, a request that names a skill was treated like any
other and could lose that skill to the threshold.

## Decision

1. **`uncertain` status.** `search_skills` may answer
   `{status: "uncertain", hits: [{name, description, confidence: "low"}],
   message}`. Hits carry no `score` and no `agent`. The message tells the
   caller to load one only if its description clearly covers the task.
2. **Uncertain band with a judge (default on).** When no candidate reaches
   `SKILL_RAG_RERANK_THRESHOLD`, the single best candidate at or above
   `SKILL_RAG_RERANK_UNCERTAIN_FROM` (default 0.7) is returned as `uncertain`
   with a 120-character description. A value at or above the threshold turns
   it off. Below 0.7 the answer stays `no_match`.
3. **Local candidates without a judge (default off).**
   `SKILL_RAG_LOCAL_CANDIDATES=N` returns the top N of the local ranking as
   `uncertain` (300-character descriptions) instead of the gate's result, also
   when a configured judge fails. Default 0: the gate, unchanged.
4. **Explicitly named skills (default on).** If the query names an indexed
   skill outright, that skill is returned as `ok` with `score` 1.0 before any
   ranking or judgment, ignoring the already-loaded exclusion. Accepted forms:
   the whole query is the name; `/name` or `$name` at the start of a word;
   the name next to the word skill (`name skill`, `name 스킬`, `skill name`,
   `스킬 name`, `skill: name`). Not accepted: a bare mention, a quoted or
   backticked name, the plural `skills`, a name followed by a file extension.
   `SKILL_RAG_EXPLICIT=0` turns it off. The usage log records the provider as
   `explicit`.
5. The bootstrap skill documents `uncertain` (load at most one that clearly
   fits; no reworded retry) and tells agents to keep a user's skill name in
   the query.

## Evidence

`docs/benchmarks/2026-11-25-agent-results.md` (first dev set, not adopted) and
`docs/benchmarks/2026-11-25-agent2-results.md` (new dev set, fresh test). On
the fresh test a simulated agent loaded a useful skill for 67.0% of matching
requests with the band against 60.3% without, and a wrong skill for 8.2% of
no-match requests against 4.1%. Local candidates without a judge loaded a
useful skill less often than the gate's result read by the same agent (62.9%
against 69.6%), which is why item 3 is off by default.

The explicit-name rule matched none of 1,372 benchmark requests, none of which
names a skill; the quoted form was dropped because it matched a package name
written as code. No benchmark contains requests that do name a skill.

## Privacy

Nothing new leaves the machine. The band reuses probabilities the judge
already returned; explicit matching and local candidates are local.

## Limits

The agent in the benchmark is one model call with an empty context and not the
model of a real harness. Only `jev` was measured for the band. An agent that
loads uncertain candidates too readily would raise wrong loads; the usage log
(`loaded after suggestion`) is the way to see that in real use.
