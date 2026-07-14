# Security and privacy

skill-rag is local-first. Embeddings, translation, indexing, and MCP serving
run on the user's machine. The repository must not contain a user's `~/.skills`
corpus, LanceDB indexes, model caches, or generated benchmark output.

Do not add raw user queries, `SKILL.md` bodies, local paths, credentials, or
tokens to logs, traces, metrics, fixtures, or issue reports. Optional local
OpenTelemetry/AgentOTelStack experiments belong in a private branch or patch
unless a future generic, opt-in telemetry design is explicitly approved.

If a security issue is found, do not publish the sensitive corpus or token in a
public issue. Remove or redact it first and contact the repository maintainer.
