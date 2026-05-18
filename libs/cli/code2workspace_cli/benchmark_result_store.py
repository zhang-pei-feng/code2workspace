"""Benchmark comparison history store with optional embedding-backed retrieval.

The module name is kept for compatibility; the user-facing store is the
benchmark comparison history store.
"""
# ruff: noqa: DOC201, DOC501

from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from code2workspace_cli.operator_store import _cosine_similarity, _embed_documents, _embed_query

SCHEMA_VERSION = "0.1"
BENCHMARK_RECORD_NAME = "benchmark_result_record.json"
BENCHMARK_EMBEDDING_NAME = "embedding.json"


@dataclass(frozen=True, slots=True)
class BenchmarkResultSearchFilter:
    """Structured filter for benchmark result lookup."""

    query: str | None = None
    repo: str | None = None
    operator_id: str | None = None
    dataset_key: str | None = None
    workflow_signature: str | None = None
    input_signature: str | None = None
    success_only: bool = True
    limit: int = 20


class BenchmarkResultStore:
    """Store and query historical benchmark comparison execution records."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.records_dir = root / "records"
        self.db_path = root / "index.sqlite"
        self.root.mkdir(parents=True, exist_ok=True)
        self.records_dir.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def record_dir(self, *, repo: str, run_id: str) -> Path:
        return self.records_dir / _safe_part(repo) / _safe_part(run_id)

    def record_path(self, *, repo: str, run_id: str) -> Path:
        return self.record_dir(repo=repo, run_id=run_id) / BENCHMARK_RECORD_NAME

    def embedding_path(self, *, repo: str, run_id: str) -> Path:
        return self.record_dir(repo=repo, run_id=run_id) / BENCHMARK_EMBEDDING_NAME

    def write_record(
        self,
        record: dict[str, object],
        *,
        record_dir: Path | None = None,
    ) -> Path:
        repo = str(record.get("repo", "")).strip() or "unknown"
        run_id = str(record.get("run_id", "")).strip() or "unknown-run"
        target_dir = record_dir or self.record_dir(repo=repo, run_id=run_id)
        target_dir.mkdir(parents=True, exist_ok=True)
        record_path = target_dir / BENCHMARK_RECORD_NAME
        payload = {
            "schema_version": SCHEMA_VERSION,
            **record,
            "record_id": str(record.get("record_id") or _default_record_id(record)),
            "record_path": str(record_path),
            "updated_at": str(record.get("updated_at") or _utc_now()),
        }
        record_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        self.upsert_record(record_path)
        return record_path

    def upsert_record(self, record_path: Path) -> None:
        payload = _read_json(record_path)
        normalized = _normalize_record(payload=payload, record_path=record_path)
        embedding_path = self.embedding_path(
            repo=normalized["repo"],
            run_id=normalized["run_id"],
        )
        embedding_payload = self._materialize_record_embedding(
            normalized=normalized,
            embedding_path=embedding_path,
        )

        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO benchmark_records
                (record_id, repo, operator_id, dataset_key, workflow_signature,
                 input_signature, success, returncode, run_id, run_dir, case_dir,
                 workflow_path, inputs_json_path, status_path, wdl_status_path,
                 result_manifest_path, analysis_path, canonical_text, record_path,
                 updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    normalized["record_id"],
                    normalized["repo"],
                    normalized["operator_id"],
                    normalized["dataset_key"],
                    normalized["workflow_signature"],
                    normalized["input_signature"],
                    1 if normalized["success"] else 0,
                    normalized["returncode"],
                    normalized["run_id"],
                    normalized["run_dir"],
                    normalized["case_dir"],
                    normalized["workflow_path"],
                    normalized["inputs_json_path"],
                    normalized["status_path"],
                    normalized["wdl_status_path"],
                    normalized["result_manifest_path"],
                    normalized["analysis_path"],
                    normalized["canonical_text"],
                    str(record_path),
                    normalized["updated_at"],
                ),
            )
            if embedding_payload is not None:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO benchmark_record_embeddings
                    (record_id, model, vector_json, embedding_path, updated_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        normalized["record_id"],
                        str(embedding_payload.get("model", "")),
                        json.dumps(embedding_payload.get("vector", []), ensure_ascii=False),
                        str(embedding_path),
                        str(embedding_payload.get("updated_at", "")),
                    ),
                )

    def rebuild(self) -> int:
        with self._connect() as conn:
            conn.execute("DELETE FROM benchmark_records")
            conn.execute("DELETE FROM benchmark_record_embeddings")
        records = sorted(self.records_dir.glob(f"**/{BENCHMARK_RECORD_NAME}"))
        for record_path in records:
            self.upsert_record(record_path)
        return len(records)

    def search_records(self, filters: BenchmarkResultSearchFilter) -> list[dict[str, object]]:
        rows = self._structured_rows(filters)
        if not rows:
            return []
        query = (filters.query or "").strip()
        if not query:
            return rows[: max(1, filters.limit)]
        semantic_scores = self._semantic_scores(query=query, rows=rows)
        query_tokens = _tokenize(query)
        ranked: list[tuple[float, dict[str, object]]] = []
        for row in rows:
            record_id = str(row.get("record_id", "")).strip()
            searchable = str(row.get("canonical_text", "")).casefold()
            text_score = float(sum(token in searchable for token in query_tokens))
            semantic_score = float(semantic_scores.get(record_id, 0.0))
            if text_score <= 0 and semantic_score <= 0:
                continue
            ranked.append((((semantic_score * 100.0) + text_score), row))
        ranked.sort(
            key=lambda item: (
                -item[0],
                str(item[1].get("updated_at", "")),
                str(item[1].get("record_id", "")),
            )
        )
        return [item[1] for item in ranked[: max(1, filters.limit)]]

    def _structured_rows(self, filters: BenchmarkResultSearchFilter) -> list[dict[str, object]]:
        where = ["1=1"]
        params: list[object] = []
        if filters.repo:
            where.append("repo = ?")
            params.append(filters.repo)
        if filters.operator_id:
            where.append("operator_id = ?")
            params.append(filters.operator_id)
        if filters.dataset_key:
            where.append("dataset_key = ?")
            params.append(filters.dataset_key)
        if filters.workflow_signature:
            where.append("workflow_signature = ?")
            params.append(filters.workflow_signature)
        if filters.input_signature:
            where.append("input_signature = ?")
            params.append(filters.input_signature)
        if filters.success_only:
            where.append("success = 1")
        params.append(max(50, filters.limit * 8))
        with self._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT
                    record_id, repo, operator_id, dataset_key, workflow_signature,
                    input_signature, success, returncode, run_id, run_dir, case_dir,
                    workflow_path, inputs_json_path, status_path, wdl_status_path,
                    result_manifest_path, analysis_path, canonical_text, record_path,
                    updated_at
                FROM benchmark_records
                WHERE {" AND ".join(where)}
                ORDER BY updated_at DESC, record_id ASC
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
            query_vector, model_name = _embed_query(query)
        except Exception:
            return {}
        if not query_vector or not model_name:
            return {}
        row_ids = [str(row.get("record_id", "")).strip() for row in rows if str(row.get("record_id", "")).strip()]
        if not row_ids:
            return {}
        placeholders = ", ".join("?" for _ in row_ids)
        with self._connect() as conn:
            stored = conn.execute(
                f"""
                SELECT record_id, model, vector_json
                FROM benchmark_record_embeddings
                WHERE record_id IN ({placeholders})
                """,
                row_ids,
            ).fetchall()
        scores: dict[str, float] = {}
        for record_id, stored_model, vector_json in stored:
            if str(stored_model) != model_name:
                continue
            try:
                vector = json.loads(str(vector_json))
            except json.JSONDecodeError:
                continue
            if not isinstance(vector, list) or not vector:
                continue
            similarity = _cosine_similarity(query_vector, [float(item) for item in vector])
            if similarity > 0:
                scores[str(record_id)] = similarity
        return scores

    def _materialize_record_embedding(
        self,
        *,
        normalized: dict[str, object],
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
            ):
                return existing
        try:
            vectors, model_name = _embed_documents([source_text])
        except Exception:
            return None
        if not vectors or not model_name:
            return None
        payload = {
            "schema_version": SCHEMA_VERSION,
            "record_id": normalized["record_id"],
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
                CREATE TABLE IF NOT EXISTS benchmark_records (
                    record_id TEXT PRIMARY KEY,
                    repo TEXT NOT NULL,
                    operator_id TEXT NOT NULL,
                    dataset_key TEXT NOT NULL,
                    workflow_signature TEXT NOT NULL,
                    input_signature TEXT NOT NULL,
                    success INTEGER NOT NULL,
                    returncode INTEGER,
                    run_id TEXT NOT NULL,
                    run_dir TEXT NOT NULL,
                    case_dir TEXT NOT NULL,
                    workflow_path TEXT NOT NULL,
                    inputs_json_path TEXT NOT NULL,
                    status_path TEXT NOT NULL,
                    wdl_status_path TEXT NOT NULL,
                    result_manifest_path TEXT NOT NULL,
                    analysis_path TEXT NOT NULL,
                    canonical_text TEXT NOT NULL,
                    record_path TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS benchmark_record_embeddings (
                    record_id TEXT PRIMARY KEY,
                    model TEXT NOT NULL,
                    vector_json TEXT NOT NULL,
                    embedding_path TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_benchmark_records_repo ON benchmark_records(repo)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_benchmark_records_operator ON benchmark_records(operator_id)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_benchmark_records_dataset ON benchmark_records(dataset_key)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_benchmark_records_success ON benchmark_records(success)"
            )


def _default_record_id(record: dict[str, object]) -> str:
    repo = str(record.get("repo", "unknown")).strip() or "unknown"
    run_id = str(record.get("run_id", "unknown-run")).strip() or "unknown-run"
    return f"benchmark-result:{repo}:{run_id}"


def _normalize_record(
    *,
    payload: dict[str, object],
    record_path: Path,
) -> dict[str, object]:
    repo = str(payload.get("repo", "")).strip() or "unknown"
    run_id = str(payload.get("run_id", "")).strip() or record_path.parent.name
    return {
        "record_id": str(payload.get("record_id") or _default_record_id(payload)),
        "repo": repo,
        "operator_id": str(payload.get("operator_id", "")).strip(),
        "dataset_key": str(payload.get("dataset_key", "")).strip(),
        "workflow_signature": str(payload.get("workflow_signature", "")).strip(),
        "input_signature": str(payload.get("input_signature", "")).strip(),
        "success": bool(payload.get("success")),
        "returncode": _int_or_none(payload.get("returncode")),
        "run_id": run_id,
        "run_dir": str(payload.get("run_dir", "")).strip(),
        "case_dir": str(payload.get("case_dir", "")).strip(),
        "workflow_path": str(payload.get("workflow_path", "")).strip(),
        "inputs_json_path": str(payload.get("inputs_json_path", "")).strip(),
        "status_path": str(payload.get("status_path", "")).strip(),
        "wdl_status_path": str(payload.get("wdl_status_path", "")).strip(),
        "result_manifest_path": str(payload.get("result_manifest_path", "")).strip(),
        "analysis_path": str(payload.get("analysis_path", "")).strip(),
        "canonical_text": str(payload.get("canonical_text", "")).strip(),
        "updated_at": str(payload.get("updated_at", "")).strip() or _utc_now(),
    }


def _row_to_result(row: tuple[object, ...]) -> dict[str, object]:
    return {
        "record_id": str(row[0]),
        "repo": str(row[1]),
        "operator_id": str(row[2]),
        "dataset_key": str(row[3]),
        "workflow_signature": str(row[4]),
        "input_signature": str(row[5]),
        "success": bool(row[6]),
        "returncode": _int_or_none(row[7]),
        "run_id": str(row[8]),
        "run_dir": str(row[9]),
        "case_dir": str(row[10]),
        "workflow_path": str(row[11]),
        "inputs_json_path": str(row[12]),
        "status_path": str(row[13]),
        "wdl_status_path": str(row[14]),
        "result_manifest_path": str(row[15]),
        "analysis_path": str(row[16]),
        "canonical_text": str(row[17]),
        "record_path": str(row[18]),
        "updated_at": str(row[19]),
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


def _tokenize(text: str) -> list[str]:
    import re

    return [
        token
        for token in re.split(r"[^0-9A-Za-z\u4e00-\u9fff]+", text.casefold())
        if token and len(token) > 1
    ]
