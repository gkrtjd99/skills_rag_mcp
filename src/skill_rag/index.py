"""LanceDB-backed index for skill records.

Schema version: 11
- v1: pk=name
- v2: pk=path; added `source` column
- v3: pk=path; removed `source`, `allowed_tools` (single-corpus design)
- v4: added `text` column (name+description+body) for BM25 lexical search
- v5: added `agent` column (source harness: claude-code, codex, local, ...)
  (the `text`/vector content also includes a ko↔en translation of the
   description via translate.py; changing embed_text requires `reset && sync`)
- v6: added `translation_status` column so failed/disabled description
  translations can be retried without a content change.
- v7: marked the E5 query/passage prompt profile so vectors built by the old
  unprompted encoder are rebuilt instead of being mixed with prompted queries.
- v8: records the dense sequence cap and switches the default profile to 256
  tokens so an old 512-token cache is rebuilt automatically.
- v9: encodes a compact name/description/opening-body passage while retaining
  the full text column for BM25.
- v10: makes the compact dense passage description-only by default; an optional
  opening-body character count remains part of the schema profile.
- v11: sets the default description-only dense sequence cap to 64 tokens.
"""

from __future__ import annotations

import os
from pathlib import Path

import lancedb
import pyarrow as pa

from .corpus import DENSE_BODY_CHARS
from .embed import DEFAULT_MODEL, MAX_SEQ_LENGTH, encode, model_dim
from .models import SearchHit, SkillRecord

TABLE_NAME = "skills"
SCHEMA_VERSION = 11

# LanceDB table handles and metadata are stable for the lifetime of the MCP
# process. Keeping them hot avoids reopening the database and materializing an
# Arrow table for every query. All writes in this package invalidate the row
# snapshot; the index remains a disposable cache, so external mutation is not
# part of the runtime contract.
_table_cache: dict[str, object] = {}
_rows_cache: dict[str, list[dict]] = {}


def index_path() -> Path:
    return Path(os.environ.get("SKILL_RAG_INDEX_PATH", "./var/index.lance")).expanduser()


def _schema(dim: int) -> pa.Schema:
    return pa.schema(
        [
            pa.field("path", pa.string()),
            pa.field("name", pa.string()),
            pa.field("description", pa.string()),
            pa.field("content_hash", pa.string()),
            pa.field("text", pa.string()),
            pa.field("agent", pa.string()),
            pa.field("translation_status", pa.string()),
            pa.field("vector", pa.list_(pa.float32(), dim)),
        ],
        metadata={
            b"skill-rag-schema": str(SCHEMA_VERSION).encode("ascii"),
            b"embedding-profile": b"e5-query-passage-v4-description",
            b"dense-max-seq-length": str(MAX_SEQ_LENGTH).encode("ascii"),
            b"dense-body-chars": str(DENSE_BODY_CHARS).encode("ascii"),
        },
    )


def _open_db():
    path = index_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    return lancedb.connect(str(path))


def _cache_key() -> str:
    return str(index_path().resolve())


def _invalidate_cache(*, table: bool = False) -> None:
    key = _cache_key()
    _rows_cache.pop(key, None)
    if table:
        _table_cache.pop(key, None)


def _open_existing_table():
    """Open the existing table without loading the embedding model."""
    key = _cache_key()
    cached = _table_cache.get(key)
    if cached is not None:
        return cached
    db = _open_db()
    if TABLE_NAME not in db.list_tables().tables:
        return None
    table = db.open_table(TABLE_NAME)
    _table_cache[key] = table
    return table


def open_table(model_name: str = DEFAULT_MODEL):
    db = _open_db()
    schema = _schema(model_dim(model_name))
    tbl = _open_existing_table()
    if tbl is not None:
        # Drop and recreate on any schema drift (e.g. a pre-`text` v3 table).
        # The index is a derived cache — `sync` rebuilds it from the corpus.
        if not tbl.schema.equals(schema, check_metadata=True):
            db.drop_table(TABLE_NAME)
            _invalidate_cache(table=True)
            tbl = db.create_table(TABLE_NAME, schema=schema)
            _table_cache[_cache_key()] = tbl
            return tbl
        return tbl
    tbl = db.create_table(TABLE_NAME, schema=schema)
    _table_cache[_cache_key()] = tbl
    return tbl


def ensure_schema(model_name: str = DEFAULT_MODEL) -> None:
    """Migrate an existing cache without creating one for an empty corpus."""
    if _open_existing_table() is not None:
        open_table(model_name)


def list_indexed() -> list[dict]:
    key = _cache_key()
    cached = _rows_cache.get(key)
    if cached is not None:
        return [dict(row) for row in cached]
    tbl = _open_existing_table()
    if tbl is None or tbl.count_rows() == 0:
        _rows_cache[key] = []
        return []
    cols = [
        "path",
        "name",
        "description",
        "content_hash",
        "text",
        "agent",
        "translation_status",
    ]
    rows = tbl.to_arrow().select(cols).to_pylist()
    _rows_cache[key] = rows
    return [dict(row) for row in rows]


def indexed_count() -> int:
    """Return row count without creating a table or loading the embedding model."""
    db = _open_db()
    if TABLE_NAME not in db.list_tables().tables:
        return 0
    return db.open_table(TABLE_NAME).count_rows()


def upsert(records: list[SkillRecord], model_name: str = DEFAULT_MODEL) -> None:
    if not records:
        return
    tbl = open_table(model_name)
    texts = [r.embed_text() for r in records]
    dense_texts = [r.dense_text() for r in records]
    vectors = encode(dense_texts, name=model_name, mode="passage")
    rows = [
        {
            "path": r.path,
            "name": r.name,
            "description": r.description,
            "content_hash": r.content_hash,
            "text": text,
            "agent": r.agent,
            "translation_status": r.translation_status,
            "vector": vec.tolist(),
        }
        for r, text, vec in zip(records, texts, vectors)
    ]
    (
        tbl.merge_insert("path")
        .when_matched_update_all()
        .when_not_matched_insert_all()
        .execute(rows)
    )
    _invalidate_cache()


def delete_by_paths(paths: list[str]) -> int:
    if not paths:
        return 0
    tbl = _open_existing_table()
    if tbl is None:
        return 0
    quoted = ", ".join("'" + p.replace("'", "''") + "'" for p in paths)
    tbl.delete(f"path IN ({quoted})")
    _invalidate_cache()
    return len(paths)


def reset() -> None:
    db = _open_db()
    if TABLE_NAME in db.list_tables().tables:
        db.drop_table(TABLE_NAME)
    _invalidate_cache(table=True)


def search(
    query_vector, k: int = 5, model_name: str = DEFAULT_MODEL
) -> list[SearchHit]:
    tbl = open_table(model_name)
    if tbl.count_rows() == 0:
        return []
    # Guard the common operational footgun: the index was rebuilt with a
    # different embedding model (different dim) while a long-lived server still
    # holds the old model. Without this, lance raises an opaque internal error.
    col = tbl.schema.field("vector").type
    index_dim = getattr(col, "list_size", None)
    query_dim = len(query_vector)
    if index_dim is not None and query_dim != index_dim:
        raise ValueError(
            f"Query vector dimension ({query_dim}) does not match the index "
            f"({index_dim}). The index was built with a different embedding "
            f"model. Restart the MCP server (or run `skill-rag reset && sync`) "
            f"so the query model and the index agree."
        )
    rows = tbl.search(query_vector).metric("cosine").limit(k).to_list()
    hits: list[SearchHit] = []
    for row in rows:
        distance = float(row.get("_distance", 0.0))
        score = 1.0 - distance
        hits.append(
            SearchHit(
                name=row["name"],
                description=row["description"],
                score=score,
            )
        )
    return hits
