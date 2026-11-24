# Security and privacy

skill-rag is local-first. Embeddings, translation, indexing, and MCP serving
run on the user's machine. The one exception is opt-in: with
`SKILL_RAG_RERANK` set, each search sends the query text and the names and
descriptions of up to 16 shortlisted skills to the chosen judge's provider
(`jev`: TypeSafe API; `openai`: OpenAI API; a custom judge: wherever it sends
them). Skill bodies, local paths, and the rest of the corpus are not sent, and
nothing is sent when the variable is unset. `skill-rag status` names the
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
