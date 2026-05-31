#!/usr/bin/env bash
# One-shot setup for skill-rag on the current user.
#
#   1. uv sync                                (Python deps)
#   2. Install the bootstrap meta-skill into ~/.skills/
#   3. Symlink the bootstrap into each harness (~/.claude, ~/.codex)
#   4. skill-rag collect                       (gather harness skills via symlink)
#   5. skill-rag sync                          (download model + build LanceDB index)
#   6. Print the MCP registration snippet for each harness
#
# Re-running is safe; every step is idempotent.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SKILLS_DIR="${HOME}/.skills"
BOOTSTRAP_SRC="${REPO_ROOT}/bootstrap-skill/using-skill-rag"
BOOTSTRAP_DST="${SKILLS_DIR}/using-skill-rag"

run_uv() {
  # Force the embedding model to download on first run.
  env SKILL_RAG_LOCAL_FILES_ONLY=0 \
    uv --directory "${REPO_ROOT}" run skill-rag "$@"
}

echo "→ [1/6] uv sync"
(cd "${REPO_ROOT}" && uv sync --quiet)

echo "→ [2/6] Ensuring ${SKILLS_DIR} exists"
mkdir -p "${SKILLS_DIR}"

if [ ! -e "${BOOTSTRAP_DST}" ]; then
  echo "→ [3/6] Installing bootstrap skill → ${BOOTSTRAP_DST}"
  cp -R "${BOOTSTRAP_SRC}" "${BOOTSTRAP_DST}"
else
  echo "→ [3/6] Bootstrap skill already at ${BOOTSTRAP_DST} (skipping)"
fi

for harness in claude codex; do
  HARNESS_SKILLS="${HOME}/.${harness}/skills"
  mkdir -p "${HARNESS_SKILLS}"
  LINK="${HARNESS_SKILLS}/using-skill-rag"
  ln -sfn "${BOOTSTRAP_DST}" "${LINK}"
  echo "    linked ${LINK} → ${BOOTSTRAP_DST}"
done

echo "→ [4/6] Collecting skills from harness installations into ${SKILLS_DIR}"
run_uv collect

echo "→ [5/6] Downloading embedding model + building index"
run_uv sync

cat <<EOF

──────────────────────────────────────────────────────────────────────
Setup complete.

  Skills indexed:    $(uv --directory "${REPO_ROOT}" run skill-rag list-skills --json 2>/dev/null | python3 -c 'import json,sys;print(len(json.load(sys.stdin)))' 2>/dev/null || echo "?")
  Quick status:      uv --directory "${REPO_ROOT}" run skill-rag status
  Re-scan sources:   uv --directory "${REPO_ROOT}" run skill-rag collect && \\
                     uv --directory "${REPO_ROOT}" run skill-rag sync

[6/6] Register the MCP server (one-time per harness).

Claude Code (recommended):
  claude mcp add skill-rag --scope user -- \\
    uv --directory "${REPO_ROOT}" run skill-rag mcp

Or edit ~/.claude.json manually:
  "mcpServers": {
    "skill-rag": {
      "command": "uv",
      "args": ["--directory", "${REPO_ROOT}", "run", "skill-rag", "mcp"]
    }
  }

Codex (~/.codex/config.toml):
  [mcp_servers.skill-rag]
  command = "uv"
  args = ["--directory", "${REPO_ROOT}", "run", "skill-rag", "mcp"]

Restart the harness once registered.
──────────────────────────────────────────────────────────────────────
EOF
