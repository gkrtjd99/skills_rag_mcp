"""Local ko↔en translation of skill descriptions (index-time augmentation).

Detects the description's language and translates it to the OTHER language so a
query in either Korean or English retrieves the skill. Runs entirely locally via
MarianMT (opus-mt) — no cloud calls. Enable explicitly with
SKILL_RAG_TRANSLATE=1; native E5 retrieval is the default path.

Mirrors embed.py: env-driven config, lazy model load, model cached per direction.
"""

from __future__ import annotations

import os
import re
from functools import lru_cache

from .offline import enforce_hf_offline

# E5 provides the primary Korean/English cross-lingual signal without a
# second model. Translation remains available as an explicit local-only
# augmentation for corpora that need it, but must not slow the default sync.
TRANSLATE_ENABLED = os.environ.get("SKILL_RAG_TRANSLATE", "0").lower() not in {
    "0",
    "false",
    "no",
}
LOCAL_FILES_ONLY = os.environ.get("SKILL_RAG_LOCAL_FILES_ONLY", "1").lower() not in {
    "0",
    "false",
    "no",
}
MT_KO_EN = os.environ.get("SKILL_RAG_MT_KO_EN", "Helsinki-NLP/opus-mt-ko-en")
MT_EN_KO = os.environ.get("SKILL_RAG_MT_EN_KO", "Helsinki-NLP/opus-mt-en-ko")
MAX_LENGTH = int(os.environ.get("SKILL_RAG_MT_MAX_LENGTH", "512"))

_HANGUL = re.compile(r"[가-힣]")
_LATIN = re.compile(r"[A-Za-z]")


def detect_lang(text: str) -> str:
    """Return 'ko' if Hangul characters outnumber Latin ones, else 'en' (tie → 'en')."""
    return "ko" if len(_HANGUL.findall(text)) > len(_LATIN.findall(text)) else "en"


def is_translatable(text: str) -> bool:
    return bool(text.strip() and (_HANGUL.search(text) or _LATIN.search(text)))


@lru_cache(maxsize=2)
def _load_model(name: str):
    enforce_hf_offline(LOCAL_FILES_ONLY)
    # Imported lazily so importing this module stays cheap (helps tests).
    from transformers import MarianMTModel, MarianTokenizer

    tok = MarianTokenizer.from_pretrained(name, local_files_only=LOCAL_FILES_ONLY)
    model = MarianMTModel.from_pretrained(name, local_files_only=LOCAL_FILES_ONLY)
    return tok, model


def _run_model(text: str, name: str) -> str:
    tok, model = _load_model(name)
    # Same limit for input and output: MarianMT output length tracks input for short text.
    batch = tok([text], return_tensors="pt", truncation=True, max_length=MAX_LENGTH)
    generated = model.generate(**batch, max_length=MAX_LENGTH)
    return tok.batch_decode(generated, skip_special_tokens=True)[0]


def translate_for_index(text: str) -> tuple[str, str]:
    """Translate ``text`` and return (translated_text, status).

    Status values:
    - ok: translated text is present.
    - disabled: translation is disabled by env.
    - skipped: text is empty or has no translatable script.
    - failed: model load/run failed, or the model returned empty text.
    """
    if not TRANSLATE_ENABLED:
        return "", "disabled"
    if not is_translatable(text):
        return "", "skipped"
    name = MT_KO_EN if detect_lang(text) == "ko" else MT_EN_KO
    try:
        out = _run_model(text, name).strip()
    except Exception:
        return "", "failed"
    if not out:
        return "", "failed"
    return out, "ok"


def translate(text: str) -> str:
    """Translate ``text`` to the other language (ko↔en).

    Returns "" when disabled, on empty input, or on ANY failure (so indexing
    proceeds without the augmentation rather than crashing).
    """
    return translate_for_index(text)[0]
