"""Local dataset store with optional embedding-backed retrieval."""
# ruff: noqa: BLE001,D102,D107,PLR6301,PLW0603,S310,S608,TRY004

from __future__ import annotations

import hashlib
import json
import math
import os
import sqlite3
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from code2workspace_cli.operator_store import (
    _cosine_similarity,
    _embed_documents,
    _embed_query,
    _embedding_enabled,
    _embedding_model_name,
)

SCHEMA_VERSION = "0.1"
DATASET_RECORD_NAME = "dataset.json"
DATASET_EMBEDDING_NAME = "embedding.json"
_LOCAL_EMBEDDING_MODEL = "local-hash-token-embedding-v1"
_LOCAL_EMBEDDING_DIMENSIONS = 256
_EMBEDDING_BASE_URL_ENV = "CODE2WORKSPACE_OPERATOR_STORE_EMBEDDING_BASE_URL"
_EMBEDDING_API_KEY_ENV = "CODE2WORKSPACE_OPERATOR_STORE_EMBEDDING_API_KEY"
_PROJECT_ENV_LOADED = False


@dataclass(frozen=True, slots=True)
class DatasetSearchFilter:
    """Structured filter for local dataset lookup."""

    query: str | None = None
    dataset_id: str | None = None
    domain: str | None = None
    media_type: str | None = None
    tag: str | None = None
    limit: int = 20


class DatasetStore:
    """Store dataset records as files and query dataset/input bundle metadata."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.datasets_dir = root / "datasets"
        self.db_path = root / "index.sqlite"
        self.root.mkdir(parents=True, exist_ok=True)
        self.datasets_dir.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def dataset_dir(self, *, dataset_id: str) -> Path:
        return self.datasets_dir / _safe_part(dataset_id)

    def dataset_path(self, *, dataset_id: str) -> Path:
        return self.dataset_dir(dataset_id=dataset_id) / DATASET_RECORD_NAME

    def embedding_path(self, *, dataset_id: str) -> Path:
        return self.dataset_dir(dataset_id=dataset_id) / DATASET_EMBEDDING_NAME

    def write_dataset(
        self,
        record: dict[str, object],
        *,
        dataset_dir: Path | None = None,
    ) -> Path:
        dataset_id = str(record.get("dataset_id", "")).strip() or _default_dataset_id(
            record
        )
        target_dir = dataset_dir or self.dataset_dir(dataset_id=dataset_id)
        target_dir.mkdir(parents=True, exist_ok=True)
        record_path = target_dir / DATASET_RECORD_NAME
        payload = {
            "schema_version": SCHEMA_VERSION,
            **record,
            "dataset_id": dataset_id,
            "record_path": str(record_path),
            "updated_at": str(record.get("updated_at") or _utc_now()),
        }
        if not str(payload.get("canonical_text", "")).strip():
            payload["canonical_text"] = _dataset_canonical_text(payload)
        record_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        self.upsert_dataset(record_path)
        return record_path

    def upsert_dataset(self, record_path: Path) -> None:
        payload = _read_json(record_path)
        normalized = _normalize_dataset(payload=payload, record_path=record_path)
        embedding_path = self.embedding_path(dataset_id=normalized["dataset_id"])
        embedding_payload = self._materialize_dataset_embedding(
            normalized=normalized,
            embedding_path=embedding_path,
        )
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO dataset_records
                (dataset_id, name, version, domain, source, license, summary,
                 canonical_text, record_path, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    normalized["dataset_id"],
                    normalized["name"],
                    normalized["version"],
                    normalized["domain"],
                    normalized["source"],
                    normalized["license"],
                    normalized["summary"],
                    normalized["canonical_text"],
                    str(record_path),
                    normalized["updated_at"],
                ),
            )
            conn.execute(
                "DELETE FROM dataset_files WHERE dataset_id = ?",
                (normalized["dataset_id"],),
            )
            for file_record in normalized["files"]:
                conn.execute(
                    """
                    INSERT INTO dataset_files
                    (dataset_id, name, role, media_type, uri, sha256, size_bytes)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        normalized["dataset_id"],
                        str(file_record.get("name", "")),
                        str(file_record.get("role", "")),
                        str(file_record.get("media_type", "")),
                        str(file_record.get("uri", "")),
                        str(file_record.get("sha256", "")),
                        _int_or_none(file_record.get("size_bytes")),
                    ),
                )
            conn.execute(
                "DELETE FROM dataset_tags WHERE dataset_id = ?",
                (normalized["dataset_id"],),
            )
            for tag in normalized["tags"]:
                conn.execute(
                    "INSERT INTO dataset_tags (dataset_id, tag) VALUES (?, ?)",
                    (normalized["dataset_id"], tag),
                )
            conn.execute(
                "DELETE FROM dataset_compatible_operators WHERE dataset_id = ?",
                (normalized["dataset_id"],),
            )
            for operator_id in normalized["compatible_operator_ids"]:
                conn.execute(
                    """
                    INSERT INTO dataset_compatible_operators (dataset_id, operator_id)
                    VALUES (?, ?)
                    """,
                    (normalized["dataset_id"], operator_id),
                )
            if embedding_payload is not None:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO dataset_record_embeddings
                    (dataset_id, model, vector_json, embedding_path, updated_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        normalized["dataset_id"],
                        str(embedding_payload.get("model", "")),
                        json.dumps(
                            embedding_payload.get("vector", []),
                            ensure_ascii=False,
                        ),
                        str(embedding_path),
                        str(embedding_payload.get("updated_at", "")),
                    ),
                )

    def rebuild(self) -> int:
        with self._connect() as conn:
            conn.execute("DELETE FROM dataset_records")
            conn.execute("DELETE FROM dataset_files")
            conn.execute("DELETE FROM dataset_tags")
            conn.execute("DELETE FROM dataset_compatible_operators")
            conn.execute("DELETE FROM dataset_record_embeddings")
        records = sorted(self.datasets_dir.glob(f"*/{DATASET_RECORD_NAME}"))
        for record_path in records:
            self.upsert_dataset(record_path)
        return len(records)

    def search_datasets(self, filters: DatasetSearchFilter) -> list[dict[str, object]]:
        rows = self._structured_rows(filters)
        query = (filters.query or "").strip()
        if not query:
            return rows[: max(1, filters.limit)]
        semantic_scores = self._semantic_scores(query=query, rows=rows)
        query_tokens = _tokenize(query)
        ranked: list[tuple[float, dict[str, object]]] = []
        for row in rows:
            dataset_id = str(row.get("dataset_id", "")).strip()
            searchable = str(row.get("canonical_text", "")).casefold()
            text_score = float(sum(token in searchable for token in query_tokens))
            semantic_score = float(semantic_scores.get(dataset_id, 0.0))
            if text_score <= 0 and semantic_score <= 0:
                continue
            ranked.append((((semantic_score * 100.0) + text_score), row))
        ranked.sort(key=lambda item: (-item[0], str(item[1].get("dataset_id", ""))))
        return [item[1] for item in ranked[: max(1, filters.limit)]]

    def _structured_rows(self, filters: DatasetSearchFilter) -> list[dict[str, object]]:
        where = ["1=1"]
        params: list[object] = []
        if filters.dataset_id:
            where.append("d.dataset_id = ?")
            params.append(filters.dataset_id)
        if filters.domain:
            where.append("d.domain = ?")
            params.append(filters.domain)
        if filters.media_type:
            where.append(
                "EXISTS ("
                "SELECT 1 FROM dataset_files f "
                "WHERE f.dataset_id = d.dataset_id AND f.media_type = ?"
                ")"
            )
            params.append(filters.media_type)
        if filters.tag:
            where.append(
                "EXISTS ("
                "SELECT 1 FROM dataset_tags t "
                "WHERE t.dataset_id = d.dataset_id AND t.tag = ?"
                ")"
            )
            params.append(filters.tag)
        params.append(max(50, filters.limit * 8))
        with self._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT d.dataset_id, d.name, d.version, d.domain, d.source, d.license,
                       d.summary, d.canonical_text, d.record_path, d.updated_at
                FROM dataset_records d
                WHERE {" AND ".join(where)}
                ORDER BY d.updated_at DESC, d.dataset_id ASC
                LIMIT ?
                """,
                params,
            ).fetchall()
        return [_row_to_result(row) for row in rows]

    def _semantic_scores(
        self,
        *,
        query: str,
        rows: list[dict[str, object]],
    ) -> dict[str, float]:
        try:
            query_vector, model_name = _dataset_embed_query(query)
        except Exception:
            return {}
        if not query_vector or not model_name:
            return {}
        row_ids = [
            str(row.get("dataset_id", "")).strip()
            for row in rows
            if str(row.get("dataset_id", "")).strip()
        ]
        if not row_ids:
            return {}
        placeholders = ", ".join("?" for _ in row_ids)
        with self._connect() as conn:
            stored = conn.execute(
                f"""
                SELECT dataset_id, model, vector_json
                FROM dataset_record_embeddings
                WHERE dataset_id IN ({placeholders})
                """,
                row_ids,
            ).fetchall()
        scores: dict[str, float] = {}
        for dataset_id, stored_model, vector_json in stored:
            if str(stored_model) != model_name:
                continue
            try:
                vector = json.loads(str(vector_json))
            except json.JSONDecodeError:
                continue
            if not isinstance(vector, list) or not vector:
                continue
            similarity = _cosine_similarity(
                query_vector,
                [float(item) for item in vector],
            )
            if similarity > 0:
                scores[str(dataset_id)] = similarity
        return scores

    def _materialize_dataset_embedding(
        self,
        *,
        normalized: dict[str, Any],
        embedding_path: Path,
    ) -> dict[str, object] | None:
        source_text = str(normalized.get("canonical_text", "")).strip()
        if not source_text:
            return None
        source_text_sha256 = hashlib.sha256(source_text.encode("utf-8")).hexdigest()
        if embedding_path.exists():
            existing = _read_json(embedding_path)
            if (
                str(existing.get("source_text_sha256", "")) == source_text_sha256
                and isinstance(existing.get("vector"), list)
                and existing.get("vector")
                and str(existing.get("model", "")) != _LOCAL_EMBEDDING_MODEL
            ):
                return existing
        try:
            vectors, model_name = _dataset_embed_documents([source_text])
        except Exception:
            return None
        if not vectors or not model_name:
            return None
        payload = {
            "schema_version": SCHEMA_VERSION,
            "dataset_id": normalized["dataset_id"],
            "model": model_name,
            "source_text_sha256": source_text_sha256,
            "source_text": source_text,
            "vector": vectors[0],
            "updated_at": _utc_now(),
        }
        embedding_path.parent.mkdir(parents=True, exist_ok=True)
        embedding_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        return payload

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path)

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS dataset_records (
                    dataset_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    version TEXT NOT NULL,
                    domain TEXT NOT NULL,
                    source TEXT NOT NULL,
                    license TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    canonical_text TEXT NOT NULL,
                    record_path TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS dataset_files (
                    dataset_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    role TEXT NOT NULL,
                    media_type TEXT NOT NULL,
                    uri TEXT NOT NULL,
                    sha256 TEXT NOT NULL,
                    size_bytes INTEGER,
                    FOREIGN KEY(dataset_id) REFERENCES dataset_records(dataset_id)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS dataset_tags (
                    dataset_id TEXT NOT NULL,
                    tag TEXT NOT NULL,
                    FOREIGN KEY(dataset_id) REFERENCES dataset_records(dataset_id)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS dataset_compatible_operators (
                    dataset_id TEXT NOT NULL,
                    operator_id TEXT NOT NULL,
                    FOREIGN KEY(dataset_id) REFERENCES dataset_records(dataset_id)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS dataset_record_embeddings (
                    dataset_id TEXT PRIMARY KEY,
                    model TEXT NOT NULL,
                    vector_json TEXT NOT NULL,
                    embedding_path TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_dataset_domain "
                "ON dataset_records(domain)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_dataset_files_media "
                "ON dataset_files(media_type)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_dataset_tags_tag ON dataset_tags(tag)"
            )


def _default_dataset_id(record: dict[str, object]) -> str:
    name = str(record.get("name", "dataset")).strip() or "dataset"
    version = str(record.get("version", "unversioned")).strip() or "unversioned"
    return f"dataset:{name}:{version}"


def _normalize_dataset(
    *,
    payload: dict[str, object],
    record_path: Path,
) -> dict[str, Any]:
    dataset_id = str(payload.get("dataset_id", "")).strip() or record_path.parent.name
    return {
        "dataset_id": dataset_id,
        "name": str(payload.get("name", dataset_id)).strip() or dataset_id,
        "version": str(payload.get("version", "")).strip(),
        "domain": str(payload.get("domain", "")).strip(),
        "source": str(payload.get("source", "")).strip(),
        "license": str(payload.get("license", "")).strip(),
        "summary": str(payload.get("summary", "")).strip(),
        "files": _list_of_dicts(payload.get("files")),
        "tags": _list_of_strings(payload.get("tags")),
        "compatible_operator_ids": _list_of_strings(
            payload.get("compatible_operator_ids")
        ),
        "canonical_text": str(payload.get("canonical_text", "")).strip()
        or _dataset_canonical_text(payload),
        "updated_at": str(payload.get("updated_at", "")).strip() or _utc_now(),
    }


def _dataset_canonical_text(payload: dict[str, object]) -> str:
    files = _list_of_dicts(payload.get("files"))
    file_text = " ".join(
        " ".join(
            str(item.get(key, "")).strip()
            for key in ("name", "role", "media_type", "uri", "description")
        )
        for item in files
    )
    return "\n".join(
        item
        for item in (
            f"dataset_id: {payload.get('dataset_id', '')}",
            f"name: {payload.get('name', '')}",
            f"version: {payload.get('version', '')}",
            f"domain: {payload.get('domain', '')}",
            f"summary: {payload.get('summary', '')}",
            f"description: {payload.get('description', '')}",
            f"source: {payload.get('source', '')}",
            f"tags: {' '.join(_list_of_strings(payload.get('tags')))}",
            (
                "compatible_operators: "
                f"{' '.join(_list_of_strings(payload.get('compatible_operator_ids')))}"
            ),
            f"files: {file_text}",
        )
        if item.strip()
    )


def _row_to_result(row: tuple[object, ...]) -> dict[str, object]:
    return {
        "dataset_id": str(row[0]),
        "name": str(row[1]),
        "version": str(row[2]),
        "domain": str(row[3]),
        "source": str(row[4]),
        "license": str(row[5]),
        "summary": str(row[6]),
        "canonical_text": str(row[7]),
        "record_path": str(row[8]),
        "updated_at": str(row[9]),
    }


def _read_json(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        msg = f"Expected JSON object at {path}"
        raise ValueError(msg)
    return payload


def _safe_part(value: str) -> str:
    safe = "".join(ch if ch.isalnum() or ch in "._-" else "-" for ch in value.strip())
    safe = safe.strip(".-")
    return safe or "item"


def _utc_now() -> str:
    from datetime import UTC, datetime

    return datetime.now(UTC).isoformat()


def _int_or_none(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str) and value.strip():
        try:
            return int(value.strip())
        except ValueError:
            return None
    return None


def _list_of_dicts(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _list_of_strings(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [
        str(item).strip()
        for item in value
        if isinstance(item, str) and item.strip()
    ]


def _tokenize(text: str) -> list[str]:
    import re

    return [
        token
        for token in re.split(r"[^0-9A-Za-z\u4e00-\u9fff]+", text.casefold())
        if token and len(token) > 1
    ]


def _dataset_embed_documents(texts: list[str]) -> tuple[list[list[float]], str | None]:
    try:
        vectors, model_name = _native_embed_documents(texts)
    except Exception:
        vectors, model_name = [], None
    if vectors and model_name:
        return vectors, model_name
    try:
        vectors, model_name = _embed_documents(texts)
    except Exception:
        vectors, model_name = [], None
    if vectors and model_name:
        return vectors, model_name
    return [_local_text_embedding(text) for text in texts], _LOCAL_EMBEDDING_MODEL


def _dataset_embed_query(text: str) -> tuple[list[float], str | None]:
    try:
        vectors, model_name = _native_embed_documents([text])
    except Exception:
        vectors, model_name = [], None
    if vectors and model_name:
        return vectors[0], model_name
    try:
        vector, model_name = _embed_query(text)
    except Exception:
        vector, model_name = [], None
    if vector and model_name:
        return vector, model_name
    if not text.strip():
        return [], None
    return _local_text_embedding(text), _LOCAL_EMBEDDING_MODEL


def _native_embed_documents(texts: list[str]) -> tuple[list[list[float]], str | None]:
    clean_texts = [text for text in texts if text.strip()]
    if len(clean_texts) != len(texts) or not clean_texts or not _embedding_enabled():
        return [], None
    base_url = _embedding_base_url()
    api_key = _embedding_api_key()
    if not base_url or not api_key:
        return [], None
    model_name = _embedding_model_name()
    endpoint = base_url.rstrip("/") + "/embeddings"
    if not endpoint.startswith(("https://", "http://")):
        return [], None
    request = urllib.request.Request(
        endpoint,
        data=json.dumps(
            {
                "model": model_name,
                "input": texts,
            }
        ).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        payload = json.loads(response.read().decode("utf-8"))
    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(data, list):
        return [], None
    vectors_by_index: dict[int, list[float]] = {}
    for fallback_index, item in enumerate(data):
        if not isinstance(item, dict):
            continue
        raw_embedding = item.get("embedding")
        if not isinstance(raw_embedding, list):
            continue
        index = _int_or_none(item.get("index"))
        if index is None:
            index = fallback_index
        vectors_by_index[index] = [float(value) for value in raw_embedding]
    vectors = [
        vectors_by_index[index]
        for index in range(len(texts))
        if index in vectors_by_index
    ]
    if len(vectors) != len(texts):
        return [], None
    return vectors, model_name


def _embedding_base_url() -> str | None:
    _ensure_project_env_loaded()
    raw = os.environ.get(_EMBEDDING_BASE_URL_ENV) or _resolve_env_var("OPENAI_BASE_URL")
    return raw.strip() if isinstance(raw, str) and raw.strip() else None


def _embedding_api_key() -> str | None:
    _ensure_project_env_loaded()
    raw = os.environ.get(_EMBEDDING_API_KEY_ENV) or _resolve_env_var("OPENAI_API_KEY")
    return raw.strip() if isinstance(raw, str) and raw.strip() else None


def _ensure_project_env_loaded() -> None:
    global _PROJECT_ENV_LOADED
    if _PROJECT_ENV_LOADED:
        return
    _PROJECT_ENV_LOADED = True
    try:
        import dotenv
    except ImportError:
        return
    for parent in (Path.cwd(), *Path.cwd().parents):
        dotenv_path = parent / ".env"
        if dotenv_path.exists():
            dotenv.load_dotenv(dotenv_path=dotenv_path, override=False)
            return


def _resolve_env_var(name: str) -> str | None:
    try:
        from code2workspace_cli.model_config import resolve_env_var
    except ImportError:
        return os.environ.get(name) or None
    return resolve_env_var(name)


def _local_text_embedding(text: str) -> list[float]:
    vector = [0.0] * _LOCAL_EMBEDDING_DIMENSIONS
    tokens = _tokenize(text)
    if not tokens:
        return vector
    for token in tokens:
        digest = hashlib.blake2b(token.encode("utf-8"), digest_size=4).digest()
        bucket = int.from_bytes(digest[:2], "big") % _LOCAL_EMBEDDING_DIMENSIONS
        sign = 1.0 if digest[2] % 2 == 0 else -1.0
        vector[bucket] += sign
    norm = math.sqrt(sum(value * value for value in vector))
    if norm == 0:
        return vector
    return [value / norm for value in vector]
