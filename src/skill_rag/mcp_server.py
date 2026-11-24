"""MCP server exposing two tools: search_skills, get_skill.

search_skills: ranked metadata via hybrid search (auto-syncs on TTL).
get_skill:     full SKILL.md body for a single skill.

Response shapes (mirrored in bootstrap-skill/using-skill-rag/SKILL.md):
  search_skills -> {"status": "ok", "hits": [...]}
                or {"status": "no_match", "hits": [], "message": "..."}
                or {"status": "skip", "hits": [], "message": "..."}
  get_skill     -> {"status": "ok", "body": "...", "path": "<skill directory>"}
                or {"status": "not_found", "message": "..."}
"""

from __future__ import annotations

from pathlib import Path

from mcp.server.fastmcp import FastMCP

from . import index as index_mod
from . import rerank
from . import retrieve
from . import sync as sync_mod
from . import usage
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
    """Search skill metadata for a new task or materially changed topic.

    Search once per task; call ``get_skill`` only for a clearly relevant hit.
    """
    if isinstance(k, bool) or not isinstance(k, int) or not MIN_SEARCH_K <= k <= MAX_SEARCH_K:
        raise ValueError(f"k must be an integer between {MIN_SEARCH_K} and {MAX_SEARCH_K}")
    # Cheap guard first: a bare interactive-flow reply ("A", "네", "next") can
    # never need a new skill, so skip before sync and embedding entirely.
    if retrieve.is_conversational(query):
        return retrieve.skip_response()
    sync_mod.sync_if_stale()
    # Local hybrid gate by default; opt-in Jev fit judgment (SKILL_RAG_RERANK).
    result, provider = rerank.search_traced(
        query, k=k, agent=agent, exclude=usage.loaded_this_session()
    )
    # ``provider`` is what produced this result, so a fallback is logged as the gate.
    usage.record_search(query, result, provider)
    return result


def _skill_response(skill_md: Path) -> dict:
    # A skill served only through this tool is not loaded by the harness, so
    # the agent has no other way to learn where its bundled files live.
    return {
        "status": "ok",
        "body": skill_md.read_text(encoding="utf-8"),
        "path": str(skill_md.parent),
    }


@server.tool()
def get_skill(name: str) -> dict:
    """Fetch the full SKILL.md body for one returned skill name.

    ``path`` is the skill's directory: resolve files the body refers to
    (scripts, references, assets) relative to it.
    """
    path = _path_for_name(name)
    if path is None or not path.exists():
        # Not found or path stale — force a sync, retry.
        sync_mod.sync_if_stale(ttl=0)
        path = _path_for_name(name)
    found = path is not None and path.exists()
    usage.record_load(name, found)
    if found:
        return _skill_response(path)
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
