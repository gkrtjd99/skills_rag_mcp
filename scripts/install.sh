#!/usr/bin/env bash
# Install skill-rag for the current user.
# - Creates ~/.skills/ (the central corpus)
# - Installs the bootstrap skill at ~/.skills/using-skill-rag/
# - Symlinks ~/.<harness>/skills/using-skill-rag -> ~/.skills/using-skill-rag
# - Prints MCP server registration instructions per harness

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SKILLS_DIR="${HOME}/.skills"
BOOTSTRAP_SRC="${REPO_ROOT}/bootstrap-skill/using-skill-rag"
BOOTSTRAP_DST="${SKILLS_DIR}/using-skill-rag"

echo "→ Ensuring ${SKILLS_DIR} exists"
mkdir -p "${SKILLS_DIR}"

if [ ! -d "${BOOTSTRAP_DST}" ]; then
  echo "→ Installing bootstrap skill to ${BOOTSTRAP_DST}"
  cp -R "${BOOTSTRAP_SRC}" "${BOOTSTRAP_DST}"
else
  echo "→ Bootstrap skill already present at ${BOOTSTRAP_DST} (skipping copy)"
fi

for harness in claude codex; do
  HARNESS_SKILLS="${HOME}/.${harness}/skills"
  mkdir -p "${HARNESS_SKILLS}"
  LINK="${HARNESS_SKILLS}/using-skill-rag"
  echo "→ Linking ${LINK} → ${BOOTSTRAP_DST}"
  ln -sfn "${BOOTSTRAP_DST}" "${LINK}"
done

cat <<EOF

Done. Next step — register the MCP server in each harness.

Claude Code:
  Add to ~/.claude.json under "mcpServers":
    "skill-rag": {
      "command": "uv",
      "args": ["--directory", "${REPO_ROOT}", "run", "skill-rag", "mcp"]
    }

Codex:
  See the Codex docs for MCP server registration. Use the same command:
    uv --directory ${REPO_ROOT} run skill-rag mcp

After registering, restart the harness so the MCP server is picked up.
EOF
