"""MCP server exposing two tools: search_skills, get_skill.

search_skills: ranked metadata via vector search (auto-syncs on TTL).
get_skill:     full SKILL.md body for a single skill.

Response shapes (mirrored in bootstrap-skill/using-skill-rag/SKILL.md):
  search_skills -> {"status": "ok", "hits": [...]}
                or {"status": "no_match", "hits": [], "message": "..."}
                or {"status": "skip", "hits": [], "message": "..."}
  get_skill     -> {"status": "ok", "body": "..."}
                or {"status": "not_found", "message": "..."}
"""

from __future__ import annotations

from pathlib import Path

from mcp.server.fastmcp import FastMCP

from . import index as index_mod
from . import retrieve
from . import sync as sync_mod
from .corpus import MAX_SEARCH_K, MIN_SEARCH_K

server = FastMCP("skill-rag")


def _path_for_name(name: str) -> Path | None:
    """Look up the indexed SKILL.md path by frontmatter `name`.

    Skill `name` (from frontmatter) does not always equal the directory name —
    e.g. Vercel skills live in ``react-best-practices/`` but their name is
    ``vercel-react-best-practices``. The index is the authoritative mapping.
    """
    for row in index_mod.list_indexed():
        if row["name"] == name:
            return Path(row["path"])
    return None


@server.tool()
def search_skills(query: str, k: int = 5, agent: str | None = None) -> dict:
    """Find skills relevant to ``query``. Call when a new task starts or the
    topic shifts — not on every reply inside an interactive flow. Returns
    metadata only; call ``get_skill`` to fetch the body of any skill that fits.

    Pass ``agent`` as your own harness name (e.g. "claude-code", "codex") so
    each hit can be attributed to its source. Each hit reports the ``agent``
    that owns that skill.

    Response:
      - {"status": "ok", "hits": [{"name", "description", "score", "agent"}, ...]}
      - {"status": "no_match", "hits": [], "message": "..."}
      - {"status": "skip", "hits": [], "message": "..."}  # conversational reply
    """
    if isinstance(k, bool) or not isinstance(k, int) or not MIN_SEARCH_K <= k <= MAX_SEARCH_K:
        raise ValueError(f"k must be an integer between {MIN_SEARCH_K} and {MAX_SEARCH_K}")
    # Cheap guard first: a bare interactive-flow reply ("A", "네", "next") can
    # never need a new skill, so skip before sync and embedding entirely.
    if retrieve.is_conversational(query):
        return retrieve.skip_response()
    sync_mod.sync_if_stale()
    return retrieve.search(query, k=k, agent=agent)


@server.tool()
def get_skill(name: str) -> dict:
    """Fetch the full SKILL.md body for ``name``.

    Response:
      - {"status": "ok", "body": "..."}
      - {"status": "not_found", "message": "..."}
    """
    path = _path_for_name(name)
    if path is not None and path.exists():
        return {"status": "ok", "body": path.read_text(encoding="utf-8")}
    # Not found or path stale — force a sync, retry.
    sync_mod.sync_if_stale(ttl=0)
    path = _path_for_name(name)
    if path is not None and path.exists():
        return {"status": "ok", "body": path.read_text(encoding="utf-8")}
    return {
        "status": "not_found",
        "message": (
            f"Skill '{name}' does not exist in the corpus. "
            f"Do not call get_skill or search_skills for this name again. "
            f"Proceed without it."
        ),
    }


def run() -> None:
    server.run()


if __name__ == "__main__":
    run()
