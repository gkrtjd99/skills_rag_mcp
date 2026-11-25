# Security and privacy

skill-rag is local-first. Embeddings, translation, indexing, and MCP serving
run on the user's machine. The one exception is opt-in: with
`SKILL_RAG_RERANK` set, each search sends to the chosen judge's provider
(`jev`: TypeSafe API; `openai`: OpenAI API; a custom judge: wherever it sends
them) the query text, the name and first 120 characters of the description of
every indexed skill (the whole-corpus scan, for corpora up to
`SKILL_RAG_RERANK_SCAN_MAX`, default 500), and the names and full
descriptions of the 16 shortlisted skills. With `SKILL_RAG_RERANK_SCAN_MAX=0`
only the query and the 16 shortlisted names and descriptions are sent. Skill
bodies and local paths are never sent, and nothing is sent when
`SKILL_RAG_RERANK` is unset. `skill-rag status` names the
destination. Keep `TYPESAFE_API_KEY` and `OPENAI_API_KEY` in the environment,
never in the repository. The repository must not contain a user's `~/.skills`
corpus, LanceDB indexes, model caches, or generated benchmark output.

A local usage log (`var/usage.jsonl`) records which skills were suggested and
loaded. By default it holds no request text; `SKILL_RAG_USAGE_LOG=full` adds
it, on the user's machine only, and `off` disables the log.

Do not add raw user queries, `SKILL.md` bodies, local paths, credentials, or
tokens to logs, traces, metrics, fixtures, or issue reports. Optional local
OpenTelemetry/AgentOTelStack experiments belong in a private branch or patch
unless a future generic, opt-in telemetry design is explicitly approved.

If a security issue is found, do not publish the sensitive corpus or token in a
public issue. Remove or redact it first and contact the repository maintainer.
