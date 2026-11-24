"""Local record of what was suggested and what was then loaded.

Every benchmark so far used model-written requests. This log is how real use
becomes data: which skills ``search_skills`` returned, and whether the agent
went on to ``get_skill`` them in the same session. It also remembers which
skills this session already loaded, so they are not suggested again.

Nothing here leaves the machine. Modes (``SKILL_RAG_USAGE_LOG``):

- ``stats`` (default): skill names, scores, statuses, timestamps. No request
  text.
- ``full``: also the request text, for building an evaluation set from real
  requests. Opt-in, because requests can be private.
- ``off``: nothing is written; already-loaded skills are still remembered in
  memory for the session.

A session is one MCP server process.
"""

from __future__ import annotations

import json
import os
import time
import uuid
from collections import Counter
from pathlib import Path

USAGE_LOG = os.environ.get("SKILL_RAG_USAGE_LOG", "stats").strip().lower()
EXCLUDE_LOADED = os.environ.get("SKILL_RAG_EXCLUDE_LOADED", "1").lower() not in {"0", "false", "no"}

_session = uuid.uuid4().hex[:12]
_loaded: set[str] = set()
_suggested: set[str] = set()


def usage_path() -> Path:
    return Path(os.environ.get("SKILL_RAG_USAGE_PATH", "./var/usage.jsonl")).expanduser()


def loaded_this_session() -> frozenset[str]:
    """Skills to leave out of suggestions: already loaded in this session."""
    return frozenset(_loaded) if EXCLUDE_LOADED else frozenset()


def _write(event: dict) -> None:
    if USAGE_LOG not in {"stats", "full"}:
        return
    try:
        path = usage_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps({"ts": round(time.time(), 3), "session": _session, **event}, ensure_ascii=False) + "\n")
    except OSError:
        pass  # a log must never break a search


def record_search(query: str, result: dict, provider: str) -> None:
    hits = [{"name": h["name"], "score": h["score"]} for h in result.get("hits", [])]
    _suggested.update(h["name"] for h in hits)
    event = {"event": "search", "status": result.get("status"), "provider": provider or "gate", "hits": hits}
    if USAGE_LOG == "full":
        event["query"] = query
    _write(event)


def record_load(name: str, found: bool) -> None:
    if found:
        _loaded.add(name)
    _write({"event": "load", "name": name, "found": found, "suggested": name in _suggested})


def stats(path: Path | None = None) -> dict:
    """Per-skill counts: how often suggested, and how often loaded after being
    suggested in the same session."""
    path = path or usage_path()
    suggested: Counter = Counter()
    loaded_after: Counter = Counter()
    loaded_unprompted: Counter = Counter()
    searches = empty = 0
    seen: dict[str, set] = {}
    counted: dict[str, set] = {}
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        lines = []
    for line in lines:
        try:
            e = json.loads(line)
        except json.JSONDecodeError:
            continue
        session = e.get("session", "")
        if e.get("event") == "search":
            searches += 1
            empty += not e.get("hits")
            for h in e.get("hits", []):
                suggested[h["name"]] += 1
                seen.setdefault(session, set()).add(h["name"])
        elif e.get("event") == "load" and e.get("found"):
            name = e["name"]
            if name in counted.setdefault(session, set()):
                continue
            counted[session].add(name)
            (loaded_after if name in seen.get(session, set()) else loaded_unprompted)[name] += 1
    skills = {
        name: {
            "suggested": suggested[name],
            "loaded_after_suggestion": loaded_after[name],
            "loaded_without_suggestion": loaded_unprompted[name],
        }
        for name in sorted(set(suggested) | set(loaded_after) | set(loaded_unprompted))
    }
    return {
        "searches": searches,
        "searches_with_no_hit": empty,
        "suggestions": sum(suggested.values()),
        "loaded_after_suggestion": sum(loaded_after.values()),
        "loaded_without_suggestion": sum(loaded_unprompted.values()),
        "skills": skills,
    }
