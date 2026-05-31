"""Classify which harness a skill came from, by its filesystem path.

Kept dependency-free (no internal imports) so both ``loader`` and ``collect``
can import it without creating an import cycle.
"""

from __future__ import annotations

from pathlib import Path

_KNOWN = {
    ".claude": "claude-code",
    ".codex": "codex",
    ".antigravity": "antigravity",
}


def agent_for_path(path: str | Path) -> str:
    """Return the source harness for a resolved skill path.

    Keys off the ``.<harness>`` home-dir segment. A skill living directly under
    ``~/.skills`` (no harness segment) is ``local`` — registered here by the
    user rather than pulled from an agent's install.
    """
    for part in Path(path).parts:
        if part in _KNOWN:
            return _KNOWN[part]
    return "local"
