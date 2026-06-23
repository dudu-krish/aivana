"""SQLite parent/child store + turbovec ANN index on child chunks only."""

from __future__ import annotations

import json
import logging
import math
import os
import sqlite3
import threading
from pathlib import Path
from typing import Any

from app.config import settings

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_conn: sqlite3.Connection | None = None
_tv_lock = threading.Lock()
_tv_cache: dict[str, tuple[Any, float, float]] = {}


def _db_path() -> Path:
    base = Path(settings.kb_db_path)
    path = base if base.is_absolute() else settings.data_dir / base
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return {row[1] for row in rows}


def _ensure_column(conn: sqlite3.Connection, table: str, column: str, col_type: str = "TEXT") -> None:
    if column not in _table_columns(conn, table):
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}")


def _ensure_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS kb_chunks (
            collection_id TEXT NOT NULL,
            chunk_id TEXT NOT NULL,
            document_id TEXT NOT NULL,
            document TEXT NOT NULL,
            embedding TEXT NOT NULL,
            metadata TEXT,
            content_hash TEXT,
            PRIMARY KEY (collection_id, chunk_id)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS kb_parents (
            collection_id TEXT NOT NULL,
            parent_id TEXT NOT NULL,
            document_id TEXT NOT NULL,
            parent_text TEXT NOT NULL,
            metadata TEXT,
            PRIMARY KEY (collection_id, parent_id)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS kb_documents (
            collection_id TEXT NOT NULL,
            document_id TEXT NOT NULL,
            source_type TEXT,
            source_uri TEXT,
            content_hash TEXT,
            indexed_at TEXT,
            PRIMARY KEY (collection_id, document_id)
        )
        """
    )
    _ensure_column(conn, "kb_chunks", "parent_id")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_kb_doc_collection ON kb_documents(collection_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_kb_parent_collection ON kb_parents(collection_id, parent_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_kb_chunk_parent ON kb_chunks(collection_id, parent_id)"
    )
    conn.commit()


def _connection() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        _conn = sqlite3.connect(str(_db_path()), check_same_thread=False)
    _ensure_schema(_conn)
    return _conn


def _safe_id(value: str) -> str:
    return "".join(c if c.isalnum() or c in "-_" else "_" for c in value)


def turbovec_index_paths(collection_id: str) -> tuple[Path, Path]:
    d = Path(settings.kb_turbovec_index_dir)
    path = d if d.is_absolute() else settings.data_dir / d
    base = path / _safe_id(collection_id)
    return base.with_suffix(".tv"), base.with_suffix(".meta.json")


def _try_import_turboquant() -> Any | None:
    try:
        from turbovec import TurboQuantIndex

        return TurboQuantIndex
    except ImportError:
        return None


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return -1.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return -1.0
    return dot / (na * nb)


def delete_document_index(collection_id: str, document_id: str) -> None:
    conn = _connection()
    with _lock:
        conn.execute(
            "DELETE FROM kb_chunks WHERE collection_id = ? AND document_id = ?",
            (collection_id, document_id),
        )
        conn.execute(
            "DELETE FROM kb_parents WHERE collection_id = ? AND document_id = ?",
            (collection_id, document_id),
        )
        conn.commit()


def upsert_parents(collection_id: str, parents: list[dict[str, Any]]) -> int:
    if not parents:
        return 0
    conn = _connection()
    with _lock:
        for row in parents:
            conn.execute(
                """
                INSERT INTO kb_parents (collection_id, parent_id, document_id, parent_text, metadata)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(collection_id, parent_id) DO UPDATE SET
                    parent_text = excluded.parent_text,
                    metadata = excluded.metadata
                """,
                (
                    collection_id,
                    row["parent_id"],
                    row["document_id"],
                    row["parent_text"],
                    json.dumps(row.get("metadata") or {}),
                ),
            )
        conn.commit()
    return len(parents)


def upsert_chunks(
    collection_id: str,
    chunks: list[dict[str, Any]],
    *,
    rebuild_index: bool = False,
) -> int:
    if not chunks:
        return 0
    conn = _connection()
    with _lock:
        for row in chunks:
            conn.execute(
                """
                INSERT INTO kb_chunks (collection_id, chunk_id, document_id, document, embedding, metadata, content_hash, parent_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(collection_id, chunk_id) DO UPDATE SET
                    document = excluded.document,
                    embedding = excluded.embedding,
                    metadata = excluded.metadata,
                    content_hash = excluded.content_hash,
                    parent_id = excluded.parent_id
                """,
                (
                    collection_id,
                    row["chunk_id"],
                    row["document_id"],
                    row["document"],
                    json.dumps(row["embedding"]),
                    json.dumps(row.get("metadata") or {}),
                    row.get("content_hash") or "",
                    row.get("parent_id"),
                ),
            )
        conn.commit()
    if rebuild_index:
        rebuild_turbovec_index(collection_id)
    return len(chunks)


def mark_document_indexed(
    collection_id: str,
    document_id: str,
    *,
    source_type: str,
    source_uri: str,
    content_hash: str,
    indexed_at: str,
) -> None:
    conn = _connection()
    with _lock:
        conn.execute(
            """
            INSERT INTO kb_documents (collection_id, document_id, source_type, source_uri, content_hash, indexed_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(collection_id, document_id) DO UPDATE SET
                source_type = excluded.source_type,
                source_uri = excluded.source_uri,
                content_hash = excluded.content_hash,
                indexed_at = excluded.indexed_at
            """,
            (collection_id, document_id, source_type, source_uri, content_hash, indexed_at),
        )
        conn.commit()


def document_hash(collection_id: str, document_id: str) -> str | None:
    row = _connection().execute(
        "SELECT content_hash FROM kb_documents WHERE collection_id = ? AND document_id = ?",
        (collection_id, document_id),
    ).fetchone()
    return row[0] if row else None


def collection_stats(collection_id: str) -> dict[str, int]:
    conn = _connection()
    docs = conn.execute(
        "SELECT COUNT(*) FROM kb_documents WHERE collection_id = ?",
        (collection_id,),
    ).fetchone()[0]
    parents = conn.execute(
        "SELECT COUNT(*) FROM kb_parents WHERE collection_id = ?",
        (collection_id,),
    ).fetchone()[0]
    children = conn.execute(
        "SELECT COUNT(*) FROM kb_chunks WHERE collection_id = ? AND parent_id IS NOT NULL",
        (collection_id,),
    ).fetchone()[0]
    legacy = conn.execute(
        "SELECT COUNT(*) FROM kb_chunks WHERE collection_id = ? AND parent_id IS NULL",
        (collection_id,),
    ).fetchone()[0]
    return {
        "documents": docs,
        "parents": parents,
        "children": children,
        "chunks": children + legacy,
    }


def fetch_parents(collection_id: str, parent_ids: list[str]) -> dict[str, dict[str, Any]]:
    if not parent_ids:
        return {}
    conn = _connection()
    placeholders = ",".join("?" for _ in parent_ids)
    rows = conn.execute(
        f"""
        SELECT parent_id, document_id, parent_text, metadata
        FROM kb_parents
        WHERE collection_id = ? AND parent_id IN ({placeholders})
        """,
        (collection_id, *parent_ids),
    ).fetchall()
    out: dict[str, dict[str, Any]] = {}
    for parent_id, document_id, parent_text, meta_json in rows:
        out[parent_id] = {
            "parent_id": parent_id,
            "document_id": document_id,
            "text": parent_text,
            "metadata": json.loads(meta_json or "{}"),
        }
    return out


def rebuild_turbovec_index(collection_id: str) -> None:
    TQI = _try_import_turboquant()
    if TQI is None:
        return
    import numpy as np

    conn = _connection()
    rows = conn.execute(
        """
        SELECT chunk_id, document, embedding FROM kb_chunks
        WHERE collection_id = ? ORDER BY chunk_id
        """,
        (collection_id,),
    ).fetchall()
    tv_path, meta_path = turbovec_index_paths(collection_id)
    tv_path.parent.mkdir(parents=True, exist_ok=True)

    if not rows:
        tv_path.unlink(missing_ok=True)
        meta_path.unlink(missing_ok=True)
        _invalidate_cache(collection_id)
        return

    vectors: list[list[float]] = []
    chunk_ids: list[str] = []
    for chunk_id, _doc, emb_json in rows:
        try:
            vec = json.loads(emb_json)
        except json.JSONDecodeError:
            continue
        if isinstance(vec, list) and vec:
            vectors.append(vec)
            chunk_ids.append(chunk_id)

    if not vectors:
        return

    arr = np.asarray(vectors, dtype=np.float32)
    bw = settings.kb_turbovec_bit_width if settings.kb_turbovec_bit_width in (2, 4) else 4
    idx = TQI(dim=int(arr.shape[1]), bit_width=bw)
    idx.add(arr)
    try:
        idx.prepare()
    except Exception:
        logger.debug("turbovec prepare skipped", exc_info=True)

    tmp = tv_path.with_suffix(".tv.tmp")
    idx.write(str(tmp))
    if tv_path.exists():
        tv_path.unlink()
    os.replace(str(tmp), str(tv_path))
    meta_path.write_text(
        json.dumps({"chunk_ids": chunk_ids, "dim": int(arr.shape[1]), "bit_width": bw}),
        encoding="utf-8",
    )
    _invalidate_cache(collection_id)
    logger.info("KB turbovec rebuilt collection=%s vectors=%s", collection_id, len(chunk_ids))


def _invalidate_cache(collection_id: str) -> None:
    with _tv_lock:
        _tv_cache.pop(collection_id, None)


def _load_index(collection_id: str) -> tuple[Any | None, dict[str, Any] | None]:
    TQI = _try_import_turboquant()
    if TQI is None:
        return None, None
    tv_path, meta_path = turbovec_index_paths(collection_id)
    if not tv_path.exists() or not meta_path.exists():
        return None, None
    m_tv = tv_path.stat().st_mtime
    m_meta = meta_path.stat().st_mtime
    with _tv_lock:
        hit = _tv_cache.get(collection_id)
        if hit and hit[1] == m_tv and hit[2] == m_meta:
            return hit[0], json.loads(meta_path.read_text(encoding="utf-8"))
    idx = TQI.load(str(tv_path))
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    with _tv_lock:
        _tv_cache[collection_id] = (idx, m_tv, m_meta)
    return idx, meta


def _fetch_chunks_by_ids(collection_id: str, chunk_ids: list[str]) -> dict[str, dict[str, Any]]:
    if not chunk_ids:
        return {}
    conn = _connection()
    placeholders = ",".join("?" for _ in chunk_ids)
    rows = conn.execute(
        f"""
        SELECT chunk_id, document_id, document, metadata, parent_id
        FROM kb_chunks WHERE collection_id = ? AND chunk_id IN ({placeholders})
        """,
        (collection_id, *chunk_ids),
    ).fetchall()
    return {
        row[0]: {
            "chunk_id": row[0],
            "document_id": row[1],
            "text": row[2],
            "metadata": json.loads(row[3] or "{}"),
            "parent_id": row[4],
        }
        for row in rows
    }


def search(collection_id: str, query_vec: list[float], *, top_k: int = 8) -> list[dict[str, Any]]:
    conn = _connection()
    idx, meta = _load_index(collection_id)
    if idx is not None and meta is not None:
        chunk_ids: list[str] = list(meta.get("chunk_ids") or [])
        if chunk_ids:
            n = len(idx)
            kk = min(top_k, n)
            q = __import__("numpy").asarray(query_vec, dtype=__import__("numpy").float32).reshape(1, -1)
            _scores, indices = idx.search(q, k=kk)
            hits: list[dict[str, Any]] = []
            for slot, score in zip(indices[0], _scores[0]):
                si = int(slot)
                if si < 0 or si >= len(chunk_ids):
                    continue
                cid = chunk_ids[si]
                row = conn.execute(
                    """
                    SELECT chunk_id, document_id, document, metadata, parent_id
                    FROM kb_chunks WHERE collection_id = ? AND chunk_id = ?
                    """,
                    (collection_id, cid),
                ).fetchone()
                if row:
                    hits.append(
                        {
                            "chunk_id": row[0],
                            "document_id": row[1],
                            "text": row[2],
                            "metadata": json.loads(row[3] or "{}"),
                            "parent_id": row[4],
                            "score": float(score),
                        }
                    )
            if hits:
                return hits

    rows = conn.execute(
        "SELECT chunk_id, document_id, document, embedding, metadata, parent_id FROM kb_chunks WHERE collection_id = ?",
        (collection_id,),
    ).fetchall()
    scored: list[tuple[float, dict[str, Any]]] = []
    for chunk_id, doc_id, document, emb_json, meta_json, parent_id in rows:
        try:
            vec = json.loads(emb_json)
        except json.JSONDecodeError:
            continue
        score = _cosine(query_vec, vec)
        scored.append(
            (
                score,
                {
                    "chunk_id": chunk_id,
                    "document_id": doc_id,
                    "text": document,
                    "metadata": json.loads(meta_json or "{}"),
                    "parent_id": parent_id,
                    "score": score,
                },
            )
        )
    scored.sort(key=lambda x: -x[0])
    return [item for _, item in scored[:top_k]]


def search_hierarchical(
    collection_id: str,
    query_vec: list[float],
    *,
    child_k: int | None = None,
    parent_k: int | None = None,
) -> list[dict[str, Any]]:
    """Search child chunks via ANN, return deduplicated parent sections for RAG context."""
    child_k = child_k or settings.kb_ask_child_candidates
    parent_k = parent_k or settings.kb_ask_parent_top_k

    child_hits = search(collection_id, query_vec, top_k=child_k)
    if not child_hits:
        return []

    parent_scores: dict[str, float] = {}
    parent_previews: dict[str, str] = {}
    legacy_hits: list[dict[str, Any]] = []

    for hit in child_hits:
        parent_id = hit.get("parent_id")
        score = float(hit.get("score") or 0.0)
        if not parent_id:
            legacy_hits.append(hit)
            continue
        if parent_id not in parent_scores or score > parent_scores[parent_id]:
            parent_scores[parent_id] = score
            parent_previews[parent_id] = (hit.get("text") or "")[:220]

    ranked_parents = sorted(parent_scores.items(), key=lambda item: -item[1])[:parent_k]
    parent_map = fetch_parents(collection_id, [pid for pid, _ in ranked_parents])

    results: list[dict[str, Any]] = []
    for parent_id, score in ranked_parents:
        parent = parent_map.get(parent_id)
        if not parent:
            continue
        results.append(
            {
                "parent_id": parent_id,
                "document_id": parent["document_id"],
                "text": parent["text"],
                "preview": parent_previews.get(parent_id, ""),
                "metadata": parent.get("metadata") or {},
                "score": score,
                "retrieval_level": "parent",
            }
        )

    if results:
        return results

    legacy_hits.sort(key=lambda h: -(h.get("score") or 0.0))
    return [
        {
            "parent_id": h.get("chunk_id"),
            "document_id": h.get("document_id"),
            "text": h.get("text") or "",
            "preview": (h.get("text") or "")[:220],
            "metadata": h.get("metadata") or {},
            "score": h.get("score"),
            "retrieval_level": "legacy",
        }
        for h in legacy_hits[:parent_k]
    ]
