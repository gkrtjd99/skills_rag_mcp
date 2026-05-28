from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class SkillRecord:
    name: str
    description: str
    path: str
    body: str
    content_hash: str

    def embed_text(self) -> str:
        # Stable string we embed. Changing this requires a reindex.
        return f"{self.name}\n{self.description}"


@dataclass(slots=True)
class SearchHit:
    name: str
    description: str
    score: float
