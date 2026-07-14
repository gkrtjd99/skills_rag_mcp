from __future__ import annotations

from dataclasses import dataclass

from .corpus import DENSE_BODY_CHARS
from .normalize import normalize_for_dense


@dataclass(slots=True)
class SkillRecord:
    name: str
    description: str
    path: str
    body: str
    content_hash: str
    agent: str = "unknown"  # source harness: claude-code, codex, local, ...
    description_translated: str = ""  # ko↔en translation, filled at sync time
    translation_status: str = "pending"  # ok, failed, disabled, skipped, pending

    def embed_text(self) -> str:
        # Stable string we embed AND index for lexical (BM25) search.
        # Body is included because it carries the trigger phrases and
        # examples that the one-line description omits. The embedding model
        # truncates to its max sequence length, so this mainly adds the
        # body's intro to the dense vector while giving BM25 the full text.
        # The ko↔en translation of the description (when present) lets a query
        # in either language match. Changing this requires a reindex.
        parts = [self.name, self.description]
        if self.description_translated.strip():
            parts.append(self.description_translated.strip())
        if self.body.strip():
            parts.append(self.body.strip())
        return normalize_for_dense("\n".join(parts))

    def dense_text(self) -> str:
        """Return the compact semantic passage used for vector encoding.

        The full body remains in :meth:`embed_text` for BM25. Encoding an
        entire instruction body made large-corpus sync spend most of its time
        padding irrelevant tail content, while names, descriptions, and the
        opening trigger section carry the skill-discovery signal.
        """
        parts = [self.name, self.description]
        if self.description_translated.strip():
            parts.append(self.description_translated.strip())
        if self.body.strip() and DENSE_BODY_CHARS > 0:
            parts.append(self.body.strip()[:DENSE_BODY_CHARS])
        return normalize_for_dense("\n".join(parts))


@dataclass(slots=True)
class SearchHit:
    name: str
    description: str
    score: float
