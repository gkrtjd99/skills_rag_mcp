# Multilingual Description Auto-Translation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** At index time, translate each skill `description` to the other language (ko↔en) with a local MarianMT model and fold it into the embedded/BM25 text, so a query in either language retrieves a skill whose description is written in the other.

**Architecture:** A new `translate.py` module (mirrors `embed.py`'s lazy-load + env conventions) detects the description language and runs `opus-mt-ko-en` / `opus-mt-en-ko` locally. `SkillRecord` gains a `description_translated` field that `embed_text()` appends — so the translation reaches both the dense vector and the BM25 `text` with no schema change. `sync.run_sync` fills that field only for added/changed records (content-hash cache), so unchanged skills are never re-translated.

**Tech Stack:** Python 3.13, transformers (MarianMT) — already present via sentence-transformers — plus `sentencepiece` + `sacremoses`, pytest.

**Baseline:** branch `feat/multilingual-description-translation` at HEAD `fac9b03` (spec committed). Corpus is currently empty, so no live index migration is needed.

---

### Task 1: Add `sentencepiece` + `sacremoses` dependencies + reference doc

**Files:**
- Modify: `pyproject.toml` (the `dependencies` list)
- Create: `docs/references/opus-mt-llms.txt`

- [ ] **Step 1: Add the dependencies**

In `pyproject.toml`, add two entries to the end of the `dependencies` list (it currently ends with `"tomlkit>=0.13.0",`):

```toml
    "sentencepiece>=0.2.0",
    "sacremoses>=0.1.1",
```

- [ ] **Step 2: Sync the environment**

Run: `uv sync`
Expected: resolves and installs `sentencepiece` and `sacremoses` (exit 0).

- [ ] **Step 3: Add the reference doc**

Create `docs/references/opus-mt-llms.txt`:

```
# opus-mt (MarianMT) quick reference

Local ko<->en translation for skill_rag (translate.py). No cloud calls.
Models: Helsinki-NLP/opus-mt-ko-en, Helsinki-NLP/opus-mt-en-ko.
Tokenizer needs sentencepiece + sacremoses.

from transformers import MarianMTModel, MarianTokenizer

tok = MarianTokenizer.from_pretrained(name, local_files_only=True)
model = MarianMTModel.from_pretrained(name, local_files_only=True)
batch = tok([text], return_tensors="pt", truncation=True, max_length=512)
out = model.generate(**batch, max_length=512)
text = tok.batch_decode(out, skip_special_tokens=True)[0]

Models download on first `make install` (SKILL_RAG_LOCAL_FILES_ONLY=0).
Disable translation entirely with SKILL_RAG_TRANSLATE=0.
```

- [ ] **Step 4: Verify the imports resolve**

Run: `uv run python -c "import sentencepiece, sacremoses; print('ok')"`
Expected: prints `ok` (exit 0).

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml uv.lock docs/references/opus-mt-llms.txt
git commit -m "build: add sentencepiece + sacremoses for opus-mt translation"
```

---

### Task 2: `translate.py` module

**Files:**
- Create: `src/skill_rag/translate.py`
- Test: `tests/test_translate.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_translate.py`:

```python
from skill_rag import translate


def test_detect_lang_korean():
    assert translate.detect_lang("벌집에 배포하는 스킬") == "ko"


def test_detect_lang_english():
    assert translate.detect_lang("Deploy to Vercel") == "en"


def test_detect_lang_mixed_dominant_korean():
    assert translate.detect_lang("배포 자동화 스킬 모음") == "ko"


def test_detect_lang_empty_is_english():
    assert translate.detect_lang("   ") == "en"


def test_translate_korean_uses_ko_en_model(monkeypatch):
    seen = {}

    def fake(text, name):
        seen["name"] = name
        return f"EN: {text}"

    monkeypatch.setattr(translate, "_run_model", fake)
    monkeypatch.setattr(translate, "TRANSLATE_ENABLED", True)
    out = translate.translate("배포 스킬")
    assert seen["name"] == translate.MT_KO_EN
    assert out == "EN: 배포 스킬"


def test_translate_english_uses_en_ko_model(monkeypatch):
    seen = {}

    def fake(text, name):
        seen["name"] = name
        return f"KO: {text}"

    monkeypatch.setattr(translate, "_run_model", fake)
    monkeypatch.setattr(translate, "TRANSLATE_ENABLED", True)
    out = translate.translate("Deploy app")
    assert seen["name"] == translate.MT_EN_KO
    assert out == "KO: Deploy app"


def test_translate_disabled_returns_empty(monkeypatch):
    monkeypatch.setattr(translate, "TRANSLATE_ENABLED", False)
    assert translate.translate("배포 스킬") == ""


def test_translate_empty_returns_empty(monkeypatch):
    monkeypatch.setattr(translate, "TRANSLATE_ENABLED", True)
    assert translate.translate("   ") == ""


def test_translate_failure_returns_empty(monkeypatch):
    def boom(text, name):
        raise RuntimeError("model not cached")

    monkeypatch.setattr(translate, "_run_model", boom)
    monkeypatch.setattr(translate, "TRANSLATE_ENABLED", True)
    assert translate.translate("Deploy app") == ""
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_translate.py -q`
Expected: FAIL (`ModuleNotFoundError: No module named 'skill_rag.translate'`).

- [ ] **Step 3: Write the implementation**

Create `src/skill_rag/translate.py`:

```python
"""Local ko↔en translation of skill descriptions (index-time augmentation).

Detects the description's language and translates it to the OTHER language so a
query in either Korean or English retrieves the skill. Runs entirely locally via
MarianMT (opus-mt) — no cloud calls. Disable with SKILL_RAG_TRANSLATE=0.

Mirrors embed.py: env-driven config, lazy model load, model cached per direction.
"""

from __future__ import annotations

import os
import re
from functools import lru_cache

TRANSLATE_ENABLED = os.environ.get("SKILL_RAG_TRANSLATE", "1").lower() not in {
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
    """Return 'ko' if Hangul dominates the text, else 'en'."""
    return "ko" if len(_HANGUL.findall(text)) > len(_LATIN.findall(text)) else "en"


@lru_cache(maxsize=2)
def _load(name: str):
    # Imported lazily so importing this module stays cheap (helps tests).
    from transformers import MarianMTModel, MarianTokenizer

    tok = MarianTokenizer.from_pretrained(name, local_files_only=LOCAL_FILES_ONLY)
    model = MarianMTModel.from_pretrained(name, local_files_only=LOCAL_FILES_ONLY)
    return tok, model


def _run_model(text: str, name: str) -> str:
    tok, model = _load(name)
    batch = tok([text], return_tensors="pt", truncation=True, max_length=MAX_LENGTH)
    generated = model.generate(**batch, max_length=MAX_LENGTH)
    return tok.batch_decode(generated, skip_special_tokens=True)[0]


def translate(text: str) -> str:
    """Translate ``text`` to the other language (ko↔en).

    Returns "" when disabled, on empty input, or on ANY failure (so indexing
    proceeds without the augmentation rather than crashing).
    """
    if not TRANSLATE_ENABLED or not text.strip():
        return ""
    name = MT_KO_EN if detect_lang(text) == "ko" else MT_EN_KO
    try:
        return _run_model(text, name).strip()
    except Exception:
        return ""
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/test_translate.py -q`
Expected: PASS (8 tests). No real model loads — `_run_model` is stubbed and the model-loading tests set `TRANSLATE_ENABLED`.

- [ ] **Step 5: Commit**

```bash
git add src/skill_rag/translate.py tests/test_translate.py
git commit -m "feat(translate): local ko↔en description translation"
```

---

### Task 3: `SkillRecord.description_translated` + `embed_text`

**Files:**
- Modify: `src/skill_rag/models.py`
- Test: `tests/test_models.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_models.py`:

```python
def test_embed_text_includes_translation():
    from skill_rag.models import SkillRecord

    r = SkillRecord(
        name="n", description="Deploy to Vercel", path="p", body="",
        content_hash="h", description_translated="버셀에 배포",
    )
    text = r.embed_text()
    assert "Deploy to Vercel" in text
    assert "버셀에 배포" in text


def test_embed_text_omits_empty_translation():
    from skill_rag.models import SkillRecord

    r = SkillRecord(
        name="n", description="Deploy to Vercel", path="p", body="", content_hash="h",
    )
    # No translation field set -> appears exactly once (from description only).
    assert r.embed_text().count("Deploy to Vercel") == 1
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_models.py -k embed_text -q`
Expected: FAIL (`TypeError: ... unexpected keyword argument 'description_translated'`).

- [ ] **Step 3: Write the implementation**

In `src/skill_rag/models.py`, add the field to `SkillRecord` (after the existing `agent` field) and update `embed_text()`:

```python
@dataclass(slots=True)
class SkillRecord:
    name: str
    description: str
    path: str
    body: str
    content_hash: str
    agent: str = "unknown"  # source harness: claude-code, codex, local, ...
    description_translated: str = ""  # ko↔en translation, filled at sync time

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
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/test_models.py -q`
Expected: PASS (existing + 2 new).

- [ ] **Step 5: Commit**

```bash
git add src/skill_rag/models.py tests/test_models.py
git commit -m "feat(models): SkillRecord.description_translated folded into embed_text"
```

---

### Task 4: Sync wiring — translate added/changed records only

**Files:**
- Modify: `src/skill_rag/sync.py`
- Test: `tests/test_sync.py`

- [ ] **Step 1: Write the failing tests**

First, update the autouse `isolated` fixture in `tests/test_sync.py` so existing sync tests don't load real MT models — stub translation to a no-op by default. Change the fixture body (after the `importlib.reload(sync_mod)` line, before `yield`) to add:

```python
    from skill_rag import translate as translate_mod
    monkeypatch.setattr(translate_mod, "translate", lambda text: "")
```

Then append these tests to `tests/test_sync.py`:

```python
def test_sync_translates_only_new_and_changed(tmp_path, monkeypatch):
    from skill_rag import translate as translate_mod

    calls = []

    def fake(text):
        calls.append(text)
        return f"T[{text}]"

    monkeypatch.setattr(translate_mod, "translate", fake)
    corpus_root = tmp_path / "skills"
    _mk(corpus_root, "foo", desc="alpha")
    sync_mod.run_sync()
    assert calls == ["alpha"]  # new -> translated

    calls.clear()
    _mk(corpus_root, "foo", desc="beta")   # changed
    _mk(corpus_root, "bar", desc="gamma")  # new
    sync_mod.run_sync()
    assert sorted(calls) == ["beta", "gamma"]  # only changed + new

    calls.clear()
    sync_mod.run_sync()  # nothing changed
    assert calls == []  # unchanged -> not re-translated


def test_sync_translation_lands_in_indexed_text(tmp_path, monkeypatch):
    from skill_rag import translate as translate_mod

    monkeypatch.setattr(translate_mod, "translate", lambda text: "번역결과")
    corpus_root = tmp_path / "skills"
    _mk(corpus_root, "foo", desc="Deploy")
    sync_mod.run_sync()
    row = index_mod.list_indexed()[0]
    assert "번역결과" in row["text"]
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_sync.py -k "translat" -q`
Expected: FAIL — `test_sync_translates_only_new_and_changed` fails because `run_sync` does not call `translate` yet (`calls == []`).

- [ ] **Step 3: Write the implementation**

In `src/skill_rag/sync.py`, add the import near the other relative imports at the top:

```python
from . import translate as translate_mod
```

Then in `run_sync`, fill the translation for the upsert batch right before the upsert. Change:

```python
    if to_upsert:
        index_mod.upsert(to_upsert)
```

to:

```python
    if to_upsert:
        for record in to_upsert:
            record.description_translated = translate_mod.translate(record.description)
        index_mod.upsert(to_upsert)
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/test_sync.py -q`
Expected: PASS (existing + 2 new). Existing tests pass because the fixture stubs `translate` to `""`.

- [ ] **Step 5: Commit**

```bash
git add src/skill_rag/sync.py tests/test_sync.py
git commit -m "feat(sync): translate description for added/changed records only"
```

---

### Task 5: Docs + index note + full-suite verification

**Files:**
- Modify: `src/skill_rag/index.py` (schema docstring comment, top of file)
- Modify: `README.md` (Korean env-var table) and `README.en.md` (English env-var table)

- [ ] **Step 1: Note the content change in the index schema docstring**

In `src/skill_rag/index.py`, the module docstring lists schema versions ending with the `v5` line. Add one line after the `- v5:` line (this is a comment only — no column change, so the version stays 5):

```python
- v5: added `agent` column (source harness: claude-code, codex, local, ...)
  (the `text`/vector content also includes a ko↔en translation of the
   description via translate.py; changing embed_text requires `reset && sync`)
```

- [ ] **Step 2: Add the env var to the English README**

In `README.en.md`, in the "## Environment variables" table, add a row after the `SKILL_RAG_SCORE_THRESHOLD` row:

```markdown
| `SKILL_RAG_TRANSLATE` | `1` | Auto-translate each description ko↔en at index time (`0` disables) |
```

- [ ] **Step 3: Add the env var to the Korean README**

In `README.md`, in the "## 환경 변수" table, add a row after the `SKILL_RAG_SCORE_THRESHOLD` row:

```markdown
| `SKILL_RAG_TRANSLATE` | `1` | 인덱스 시 description 한↔영 자동 번역 (`0`이면 끔) |
```

- [ ] **Step 4: Run the full suite**

Run: `uv run pytest -q`
Expected: PASS (all tests; the translation tests are model-free via stubs).

- [ ] **Step 5: Commit**

```bash
git add src/skill_rag/index.py README.md README.en.md
git commit -m "docs: document SKILL_RAG_TRANSLATE; note index content change"
```

- [ ] **Step 6: Manual verification (real model, not a unit test)**

After `make install` (which downloads the opus-mt models on the first sync via `SKILL_RAG_LOCAL_FILES_ONLY=0`), confirm a cross-lingual hit that previously missed now resolves:

```bash
# An English-only skill (e.g. a vercel skill) retrieved by a Korean query:
uv run skill-rag query "버셀에 배포하기" -k 5
```
Expected: a deploy/vercel skill appears in the top-k. Compare against
`SKILL_RAG_TRANSLATE=0 uv run skill-rag reset && uv run skill-rag sync` to sanity-check the difference if desired. (`skill-rag eval` recall@5 must not regress on the English fixture cases.)

---

## Self-Review

**Spec coverage:**
- `translate.py` (detect_lang + translate, lazy load, graceful "", env config) → Task 2 ✅
- ko↔en only via opus-mt → Task 1 (deps) + Task 2 (model constants) ✅
- description only → Task 2 (translate takes the description string; sync passes `record.description`) ✅
- cache = added/changed only → Task 4 (loop over `to_upsert`) ✅
- `SkillRecord.description_translated` + embed_text fold-in, no schema change → Task 3 + Task 5 Step 1 ✅
- `SKILL_RAG_TRANSLATE` toggle → Task 2 (`TRANSLATE_ENABLED`) ✅
- deps sentencepiece + sacremoses + reference doc → Task 1 ✅
- graceful degrade on model-load failure → Task 2 (`test_translate_failure_returns_empty`) ✅
- verification (unit stubs + manual real-model eval) → Tasks 2/4 + Task 5 Step 6 ✅

**Placeholder scan:** No TBD/TODO; every code step shows complete code; the only "manual" step (Task 5 Step 6) is explicitly a real-model check outside pytest, with concrete commands.

**Type consistency:** `translate.translate(text: str) -> str`, `translate.detect_lang(text) -> str` ('ko'|'en'), `translate._run_model(text, name) -> str`, `TRANSLATE_ENABLED`/`MT_KO_EN`/`MT_EN_KO` module constants — all referenced consistently in Tasks 2 and 4. `SkillRecord.description_translated: str = ""` defined in Task 3, set in Task 4, read by `embed_text` in Task 3. Sync imports it as `translate as translate_mod` and calls `translate_mod.translate` — matching the test monkeypatch target. Consistent.
