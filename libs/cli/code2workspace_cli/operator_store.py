"""Manifest-first operator store with stable operator records and validation history."""
# ruff: noqa: DOC201, DOC501

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path

MANIFEST_NAME = "operator_product.json"
OPERATOR_RECORD_NAME = "operator.json"
OPERATOR_EMBEDDING_NAME = "embedding.json"
SCHEMA_VERSION = "0.2"
_EMBEDDING_MODEL_ENV = "CODE2WORKSPACE_OPERATOR_STORE_EMBEDDING_MODEL"
_EMBEDDING_ENABLED_ENV = "CODE2WORKSPACE_OPERATOR_STORE_EMBEDDINGS_ENABLED"
_EMBEDDING_BASE_URL_ENV = "CODE2WORKSPACE_OPERATOR_STORE_EMBEDDING_BASE_URL"
_EMBEDDING_API_KEY_ENV = "CODE2WORKSPACE_OPERATOR_STORE_EMBEDDING_API_KEY"
_DEFAULT_EMBEDDING_MODEL = "text-embedding-3-small"


@dataclass(frozen=True, slots=True)
class OperatorSearchFilter:
    """Structured filter for local operator lookup."""

    query: str | None = None
    family: str | None = None
    input_media_type: str | None = None
    output_media_type: str | None = None
    metric_name: str | None = None
    status: str | None = None
    tag: str | None = None
    tags: tuple[str, ...] = ()
    limit: int = 50


class OperatorStore:
    """Store operator manifests as files and query stable operator metadata."""

    def __init__(self, root: Path) -> None:
        """Create or open an operator store rooted at ``root``."""
        self.root = root
        self.objects_dir = root / "objects"
        self.operators_dir = root / "operators"
        self.db_path = root / "index.sqlite"
        self.root.mkdir(parents=True, exist_ok=True)
        self.objects_dir.mkdir(parents=True, exist_ok=True)
        self.operators_dir.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def product_dir(self, *, family: str, name: str, version: str) -> Path:
        """Return the canonical object directory for one run-level product manifest."""
        return (
            self.objects_dir
            / _safe_path_part(family)
            / _safe_path_part(name)
            / _safe_path_part(version)
        )

    def operator_dir(self, *, operator_id: str) -> Path:
        """Return the canonical directory for one stable operator record."""
        return self.operators_dir / _safe_path_part(operator_id)

    def operator_record_path(self, *, operator_id: str) -> Path:
        """Return the canonical operator record path."""
        return self.operator_dir(operator_id=operator_id) / OPERATOR_RECORD_NAME

    def operator_version_path(self, *, operator_id: str, version: str) -> Path:
        """Return the canonical version record path for one operator version."""
        return self.operator_dir(operator_id=operator_id) / "versions" / f"{_safe_path_part(version)}.json"

    def operator_validation_path(self, *, operator_id: str, run_id: str) -> Path:
        """Return the canonical validation record path for one operator run."""
        return self.operator_dir(operator_id=operator_id) / "validations" / f"{_safe_path_part(run_id)}.json"

    def operator_embedding_path(self, *, operator_id: str) -> Path:
        """Return the canonical embedding record path for one operator."""
        return self.operator_dir(operator_id=operator_id) / OPERATOR_EMBEDDING_NAME

    def write_manifest(
        self,
        manifest: dict[str, object],
        *,
        product_dir: Path | None = None,
    ) -> Path:
        """Write one run-level manifest, then materialize stable operator records."""
        target_dir = product_dir or self.product_dir(
            family=str(manifest.get("family", "unknown")),
            name=str(manifest.get("name", manifest.get("product_id", "operator"))),
            version=str(manifest.get("version", "unversioned")),
        )
        target_dir.mkdir(parents=True, exist_ok=True)
        manifest_path = target_dir / MANIFEST_NAME
        payload = {
            "schema_version": SCHEMA_VERSION,
            **manifest,
            "operator_id": str(manifest.get("operator_id") or _stable_operator_id(manifest)),
            "manifest_path": str(manifest_path),
            "updated_at": _utc_now(),
        }
        manifest_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        self.upsert_manifest(manifest_path)
        return manifest_path

    def upsert_manifest(self, manifest_path: Path) -> None:
        """Load one run-level manifest into the stable operator index."""
        payload = _read_json(manifest_path)
        normalized = _normalize_manifest(payload=payload, manifest_path=manifest_path)

        operator_path = self.operator_record_path(operator_id=normalized["operator_id"])
        version_path = self.operator_version_path(
            operator_id=normalized["operator_id"],
            version=normalized["version"],
        )
        validation_path = self.operator_validation_path(
            operator_id=normalized["operator_id"],
            run_id=normalized["run_id"],
        )
        embedding_path = self.operator_embedding_path(operator_id=normalized["operator_id"])
        operator_path.parent.mkdir(parents=True, exist_ok=True)
        version_path.parent.mkdir(parents=True, exist_ok=True)
        validation_path.parent.mkdir(parents=True, exist_ok=True)

        existing_operator = _read_json(operator_path) if operator_path.exists() else None
        operator_payload = _build_operator_record_payload(
            payload=payload,
            normalized=normalized,
            existing_operator=existing_operator,
            operator_path=operator_path,
            version_path=version_path,
            validation_path=validation_path,
            embedding_path=embedding_path,
            manifest_path=manifest_path,
        )
        version_payload = _build_operator_version_payload(
            payload=payload,
            normalized=normalized,
            operator_path=operator_path,
            version_path=version_path,
            manifest_path=manifest_path,
        )
        validation_payload = _build_validation_record_payload(
            payload=payload,
            normalized=normalized,
            validation_path=validation_path,
            manifest_path=manifest_path,
        )

        _write_json_file(operator_path, operator_payload)
        _write_json_file(version_path, version_payload)
        _write_json_file(validation_path, validation_payload)
        embedding_payload = self._materialize_operator_embedding(
            operator_payload=operator_payload,
            embedding_path=embedding_path,
        )
        if embedding_payload is not None:
            operator_payload["latest_embedding_path"] = str(embedding_path)
            operator_payload["embedding_model"] = str(embedding_payload.get("model", ""))
            operator_payload["embedding_dimensions"] = int(embedding_payload.get("dimensions", 0))
            _write_json_file(operator_path, operator_payload)
        self._upsert_operator_bundle(
            operator_payload=operator_payload,
            validation_payload=validation_payload,
            embedding_payload=embedding_payload,
        )

    def rebuild(self) -> int:
        """Rebuild the SQLite index from stable operator files or legacy manifests."""
        self._clear_index()
        operator_paths = sorted(self.operators_dir.glob(f"*/{OPERATOR_RECORD_NAME}"))
        if operator_paths:
            for operator_path in operator_paths:
                operator_payload = _read_json(operator_path)
                embedding_path = operator_path.parent / OPERATOR_EMBEDDING_NAME
                embedding_payload = _read_json(embedding_path) if embedding_path.exists() else None
                validation_paths = sorted(operator_path.parent.glob("validations/*.json"))
                if not validation_paths:
                    self._upsert_operator_bundle(
                        operator_payload=operator_payload,
                        validation_payload=None,
                        embedding_payload=embedding_payload,
                    )
                    continue
                for validation_path in validation_paths:
                    self._upsert_operator_bundle(
                        operator_payload=operator_payload,
                        validation_payload=_read_json(validation_path),
                        embedding_payload=embedding_payload,
                    )
            return len(operator_paths)

        manifests = sorted(self.objects_dir.glob(f"**/{MANIFEST_NAME}"))
        for manifest_path in manifests:
            self.upsert_manifest(manifest_path)
        return len(manifests)

    def search(self, filters: OperatorSearchFilter) -> list[dict[str, object]]:
        """Search indexed operators using filters and optional full-text query."""
        query = (filters.query or "").strip()
        with self._connect() as conn:
            if not query:
                return self._search_structured_only(conn, filters)
            text_rows = (
                self._search_with_fts(conn, filters, query)
                if self._fts_available(conn)
                else self._search_with_python_text(conn, filters, query)
            )
            semantic_rows = self._search_with_semantic(conn, filters, query)
        if semantic_rows:
            return _merge_ranked_results(
                semantic_rows=semantic_rows,
                text_rows=text_rows,
                limit=max(1, filters.limit),
            )
        return text_rows

    def search_operators(self, filters: OperatorSearchFilter) -> list[dict[str, object]]:
        """Alias for the stable operator-level search interface."""
        return self.search(filters)

    def _search_structured_only(
        self,
        conn: sqlite3.Connection,
        filters: OperatorSearchFilter,
    ) -> list[dict[str, object]]:
        where, params = _search_conditions(filters)
        params.append(max(1, filters.limit))
        rows = conn.execute(
            f"""
            SELECT
                o.operator_id,
                o.name,
                o.family,
                o.version,
                o.validation_status,
                o.latest_product_manifest_path,
                o.operator_path,
                o.latest_validation_path
            FROM operator_records o
            WHERE {" AND ".join(where)}
            ORDER BY o.updated_at DESC, o.operator_id ASC
            LIMIT ?
            """,  # noqa: S608 - where clause is assembled from fixed SQL snippets.
            params,
        ).fetchall()
        return [_row_to_result(row) for row in rows]

    def _search_with_fts(
        self,
        conn: sqlite3.Connection,
        filters: OperatorSearchFilter,
        query: str,
    ) -> list[dict[str, object]]:
        tokens = _tokenize(query)
        if not tokens:
            return self._search_structured_only(conn, filters)
        match_query = " ".join(tokens)
        where, params = _search_conditions(filters)
        params = [match_query, *params, max(1, filters.limit)]
        rows = conn.execute(
            f"""
            WITH matched AS (
                SELECT operator_id, bm25(operator_record_fts) AS text_rank
                FROM operator_record_fts
                WHERE operator_record_fts MATCH ?
            )
            SELECT
                o.operator_id,
                o.name,
                o.family,
                o.version,
                o.validation_status,
                o.latest_product_manifest_path,
                o.operator_path,
                o.latest_validation_path
            FROM operator_records o
            JOIN matched m ON m.operator_id = o.operator_id
            WHERE {" AND ".join(where)}
            ORDER BY m.text_rank ASC, o.updated_at DESC, o.operator_id ASC
            LIMIT ?
            """,  # noqa: S608 - where clause is assembled from fixed SQL snippets.
            params,
        ).fetchall()
        return [_row_to_result(row) for row in rows]

    def _search_with_python_text(
        self,
        conn: sqlite3.Connection,
        filters: OperatorSearchFilter,
        query: str,
    ) -> list[dict[str, object]]:
        where, params = _search_conditions(filters)
        rows = conn.execute(
            f"""
            SELECT
                o.operator_id,
                o.name,
                o.family,
                o.version,
                o.validation_status,
                o.latest_product_manifest_path,
                o.operator_path,
                o.latest_validation_path,
                o.canonical_text,
                o.updated_at
            FROM operator_records o
            WHERE {" AND ".join(where)}
            """,  # noqa: S608 - where clause is assembled from fixed SQL snippets.
            params,
        ).fetchall()
        query_tokens = _tokenize(query)
        scored: list[tuple[int, tuple[object, ...]]] = []
        for row in rows:
            searchable = str(row[8]).casefold()
            score = sum(token in searchable for token in query_tokens)
            if score == 0:
                continue
            scored.append((score, row))
        scored.sort(key=lambda item: (-item[0], str(item[1][9]), str(item[1][0])))
        limited = [row for _, row in scored[: max(1, filters.limit)]]
        return [_row_to_result(row) for row in limited]

    def _search_with_semantic(
        self,
        conn: sqlite3.Connection,
        filters: OperatorSearchFilter,
        query: str,
    ) -> list[dict[str, object]]:
        try:
            query_vector, model_name = _embed_query(query)
        except Exception:
            return []
        if not query_vector or not model_name:
            return []
        stored_model = self._meta_get(conn, "embedding_model")
        if stored_model and stored_model != model_name:
            return []
        if self._vec_table_available(conn):
            return self._search_with_vec(conn, filters, query_vector)
        return self._search_with_python_embeddings(conn, filters, query_vector)

    def _search_with_vec(
        self,
        conn: sqlite3.Connection,
        filters: OperatorSearchFilter,
        query_vector: list[float],
    ) -> list[dict[str, object]]:
        candidate_limit = max(20, filters.limit * 8)
        candidate_rows = conn.execute(
            """
            SELECT operator_id, distance
            FROM operator_record_vec
            WHERE embedding MATCH ? AND k = ?
            """,
            (json.dumps(query_vector), candidate_limit),
        ).fetchall()
        if not candidate_rows:
            return []
        structured_rows = self._search_structured_candidates(
            conn,
            filters,
            [str(row[0]) for row in candidate_rows],
        )
        ordered: list[dict[str, object]] = []
        for operator_id, _distance in candidate_rows:
            payload = structured_rows.get(str(operator_id))
            if payload is not None:
                ordered.append(payload)
                if len(ordered) >= max(1, filters.limit):
                    break
        return ordered

    def _search_with_python_embeddings(
        self,
        conn: sqlite3.Connection,
        filters: OperatorSearchFilter,
        query_vector: list[float],
    ) -> list[dict[str, object]]:
        rows = conn.execute(
            """
            SELECT
                e.operator_id,
                e.vector_json,
                o.name,
                o.family,
                o.version,
                o.validation_status,
                o.latest_product_manifest_path,
                o.operator_path,
                o.latest_validation_path,
                o.updated_at
            FROM operator_record_embeddings e
            JOIN operator_records o ON o.operator_id = e.operator_id
            """
        ).fetchall()
        structured_rows = self._search_structured_candidates(
            conn,
            filters,
            [str(row[0]) for row in rows],
        )
        scored: list[tuple[float, tuple[object, ...]]] = []
        for row in rows:
            operator_id = str(row[0])
            if operator_id not in structured_rows:
                continue
            try:
                vector = json.loads(str(row[1]))
            except json.JSONDecodeError:
                continue
            if not isinstance(vector, list):
                continue
            similarity = _cosine_similarity(query_vector, [float(item) for item in vector])
            if similarity <= 0:
                continue
            scored.append((similarity, row))
        scored.sort(key=lambda item: (-item[0], str(item[1][9]), str(item[1][0])))
        results: list[dict[str, object]] = []
        for _score, row in scored[: max(1, filters.limit)]:
            payload = structured_rows.get(str(row[0]))
            if payload is not None:
                results.append(payload)
        return results

    def _search_structured_candidates(
        self,
        conn: sqlite3.Connection,
        filters: OperatorSearchFilter,
        operator_ids: list[str],
    ) -> dict[str, dict[str, object]]:
        if not operator_ids:
            return {}
        where, params = _search_conditions(filters)
        placeholders = ", ".join("?" for _ in operator_ids)
        params.extend(operator_ids)
        rows = conn.execute(
            f"""
            SELECT
                o.operator_id,
                o.name,
                o.family,
                o.version,
                o.validation_status,
                o.latest_product_manifest_path,
                o.operator_path,
                o.latest_validation_path
            FROM operator_records o
            WHERE {" AND ".join(where)}
              AND o.operator_id IN ({placeholders})
            """,  # noqa: S608 - where clause is assembled from fixed SQL snippets.
            params,
        ).fetchall()
        return {str(row[0]): _row_to_result(row) for row in rows}

    def _upsert_operator_bundle(
        self,
        *,
        operator_payload: dict[str, object],
        validation_payload: dict[str, object] | None,
        embedding_payload: dict[str, object] | None,
    ) -> None:
        operator_id = str(operator_payload.get("operator_id", "")).strip()
        if not operator_id:
            msg = "Operator record is missing operator_id."
            raise ValueError(msg)
        with self._connect() as conn:
            conn.execute("BEGIN")
            existing_created_at = conn.execute(
                "SELECT created_at FROM operator_records WHERE operator_id = ?",
                (operator_id,),
            ).fetchone()
            created_at = (
                str(existing_created_at[0])
                if existing_created_at and existing_created_at[0]
                else str(operator_payload.get("created_at", operator_payload.get("updated_at", "")))
            )
            conn.execute(
                "DELETE FROM operator_record_io WHERE operator_id = ?",
                (operator_id,),
            )
            conn.execute(
                "DELETE FROM operator_record_runtime WHERE operator_id = ?",
                (operator_id,),
            )
            conn.execute(
                "DELETE FROM operator_record_metrics WHERE operator_id = ?",
                (operator_id,),
            )
            conn.execute(
                "DELETE FROM operator_record_tags WHERE operator_id = ?",
                (operator_id,),
            )
            conn.execute(
                "DELETE FROM operator_record_embeddings WHERE operator_id = ?",
                (operator_id,),
            )
            if self._vec_table_available(conn):
                conn.execute(
                    "DELETE FROM operator_record_vec WHERE operator_id = ?",
                    (operator_id,),
                )
            conn.execute(
                """
                INSERT OR REPLACE INTO operator_records
                (operator_id, family, name, version, summary, description,
                 source_repo, source_commit, operator_path, latest_version_path,
                 latest_validation_path, latest_product_manifest_path,
                 validation_status, created_at, updated_at, canonical_text)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    operator_id,
                    str(operator_payload.get("family", "")),
                    str(operator_payload.get("name", "")),
                    str(operator_payload.get("version", "")),
                    str(operator_payload.get("summary", "")),
                    str(operator_payload.get("description", "")),
                    str(operator_payload.get("source_repo", "")),
                    str(operator_payload.get("source_commit", "")),
                    str(operator_payload.get("operator_path", "")),
                    str(operator_payload.get("latest_version_path", "")),
                    str(operator_payload.get("latest_validation_path", "")),
                    str(operator_payload.get("latest_product_manifest_path", "")),
                    str(operator_payload.get("validation_status", "")),
                    created_at,
                    str(operator_payload.get("updated_at", "")),
                    str(operator_payload.get("canonical_text", "")),
                ),
            )
            for item in _list_of_dicts(operator_payload.get("inputs")):
                conn.execute(
                    """
                    INSERT INTO operator_record_io
                    (operator_id, direction, media_type, schema_path, required, name, path)
                    VALUES (?, 'input', ?, ?, ?, ?, ?)
                    """,
                    (
                        operator_id,
                        str(item.get("media_type", "")),
                        str(item.get("schema_path", "")),
                        1 if item.get("required", True) else 0,
                        str(item.get("name", "")),
                        str(item.get("path", "")),
                    ),
                )
            for item in _list_of_dicts(operator_payload.get("outputs")):
                conn.execute(
                    """
                    INSERT INTO operator_record_io
                    (operator_id, direction, media_type, schema_path, required, name, path)
                    VALUES (?, 'output', ?, ?, ?, ?, ?)
                    """,
                    (
                        operator_id,
                        str(item.get("media_type", "")),
                        str(item.get("schema_path", "")),
                        1 if item.get("required", False) else 0,
                        str(item.get("name", "")),
                        str(item.get("path", "")),
                    ),
                )
            runtime = operator_payload.get("runtime")
            if isinstance(runtime, dict):
                conn.execute(
                    """
                    INSERT INTO operator_record_runtime
                    (operator_id, backend, image_ref, entrypoint, workflow_path,
                     inputs_json_path, dockerfile_path)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        operator_id,
                        str(runtime.get("backend", "")),
                        str(runtime.get("image_ref", "")),
                        str(runtime.get("entrypoint", "")),
                        str(runtime.get("workflow_path", "")),
                        str(runtime.get("inputs_json_path", "")),
                        str(runtime.get("dockerfile_path", "")),
                    ),
                )
            for item in _list_of_dicts(operator_payload.get("metrics")):
                conn.execute(
                    """
                    INSERT INTO operator_record_metrics
                    (operator_id, metric_name, metric_type, description)
                    VALUES (?, ?, ?, ?)
                    """,
                    (
                        operator_id,
                        str(item.get("name", "")),
                        str(item.get("type", "")),
                        str(item.get("description", "")),
                    ),
                )
            for tag in operator_payload.get("tags", []):
                if isinstance(tag, str) and tag.strip():
                    conn.execute(
                        "INSERT INTO operator_record_tags (operator_id, tag) VALUES (?, ?)",
                        (operator_id, tag.strip()),
                    )
            if validation_payload is not None:
                validation_id = str(validation_payload.get("validation_id", "")).strip()
                if validation_id:
                    conn.execute(
                        """
                        INSERT OR REPLACE INTO operator_record_validations
                        (validation_id, operator_id, version, run_id, status,
                         dataset_id, run_dir, summary, created_at,
                         validation_path, product_manifest_path)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            validation_id,
                            operator_id,
                            str(validation_payload.get("version", "")),
                            str(validation_payload.get("run_id", "")),
                            str(validation_payload.get("status", "")),
                            str(validation_payload.get("dataset_id", "")),
                            str(validation_payload.get("run_dir", "")),
                            str(validation_payload.get("summary", "")),
                            str(validation_payload.get("created_at", "")),
                            str(validation_payload.get("validation_path", "")),
                            str(validation_payload.get("product_manifest_path", "")),
                        ),
                    )
            if embedding_payload is not None:
                self._upsert_embedding(conn, embedding_payload)
            self._refresh_fts(conn, operator_payload)
            conn.commit()

    def _upsert_embedding(self, conn: sqlite3.Connection, embedding_payload: dict[str, object]) -> None:
        operator_id = str(embedding_payload.get("operator_id", "")).strip()
        vector = embedding_payload.get("vector")
        if not operator_id or not isinstance(vector, list) or not vector:
            return
        vector_json = json.dumps(vector, ensure_ascii=False)
        conn.execute(
            """
            INSERT OR REPLACE INTO operator_record_embeddings
            (operator_id, model, dimensions, source_text_sha256, source_text,
             vector_json, embedding_path, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                operator_id,
                str(embedding_payload.get("model", "")),
                int(embedding_payload.get("dimensions", 0)),
                str(embedding_payload.get("source_text_sha256", "")),
                str(embedding_payload.get("source_text", "")),
                vector_json,
                str(embedding_payload.get("embedding_path", "")),
                str(embedding_payload.get("updated_at", "")),
            ),
        )
        self._meta_set(conn, "embedding_model", str(embedding_payload.get("model", "")))
        if self._vec_extension_available(conn):
            self._ensure_vec_table(conn, int(embedding_payload.get("dimensions", 0)))
        if self._vec_table_available(conn):
            conn.execute(
                """
                INSERT INTO operator_record_vec
                (operator_id, embedding)
                VALUES (?, ?)
                """,
                (
                    operator_id,
                    vector_json,
                ),
            )

    def _materialize_operator_embedding(
        self,
        *,
        operator_payload: dict[str, object],
        embedding_path: Path,
    ) -> dict[str, object] | None:
        source_text = str(operator_payload.get("canonical_text", "")).strip()
        if not source_text:
            return None
        source_text_sha256 = hashlib.sha256(source_text.encode("utf-8")).hexdigest()
        model_name = _embedding_model_name()
        existing = None
        if embedding_path.exists():
            try:
                existing = _read_json(embedding_path)
            except (OSError, json.JSONDecodeError):
                existing = None
        if (
                isinstance(existing, dict)
                and str(existing.get("model", "")) == model_name
                and str(existing.get("source_text_sha256", "")) == source_text_sha256
            ):
                return existing
        try:
            vectors, embedded_model = _embed_documents([source_text])
        except Exception:
            return None
        if not vectors or not embedded_model:
            return None
        vector = vectors[0]
        payload = {
            "schema_version": SCHEMA_VERSION,
            "operator_id": str(operator_payload.get("operator_id", "")),
            "model": embedded_model,
            "dimensions": len(vector),
            "source_text_sha256": source_text_sha256,
            "source_text": source_text,
            "vector": vector,
            "embedding_path": str(embedding_path),
            "updated_at": _utc_now(),
        }
        _write_json_file(embedding_path, payload)
        return payload

    def _refresh_fts(self, conn: sqlite3.Connection, operator_payload: dict[str, object]) -> None:
        if not self._fts_available(conn):
            return
        operator_id = str(operator_payload.get("operator_id", "")).strip()
        conn.execute("DELETE FROM operator_record_fts WHERE operator_id = ?", (operator_id,))
        conn.execute(
            """
            INSERT INTO operator_record_fts
            (operator_id, name, summary, description, tags_text, io_text, source_repo)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                operator_id,
                str(operator_payload.get("name", "")),
                str(operator_payload.get("summary", "")),
                str(operator_payload.get("description", "")),
                " ".join(str(tag) for tag in operator_payload.get("tags", []) if isinstance(tag, str)),
                _io_text(operator_payload),
                str(operator_payload.get("source_repo", "")),
            ),
        )

    def _clear_index(self) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM operator_records")
            conn.execute("DELETE FROM operator_record_io")
            conn.execute("DELETE FROM operator_record_runtime")
            conn.execute("DELETE FROM operator_record_metrics")
            conn.execute("DELETE FROM operator_record_tags")
            conn.execute("DELETE FROM operator_record_validations")
            conn.execute("DELETE FROM operator_record_embeddings")
            conn.execute("DELETE FROM operator_store_meta")
            if self._fts_available(conn):
                conn.execute("DELETE FROM operator_record_fts")
            if self._vec_table_available(conn):
                conn.execute("DELETE FROM operator_record_vec")

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        try:
            conn.enable_load_extension(True)
            import sqlite_vec

            sqlite_vec.load(conn)
            conn.enable_load_extension(False)
        except (ImportError, AttributeError, sqlite3.OperationalError):
            pass
        return conn

    def _fts_available(self, conn: sqlite3.Connection) -> bool:
        row = conn.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type = 'table' AND name = 'operator_record_fts'
            """
        ).fetchone()
        return row is not None

    def _vec_extension_available(self, conn: sqlite3.Connection) -> bool:
        try:
            conn.execute("SELECT vec_version()").fetchone()
        except sqlite3.OperationalError:
            return False
        return True

    def _vec_table_available(self, conn: sqlite3.Connection) -> bool:
        row = conn.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type = 'table' AND name = 'operator_record_vec'
            """
        ).fetchone()
        return row is not None

    def _meta_get(self, conn: sqlite3.Connection, key: str) -> str | None:
        row = conn.execute(
            "SELECT value FROM operator_store_meta WHERE key = ?",
            (key,),
        ).fetchone()
        if row is None:
            return None
        return str(row[0])

    def _meta_set(self, conn: sqlite3.Connection, key: str, value: str) -> None:
        conn.execute(
            """
            INSERT OR REPLACE INTO operator_store_meta (key, value)
            VALUES (?, ?)
            """,
            (key, value),
        )

    def _ensure_vec_table(self, conn: sqlite3.Connection, dimensions: int) -> None:
        if dimensions <= 0 or not self._vec_extension_available(conn):
            return
        stored_dimensions = self._meta_get(conn, "embedding_dimensions")
        if self._vec_table_available(conn):
            if stored_dimensions == str(dimensions):
                return
            conn.execute("DROP TABLE operator_record_vec")
        conn.execute(
            f"""
            CREATE VIRTUAL TABLE IF NOT EXISTS operator_record_vec
            USING vec0(
                operator_id text metadata,
                embedding float[{dimensions}]
            )
            """
        )
        self._meta_set(conn, "embedding_dimensions", str(dimensions))

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS operator_records (
                    operator_id TEXT PRIMARY KEY,
                    family TEXT NOT NULL,
                    name TEXT NOT NULL,
                    version TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    description TEXT NOT NULL,
                    source_repo TEXT NOT NULL,
                    source_commit TEXT NOT NULL,
                    operator_path TEXT NOT NULL,
                    latest_version_path TEXT NOT NULL,
                    latest_validation_path TEXT NOT NULL,
                    latest_product_manifest_path TEXT NOT NULL,
                    validation_status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    canonical_text TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS operator_record_io (
                    operator_id TEXT NOT NULL,
                    direction TEXT NOT NULL,
                    media_type TEXT NOT NULL,
                    schema_path TEXT NOT NULL,
                    required INTEGER NOT NULL,
                    name TEXT NOT NULL,
                    path TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS operator_record_runtime (
                    operator_id TEXT PRIMARY KEY,
                    backend TEXT NOT NULL,
                    image_ref TEXT NOT NULL,
                    entrypoint TEXT NOT NULL,
                    workflow_path TEXT NOT NULL,
                    inputs_json_path TEXT NOT NULL,
                    dockerfile_path TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS operator_record_metrics (
                    operator_id TEXT NOT NULL,
                    metric_name TEXT NOT NULL,
                    metric_type TEXT NOT NULL,
                    description TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS operator_record_tags (
                    operator_id TEXT NOT NULL,
                    tag TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS operator_record_validations (
                    validation_id TEXT PRIMARY KEY,
                    operator_id TEXT NOT NULL,
                    version TEXT NOT NULL,
                    run_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    dataset_id TEXT NOT NULL,
                    run_dir TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    validation_path TEXT NOT NULL,
                    product_manifest_path TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS operator_record_embeddings (
                    operator_id TEXT PRIMARY KEY,
                    model TEXT NOT NULL,
                    dimensions INTEGER NOT NULL,
                    source_text_sha256 TEXT NOT NULL,
                    source_text TEXT NOT NULL,
                    vector_json TEXT NOT NULL,
                    embedding_path TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS operator_store_meta (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_operator_record_io_lookup
                ON operator_record_io(direction, media_type)
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_operator_record_metrics_lookup
                ON operator_record_metrics(metric_name)
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_operator_record_tags_lookup
                ON operator_record_tags(tag)
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_operator_record_validations_status
                ON operator_record_validations(status, created_at)
                """
            )
            try:
                conn.execute(
                    """
                    CREATE VIRTUAL TABLE IF NOT EXISTS operator_record_fts
                    USING fts5(
                        operator_id UNINDEXED,
                        name,
                        summary,
                        description,
                        tags_text,
                        io_text,
                        source_repo,
                        tokenize = 'unicode61'
                    )
                    """
                )
            except sqlite3.OperationalError:
                pass


def build_benchmark_operator_manifest(
    *,
    product_id: str,
    name: str,
    version: str,
    run_dir: Path,
    case_dir: Path,
    case_manifest: dict[str, object],
    ready_payload: dict[str, object],
    status: str,
    validation_summary: str,
    source_repo: str = "",
) -> dict[str, object]:
    """Build a manifest for one staged benchmark case."""
    dataset_id = str(case_manifest.get("dataset_key", ""))
    input_items = _benchmark_input_items(case_manifest)
    output_items = _benchmark_output_items(case_manifest)
    metric_items = [
        {
            "name": str(metric),
            "type": "numeric",
            "description": f"Benchmark metric collected for {name}.",
        }
        for metric in case_manifest.get("metric_keys", [])
        if isinstance(metric, str) and metric.strip()
    ]
    runtime_image = str(
        ready_payload.get("runtime_image")
        or case_manifest.get("runtime_image")
        or case_manifest.get("image_tag")
        or ""
    )
    wdl_path = str(
        ready_payload.get("wdl_path")
        or case_manifest.get("wdl_path")
        or case_manifest.get("source_wdl_path")
        or ""
    )
    inputs_json_path = str(
        ready_payload.get("inputs_json_path")
        or case_manifest.get("inputs_json_path")
        or case_manifest.get("source_inputs_path")
        or ""
    )
    created_at = _utc_now()
    return {
        "product_id": product_id,
        "operator_id": f"benchmark:{name}",
        "name": name,
        "family": "benchmark",
        "version": version,
        "status": status,
        "summary": validation_summary,
        "created_at": created_at,
        "source": {
            "repo_url": source_repo,
            "repo_name": str(case_manifest.get("repo_name", name)),
            "commit": "",
            "case_dir": str(case_dir),
            "source_case_dir": str(case_manifest.get("source_case_dir", "")),
        },
        "runtime": {
            "backend": "wdl" if wdl_path else "unknown",
            "image_ref": runtime_image,
            "entrypoint": str(case_manifest.get("repo_native_entry", "")),
            "entry_workflow": _workflow_name_from_path(wdl_path),
            "workflow_path": wdl_path,
            "inputs_json_path": inputs_json_path,
            "dockerfile_path": str(
                ready_payload.get("dockerfile_path")
                or case_manifest.get("dockerfile_path")
                or ""
            ),
        },
        "inputs": input_items,
        "outputs": output_items,
        "metrics": metric_items,
        "validation": {
            "validation_id": f"benchmark-register:{version}:{name}",
            "status": status,
            "dataset_id": dataset_id,
            "run_dir": str(run_dir),
            "summary": validation_summary,
            "created_at": created_at,
        },
        "artifacts": {
            "case_manifest": str(case_dir / "manifest.json"),
            "execution_ready": str(case_dir / "execution_ready.json"),
            "dataset_manifest": str(case_dir / "dataset_manifest.json"),
            "result_manifest": str(case_dir / "run" / "result_manifest.json"),
            "analysis": str(case_dir / "analysis.json"),
        },
        "tags": _benchmark_tags(
            case_manifest=case_manifest,
            ready_payload=ready_payload,
            status=status,
        ),
    }


def build_github2workspace_operator_manifest(
    *,
    product_id: str,
    name: str,
    version: str,
    workspace_root: Path,
    run_dir: Path,
    status: str,
    source_repo: str,
    validation_summary: str,
) -> dict[str, object]:
    """Build a manifest for one github2workspace product."""
    created_at = _utc_now()
    dockerfile_path = workspace_root / f"{name}_Dockerfile"
    wdl_path = workspace_root / f"{name}.wdl"
    inputs_path = workspace_root / "inputs.json"
    docker_result_dir = workspace_root / "results" / "docker_test"
    wdl_result_dir = workspace_root / "results" / "wdl_result"
    wdl_outputs = wdl_result_dir / "outputs.json"
    runtime_backend = "wdl" if wdl_path.exists() else "docker"
    workflow_path = str(wdl_path) if wdl_path.exists() else ""
    return {
        "product_id": product_id,
        "operator_id": f"github2workspace:{name}",
        "name": name,
        "family": "github2workspace",
        "version": version,
        "status": status,
        "summary": validation_summary,
        "created_at": created_at,
        "source": {
            "repo_url": source_repo,
            "repo_name": name,
            "commit": "",
            "workspace_root": str(workspace_root),
        },
        "runtime": {
            "backend": runtime_backend,
            "image_ref": name,
            "entrypoint": "",
            "entry_workflow": _workflow_name_from_path(workflow_path),
            "workflow_path": workflow_path,
            "inputs_json_path": str(inputs_path) if inputs_path.exists() else "",
            "dockerfile_path": str(dockerfile_path) if dockerfile_path.exists() else "",
        },
        "inputs": _github_workspace_input_items(workspace_root=workspace_root),
        "outputs": _github_workspace_output_items(workspace_root=workspace_root),
        "metrics": [],
        "validation": {
            "validation_id": f"github2workspace:{version}:{name}",
            "status": status,
            "dataset_id": "",
            "run_dir": str(run_dir),
            "summary": validation_summary,
            "created_at": created_at,
        },
        "artifacts": {
            "dockerfile": str(dockerfile_path) if dockerfile_path.exists() else "",
            "wdl": workflow_path,
            "inputs": str(inputs_path) if inputs_path.exists() else "",
            "docker_test": str(docker_result_dir) if docker_result_dir.exists() else "",
            "wdl_outputs": str(wdl_outputs) if wdl_outputs.exists() else "",
            "run_dir": str(run_dir),
        },
        "tags": _github_workspace_tags(
            status=status,
            has_dockerfile=dockerfile_path.exists(),
            has_wdl=wdl_path.exists(),
            has_wdl_outputs=wdl_outputs.exists() and wdl_outputs.stat().st_size > 0,
            uses_synthetic_inputs=_github_workspace_uses_synthetic_inputs(
                workspace_root=workspace_root,
            ),
        ),
    }


def _normalize_manifest(
    *,
    payload: dict[str, object],
    manifest_path: Path,
) -> dict[str, str]:
    operator_id = str(payload.get("operator_id") or _stable_operator_id(payload)).strip()
    if not operator_id:
        msg = f"Operator manifest is missing operator_id: {manifest_path}"
        raise ValueError(msg)
    version = str(payload.get("version", "unversioned")).strip() or "unversioned"
    validation = payload.get("validation")
    validation_payload = validation if isinstance(validation, dict) else {}
    run_dir = str(validation_payload.get("run_dir", "")).strip()
    run_id = Path(run_dir).name if run_dir else version
    validation_id = (
        str(validation_payload.get("validation_id", "")).strip()
        or f"{operator_id}:{run_id}"
    )
    summary = (
        str(payload.get("summary", "")).strip()
        or str(validation_payload.get("summary", "")).strip()
        or f"{payload.get('name', 'operator')} validation record"
    )
    description = str(payload.get("description", "")).strip() or summary
    created_at = (
        str(payload.get("created_at", "")).strip()
        or str(validation_payload.get("created_at", "")).strip()
        or _utc_now()
    )
    return {
        "operator_id": operator_id,
        "version": version,
        "run_id": run_id,
        "validation_id": validation_id,
        "summary": summary,
        "description": description,
        "created_at": created_at,
        "updated_at": str(payload.get("updated_at", "")).strip() or _utc_now(),
    }


def _build_operator_record_payload(
    *,
    payload: dict[str, object],
    normalized: dict[str, str],
    existing_operator: dict[str, object] | None,
    operator_path: Path,
    version_path: Path,
    validation_path: Path,
    embedding_path: Path,
    manifest_path: Path,
) -> dict[str, object]:
    runtime = payload.get("runtime")
    runtime_payload = dict(runtime) if isinstance(runtime, dict) else {}
    if not runtime_payload.get("entry_workflow"):
        runtime_payload["entry_workflow"] = _workflow_name_from_path(
            str(runtime_payload.get("workflow_path", ""))
        )
    source = payload.get("source")
    source_payload = source if isinstance(source, dict) else {}
    created_at = (
        str(existing_operator.get("created_at", "")).strip()
        if isinstance(existing_operator, dict)
        else normalized["created_at"]
    ) or normalized["created_at"]
    operator_payload = {
        "schema_version": SCHEMA_VERSION,
        "operator_id": normalized["operator_id"],
        "family": str(payload.get("family", "")),
        "name": str(payload.get("name", "")),
        "version": normalized["version"],
        "summary": normalized["summary"],
        "description": normalized["description"],
        "source_repo": _nested_str(source_payload, "repo_url"),
        "source_commit": _nested_str(source_payload, "commit"),
        "source": source_payload,
        "runtime": runtime_payload,
        "inputs": _list_of_dicts(payload.get("inputs")),
        "outputs": _list_of_dicts(payload.get("outputs")),
        "metrics": _list_of_dicts(payload.get("metrics")),
        "tags": sorted(
            {
                str(tag).strip()
                for tag in payload.get("tags", [])
                if isinstance(tag, str) and tag.strip()
            }
        ),
        "input_media_types": _unique_media_types(payload.get("inputs")),
        "output_media_types": _unique_media_types(payload.get("outputs")),
        "expected_outputs": _output_names(payload.get("outputs")),
        "validation_status": str(payload.get("status", "")),
        "latest_validation_id": normalized["validation_id"],
        "created_at": created_at,
        "updated_at": normalized["updated_at"],
        "operator_path": str(operator_path),
        "latest_version_path": str(version_path),
        "latest_validation_path": str(validation_path),
        "latest_embedding_path": str(embedding_path),
        "latest_product_manifest_path": str(manifest_path),
    }
    operator_payload["canonical_text"] = _operator_canonical_text(operator_payload)
    return operator_payload


def _build_operator_version_payload(
    *,
    payload: dict[str, object],
    normalized: dict[str, str],
    operator_path: Path,
    version_path: Path,
    manifest_path: Path,
) -> dict[str, object]:
    return {
        "schema_version": SCHEMA_VERSION,
        "operator_id": normalized["operator_id"],
        "version": normalized["version"],
        "name": str(payload.get("name", "")),
        "family": str(payload.get("family", "")),
        "summary": normalized["summary"],
        "runtime": payload.get("runtime", {}),
        "inputs": _list_of_dicts(payload.get("inputs")),
        "outputs": _list_of_dicts(payload.get("outputs")),
        "metrics": _list_of_dicts(payload.get("metrics")),
        "artifacts": payload.get("artifacts", {}),
        "source": payload.get("source", {}),
        "created_at": normalized["created_at"],
        "updated_at": normalized["updated_at"],
        "operator_path": str(operator_path),
        "version_path": str(version_path),
        "product_manifest_path": str(manifest_path),
    }


def _build_validation_record_payload(
    *,
    payload: dict[str, object],
    normalized: dict[str, str],
    validation_path: Path,
    manifest_path: Path,
) -> dict[str, object]:
    validation = payload.get("validation")
    validation_payload = validation if isinstance(validation, dict) else {}
    return {
        "schema_version": SCHEMA_VERSION,
        "validation_id": normalized["validation_id"],
        "operator_id": normalized["operator_id"],
        "family": str(payload.get("family", "")),
        "name": str(payload.get("name", "")),
        "version": normalized["version"],
        "run_id": normalized["run_id"],
        "status": str(validation_payload.get("status") or payload.get("status", "")),
        "dataset_id": str(validation_payload.get("dataset_id", "")),
        "run_dir": str(validation_payload.get("run_dir", "")),
        "summary": str(validation_payload.get("summary") or normalized["summary"]),
        "created_at": str(validation_payload.get("created_at") or normalized["created_at"]),
        "artifacts": payload.get("artifacts", {}),
        "metrics": _list_of_dicts(payload.get("metrics")),
        "runtime": payload.get("runtime", {}),
        "validation_path": str(validation_path),
        "product_manifest_path": str(manifest_path),
    }


def _search_conditions(filters: OperatorSearchFilter) -> tuple[list[str], list[object]]:
    where = ["1 = 1"]
    params: list[object] = []
    if filters.family:
        where.append("o.family = ?")
        params.append(filters.family)
    if filters.status:
        where.append("o.validation_status = ?")
        params.append(filters.status)
    if filters.input_media_type:
        where.append(
            """
            EXISTS (
              SELECT 1 FROM operator_record_io io
              WHERE io.operator_id = o.operator_id
                AND io.direction = 'input'
                AND io.media_type = ?
            )
            """
        )
        params.append(filters.input_media_type)
    if filters.output_media_type:
        where.append(
            """
            EXISTS (
              SELECT 1 FROM operator_record_io io
              WHERE io.operator_id = o.operator_id
                AND io.direction = 'output'
                AND io.media_type = ?
            )
            """
        )
        params.append(filters.output_media_type)
    if filters.metric_name:
        where.append(
            """
            EXISTS (
              SELECT 1 FROM operator_record_metrics m
              WHERE m.operator_id = o.operator_id
                AND m.metric_name = ?
            )
            """
        )
        params.append(filters.metric_name)
    requested_tags = []
    if filters.tag:
        requested_tags.append(filters.tag)
    requested_tags.extend(filters.tags)
    for tag in requested_tags:
        where.append(
            """
            EXISTS (
              SELECT 1 FROM operator_record_tags t
              WHERE t.operator_id = o.operator_id
                AND t.tag = ?
            )
            """
        )
        params.append(tag)
    return where, params


def _row_to_result(row: tuple[object, ...]) -> dict[str, object]:
    return {
        "id": row[0],
        "name": row[1],
        "family": row[2],
        "version": row[3],
        "status": row[4],
        "manifest_path": row[5],
        "operator_path": row[6],
        "validation_path": row[7],
    }


def _benchmark_input_items(case_manifest: dict[str, object]) -> list[dict[str, object]]:
    selected = case_manifest.get("selected_input_files")
    items: list[dict[str, object]] = []
    if isinstance(selected, dict):
        for name, path in selected.items():
            if not isinstance(path, str) or not path.strip():
                continue
            items.append(
                {
                    "name": str(name),
                    "media_type": _infer_media_type(path),
                    "path": path,
                    "schema_path": "",
                    "required": True,
                }
            )
    inputs_path = (
        case_manifest.get("inputs_json_path")
        or case_manifest.get("source_inputs_path")
        or case_manifest.get("inputs_path")
    )
    if isinstance(inputs_path, str) and inputs_path.strip():
        items.append(
            {
                "name": "input_json",
                "media_type": "json",
                "path": inputs_path,
                "schema_path": "",
                "required": True,
            }
        )
    return items


def _github_workspace_input_items(*, workspace_root: Path) -> list[dict[str, object]]:
    test_data_dir = workspace_root / "spades" / "src" / "test" / "data"
    items: list[dict[str, object]] = [
        {
            "name": path.name,
            "media_type": _infer_media_type(str(path)),
            "path": str(path),
            "schema_path": "",
            "required": False,
        }
        for path in sorted(test_data_dir.glob("*"))
        if path.is_file()
    ]
    inputs_path = workspace_root / "inputs.json"
    if inputs_path.exists():
        items.append(
            {
                "name": "input_json",
                "media_type": "json",
                "path": str(inputs_path),
                "schema_path": "",
                "required": True,
            }
        )
    return items


def _github_workspace_output_items(*, workspace_root: Path) -> list[dict[str, object]]:
    items: list[dict[str, object]] = []
    for path in sorted((workspace_root / "results").glob("**/*")):
        if not path.is_file():
            continue
        expected_names = {
            "contigs.fasta",
            "scaffolds.fasta",
            "spades.log",
            "outputs.json",
        }
        if path.name not in expected_names:
            continue
        items.append(
            {
                "name": path.name,
                "media_type": _infer_media_type(str(path)),
                "path": str(path),
                "schema_path": "",
                "required": path.name == "outputs.json",
            }
        )
    return items


def _benchmark_output_items(case_manifest: dict[str, object]) -> list[dict[str, object]]:
    outputs = case_manifest.get("expected_outputs")
    items: list[dict[str, object]] = []
    if isinstance(outputs, list):
        for output in outputs:
            if isinstance(output, str):
                name = Path(output).name or output
                path = output
            elif isinstance(output, dict):
                name = str(output.get("name") or output.get("path") or "output")
                path = str(output.get("path") or output.get("glob") or "")
            else:
                continue
            items.append(
                {
                    "name": name,
                    "media_type": _infer_media_type(path or name),
                    "path": path,
                    "schema_path": "",
                    "required": False,
                }
            )
    return items


def _benchmark_tags(
    *,
    case_manifest: dict[str, object],
    ready_payload: dict[str, object],
    status: str,
) -> list[str]:
    tags = {
        "benchmark",
        status,
        f"dataset:{case_manifest.get('dataset_key', '')}",
    }
    if ready_payload.get("ready"):
        tags.add("execution-ready")
    if case_manifest.get("wdl_path") or ready_payload.get("wdl_path"):
        tags.add("wdl")
    if (
        ready_payload.get("runtime_image")
        or case_manifest.get("runtime_image")
        or case_manifest.get("image_tag")
    ):
        tags.add("container")
    return sorted(tag for tag in tags if tag and not tag.endswith(":"))


def _github_workspace_tags(
    *,
    status: str,
    has_dockerfile: bool,
    has_wdl: bool,
    has_wdl_outputs: bool,
    uses_synthetic_inputs: bool,
) -> list[str]:
    tags = {"github2workspace", status}
    if has_dockerfile:
        tags.add("docker")
    if has_wdl:
        tags.add("wdl")
    if has_wdl_outputs:
        tags.add("wdl-completed")
    if uses_synthetic_inputs:
        tags.add("synthetic-inputs")
    return sorted(tags)


def _github_workspace_uses_synthetic_inputs(*, workspace_root: Path) -> bool:
    inputs_path = workspace_root / "inputs.json"
    if not inputs_path.exists():
        return False
    try:
        payload = json.loads(inputs_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return False
    if not isinstance(payload, dict):
        return False
    for value in payload.values():
        if not isinstance(value, str):
            continue
        lowered = value.casefold()
        if any(marker in lowered for marker in ("toy", "synthetic", "generated")):
            return True
        if "/results/wdl_file/" in lowered and lowered.endswith((".fastq", ".fq", ".fasta", ".fa")):
            return True
    return False


def _stable_operator_id(payload: dict[str, object]) -> str:
    family = str(payload.get("family", "unknown")).strip() or "unknown"
    name = str(payload.get("name", payload.get("product_id", "operator"))).strip() or "operator"
    return f"{family}:{name}"


def _safe_path_part(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", value.strip())
    return cleaned.strip("-") or "unknown"


def _infer_media_type(path: str) -> str:
    lowered = path.casefold()
    if lowered.endswith((".fastq", ".fq", ".fastq.gz", ".fq.gz")):
        return "fastq"
    if lowered.endswith((".fasta", ".fa", ".fna", ".faa", ".fasta.gz", ".fa.gz")):
        return "fasta"
    if lowered.endswith((".bam", ".sam", ".cram")):
        return "alignment"
    if lowered.endswith((".pdb", ".pdbqt", ".cif")):
        return "structure"
    if lowered.endswith((".csv", ".tsv")):
        return "table"
    if lowered.endswith(".json"):
        return "json"
    if lowered.endswith((".txt", ".md", ".log")):
        return "text"
    return "file"


def _read_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json_file(path: Path, payload: dict[str, object]) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def _nested_str(payload: dict[str, object], key: str) -> str:
    value = payload.get(key)
    return "" if value is None else str(value)


def _list_of_dicts(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _unique_media_types(value: object) -> list[str]:
    return sorted(
        {
            str(item.get("media_type", "")).strip()
            for item in _list_of_dicts(value)
            if str(item.get("media_type", "")).strip()
        }
    )


def _output_names(value: object) -> list[str]:
    return [
        str(item.get("name", "")).strip()
        for item in _list_of_dicts(value)
        if str(item.get("name", "")).strip()
    ]


def _operator_canonical_text(payload: dict[str, object]) -> str:
    parts = [
        str(payload.get("operator_id", "")),
        str(payload.get("name", "")),
        str(payload.get("family", "")),
        str(payload.get("summary", "")),
        str(payload.get("description", "")),
        " ".join(str(tag) for tag in payload.get("tags", []) if isinstance(tag, str)),
        " ".join(str(item) for item in payload.get("input_media_types", []) if isinstance(item, str)),
        " ".join(str(item) for item in payload.get("output_media_types", []) if isinstance(item, str)),
        " ".join(str(item) for item in payload.get("expected_outputs", []) if isinstance(item, str)),
        str(payload.get("source_repo", "")),
    ]
    return "\n".join(part for part in parts if part)


def _io_text(payload: dict[str, object]) -> str:
    rows: list[str] = []
    for direction in ("inputs", "outputs"):
        for item in _list_of_dicts(payload.get(direction)):
            rows.append(
                " ".join(
                    [
                        direction[:-1],
                        str(item.get("name", "")),
                        str(item.get("media_type", "")),
                        str(item.get("path", "")),
                    ]
                ).strip()
            )
    return "\n".join(row for row in rows if row)


def _workflow_name_from_path(path: str) -> str:
    raw = path.strip()
    if not raw:
        return ""
    return Path(raw).stem


def _tokenize(text: str) -> list[str]:
    tokens = [token.casefold() for token in re.findall(r"[\w.-]+", text, flags=re.UNICODE)]
    if tokens:
        return tokens
    stripped = text.strip().casefold()
    return [stripped] if stripped else []


def _merge_ranked_results(
    *,
    semantic_rows: list[dict[str, object]],
    text_rows: list[dict[str, object]],
    limit: int,
) -> list[dict[str, object]]:
    by_id: dict[str, dict[str, object]] = {}
    scores: dict[str, float] = {}
    for rank, row in enumerate(semantic_rows, start=1):
        operator_id = str(row.get("id", ""))
        if not operator_id:
            continue
        by_id.setdefault(operator_id, row)
        scores[operator_id] = scores.get(operator_id, 0.0) + (2.0 / (20.0 + rank))
    for rank, row in enumerate(text_rows, start=1):
        operator_id = str(row.get("id", ""))
        if not operator_id:
            continue
        by_id.setdefault(operator_id, row)
        scores[operator_id] = scores.get(operator_id, 0.0) + (1.0 / (20.0 + rank))
    ordered_ids = sorted(
        scores,
        key=lambda item: (-scores[item], str(by_id[item].get("name", "")), item),
    )
    return [by_id[item] for item in ordered_ids[:limit]]


def _cosine_similarity(lhs: list[float], rhs: list[float]) -> float:
    if not lhs or not rhs or len(lhs) != len(rhs):
        return 0.0
    numerator = sum(a * b for a, b in zip(lhs, rhs, strict=False))
    lhs_norm = math.sqrt(sum(a * a for a in lhs))
    rhs_norm = math.sqrt(sum(b * b for b in rhs))
    if lhs_norm == 0 or rhs_norm == 0:
        return 0.0
    return numerator / (lhs_norm * rhs_norm)


def _embedding_enabled() -> bool:
    raw = os.environ.get(_EMBEDDING_ENABLED_ENV, "1").strip().casefold()
    if raw in {"0", "false", "no", "off"}:
        return False
    return True


def _embedding_model_name() -> str:
    return os.environ.get(_EMBEDDING_MODEL_ENV, _DEFAULT_EMBEDDING_MODEL).strip() or _DEFAULT_EMBEDDING_MODEL


def _embed_documents(texts: list[str]) -> tuple[list[list[float]], str | None]:
    if not texts or not _embedding_enabled():
        return [], None
    backend = _embedding_backend()
    if backend is None:
        return [], None
    return backend.embed_documents(texts), _embedding_model_name()


def _embed_query(text: str) -> tuple[list[float], str | None]:
    if not text.strip() or not _embedding_enabled():
        return [], None
    backend = _embedding_backend()
    if backend is None:
        return [], None
    return backend.embed_query(text), _embedding_model_name()


@lru_cache(maxsize=1)
def _embedding_backend():
    try:
        from langchain_openai import OpenAIEmbeddings
    except ImportError:
        return None
    try:
        from code2workspace_cli.model_config import resolve_env_var
    except ImportError:
        return None
    api_key = os.environ.get(_EMBEDDING_API_KEY_ENV) or resolve_env_var("OPENAI_API_KEY")
    if not api_key:
        return None
    kwargs: dict[str, object] = {
        "model": _embedding_model_name(),
        "api_key": api_key,
    }
    base_url = os.environ.get(_EMBEDDING_BASE_URL_ENV) or resolve_env_var("OPENAI_BASE_URL")
    if base_url:
        kwargs["base_url"] = base_url
    return OpenAIEmbeddings(**kwargs)


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()
