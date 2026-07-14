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
_HAS_HANGUL = re.compile(r"[가-힣]")

# Small, deterministic query hints cover the high-value intent vocabulary that
# commonly appears in Korean requests while the indexed skill descriptions are
# English. The multilingual E5 model remains the primary signal; these hints
# only prevent a low-confidence Korean paraphrase from falling below the
# no-match threshold and also give BM25 exact English trigger terms.
_KO_QUERY_HINTS = {
    "회귀": "regression regressions",
    "구현": "implementation implement",
    "위험": "risk",
    "점검": "inspect check review audit",
    "리뷰": "review",
    "버그": "bug bugs",
    "테스트": "test tests",
    "배포": "deploy deployment publish",
    "웹사이트": "website web site",
    "사이트": "site website",
    "스킬": "skill",
    "만들": "create author",
    "설명": "description",
    "검색": "search discover",
    "개선": "improve",
    "추적": "tracked",
    "파일": "file files",
    "민감": "sensitive",
    "찾아": "find search",
    "저장소": "repository",
    "커밋": "commit",
    "유지보수": "maintainability",
    "문제점": "issues problems",
    "검토": "review inspect",
    "빠진": "missing gaps",
    "트리거": "trigger",
    "지침": "instructions",
    "정상": "working verify",
    "개인": "personal private",
    "경로": "path",
    "유출": "leak expose",
    "비밀번호": "password secret credential",
    "토큰": "token",
    "파서": "parser",
    "파이썬": "python",
    "실패": "fail failing",
    "원인": "debug cause",
    "프리뷰": "preview",
    "주소": "url address",
    "확인": "verify check",
    "온라인": "online",
    "게시": "publish",
    "작성": "write create",
    "새": "new",
    "데이터베이스": "database",
    "튜닝": "tuning optimize",
    "요구사항": "requirements",
    "설계": "design",
}


def normalize_for_dense(text: str) -> str:
    text = _LATIN_THEN_HANGUL.sub(r"\1 \2", text)
    text = _HANGUL_THEN_LATIN.sub(r"\1 \2", text)
    return text


def expand_for_retrieval(text: str) -> str:
    """Append compact English intent hints to Korean retrieval queries."""
    if not _HAS_HANGUL.search(text):
        return text
    hints: list[str] = []
    for korean, english in _KO_QUERY_HINTS.items():
        if korean in text:
            hints.append(english)
    if not hints:
        return text
    return f"{text} {' '.join(hints)}"
