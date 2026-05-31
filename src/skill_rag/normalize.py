"""Text normalization shared by the dense (embedding) path.

Korean queries glue particles to stems and run Latin tokens against Hangul
without spaces (``vercel에``, ``3개``). The multilingual embedding model scores
such glued text noticeably lower than the spaced form (measured: ``코드 리뷰``
0.233 vs ``코드리뷰`` 0.157). Inserting a space at every Hangul/Latin boundary
recovers that signal. Applied identically to queries and to the embedded skill
text so both sides are encoded the same way.
"""

from __future__ import annotations

import re

_LATIN_THEN_HANGUL = re.compile(r"([A-Za-z0-9])([가-힣])")
_HANGUL_THEN_LATIN = re.compile(r"([가-힣])([A-Za-z0-9])")


def normalize_for_dense(text: str) -> str:
    text = _LATIN_THEN_HANGUL.sub(r"\1 \2", text)
    text = _HANGUL_THEN_LATIN.sub(r"\1 \2", text)
    return text
