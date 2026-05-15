"""Manifest-first operator product store with a rebuildable SQLite index."""
# ruff: noqa: DOC201, DOC501

from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

MANIFEST_NAME = "operator_product.json"
SCHEMA_VERSION = "0.1"


@dataclass(frozen=True, slots=True)
class OperatorSearchFilter:
    """Structured filter for local operator lookup."""

    input_media_type: str | None = None
    output_media_type: str | None = None
    metric_name: str | None = None
    status: str | None = None
    tag: str | None = None
    limit: int = 50


class OperatorStore:
    """Store heavy operator artifacts as files and query lightweight metadata."""

    def __init__(self, root: Path) -> None:
        """Create or open an operator store rooted at ``root``."""
        self.root = root
        self.objects_dir = root / "objects"
        self.db_path = root / "index.sqlite"
        self.root.mkdir(parents=True, exist_ok=True)
        self.objects_dir.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def product_dir(self, *, family: str, name: str, version: str) -> Path:
        """Return the canonical object directory for one operator product."""
        return (
            self.objects_dir
            / _safe_path_part(family)
            / _safe_path_part(name)
            / _safe_path_part(version)
        )

    def write_manifest(
        self,
        manifest: dict[str, object],
        *,
        product_dir: Path | None = None,
    ) -> Path:
        """Write one product manifest and upsert its SQLite index rows."""
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
        """Load one manifest file into the SQLite query index."""
        payload = _read_json(manifest_path)
        operator_id = str(payload.get("product_id", "")).strip()
        if not operator_id:
            msg = f"Operator manifest is missing product_id: {manifest_path}"
            raise ValueError(msg)
        with self._connect() as conn:
            conn.execute("BEGIN")
            delete_params = (operator_id,)
            conn.execute("DELETE FROM operator_io WHERE operator_id = ?", delete_params)
            conn.execute(
                "DELETE FROM operator_runtime WHERE operator_id = ?",
                delete_params,
            )
            conn.execute(
                "DELETE FROM operator_metrics WHERE operator_id = ?",
                delete_params,
            )
            conn.execute(
                "DELETE FROM operator_validation WHERE operator_id = ?",
                delete_params,
            )
            conn.execute(
                "DELETE FROM operator_tags WHERE operator_id = ?",
                delete_params,
            )
            conn.execute(
                """
                INSERT OR REPLACE INTO operators
                (id, name, family, version, source_repo, source_commit, manifest_path,
                 status, created_at, updated_at, searchable_text)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    operator_id,
                    str(payload.get("name", "")),
                    str(payload.get("family", "")),
                    str(payload.get("version", "")),
                    _nested_str(payload, "source", "repo_url"),
                    _nested_str(payload, "source", "commit"),
                    str(manifest_path),
                    str(payload.get("status", "")),
                    str(payload.get("created_at", payload.get("updated_at", ""))),
                    str(payload.get("updated_at", "")),
                    _searchable_text(payload),
                ),
            )
            for item in _list_of_dicts(payload.get("inputs")):
                conn.execute(
                    """
                    INSERT INTO operator_io
                    (operator_id, direction, media_type, schema_path, required, name)
                    VALUES (?, 'input', ?, ?, ?, ?)
                    """,
                    (
                        operator_id,
                        str(item.get("media_type", "")),
                        str(item.get("schema_path", "")),
                        1 if item.get("required", True) else 0,
                        str(item.get("name", "")),
                    ),
                )
            for item in _list_of_dicts(payload.get("outputs")):
                conn.execute(
                    """
                    INSERT INTO operator_io
                    (operator_id, direction, media_type, schema_path, required, name)
                    VALUES (?, 'output', ?, ?, ?, ?)
                    """,
                    (
                        operator_id,
                        str(item.get("media_type", "")),
                        str(item.get("schema_path", "")),
                        1 if item.get("required", False) else 0,
                        str(item.get("name", "")),
                    ),
                )
            runtime = payload.get("runtime")
            if isinstance(runtime, dict):
                conn.execute(
                    """
                    INSERT INTO operator_runtime
                    (operator_id, backend, image_ref, entrypoint, workflow_path)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        operator_id,
                        str(runtime.get("backend", "")),
                        str(runtime.get("image_ref", "")),
                        str(runtime.get("entrypoint", "")),
                        str(runtime.get("workflow_path", "")),
                    ),
                )
            for item in _list_of_dicts(payload.get("metrics")):
                conn.execute(
                    """
                    INSERT INTO operator_metrics
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
            validation = payload.get("validation")
            if isinstance(validation, dict):
                conn.execute(
                    """
                    INSERT INTO operator_validation
                    (operator_id, validation_id, status, dataset_id, run_dir,
                     summary, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        operator_id,
                        str(validation.get("validation_id", "")),
                        str(validation.get("status", "")),
                        str(validation.get("dataset_id", "")),
                        str(validation.get("run_dir", "")),
                        str(validation.get("summary", "")),
                        str(validation.get("created_at", "")),
                    ),
                )
            for tag in payload.get("tags", []):
                if isinstance(tag, str) and tag.strip():
                    conn.execute(
                        "INSERT INTO operator_tags (operator_id, tag) VALUES (?, ?)",
                        (operator_id, tag.strip()),
                    )
            conn.commit()

    def rebuild(self) -> int:
        """Rebuild the SQLite index from all file manifests."""
        manifests = sorted(self.objects_dir.glob(f"**/{MANIFEST_NAME}"))
        with self._connect() as conn:
            conn.execute("DELETE FROM operators")
            conn.execute("DELETE FROM operator_io")
            conn.execute("DELETE FROM operator_runtime")
            conn.execute("DELETE FROM operator_metrics")
            conn.execute("DELETE FROM operator_validation")
            conn.execute("DELETE FROM operator_tags")
            conn.execute("DELETE FROM operator_edges")
        for manifest_path in manifests:
            self.upsert_manifest(manifest_path)
        return len(manifests)

    def search(self, filters: OperatorSearchFilter) -> list[dict[str, object]]:
        """Search indexed operators using structured metadata filters."""
        where = ["1 = 1"]
        params: list[object] = []
        if filters.status:
            where.append("o.status = ?")
            params.append(filters.status)
        if filters.input_media_type:
            where.append(
                """
                EXISTS (
                  SELECT 1 FROM operator_io io
                  WHERE io.operator_id = o.id
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
                  SELECT 1 FROM operator_io io
                  WHERE io.operator_id = o.id
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
                  SELECT 1 FROM operator_metrics m
                  WHERE m.operator_id = o.id
                    AND m.metric_name = ?
                )
                """
            )
            params.append(filters.metric_name)
        if filters.tag:
            where.append(
                """
                EXISTS (
                  SELECT 1 FROM operator_tags t
                  WHERE t.operator_id = o.id
                    AND t.tag = ?
                )
                """
            )
            params.append(filters.tag)
        params.append(max(1, filters.limit))
        where_clause = " AND ".join(where)
        with self._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT o.id, o.name, o.family, o.version, o.status, o.manifest_path
                FROM operators o
                WHERE {where_clause}
                ORDER BY o.updated_at DESC, o.id ASC
                LIMIT ?
                """,  # noqa: S608 - where_clause is assembled from fixed snippets.
                params,
            ).fetchall()
        return [
            {
                "id": row[0],
                "name": row[1],
                "family": row[2],
                "version": row[3],
                "status": row[4],
                "manifest_path": row[5],
            }
            for row in rows
        ]

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path)

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS operators (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    family TEXT NOT NULL,
                    version TEXT NOT NULL,
                    source_repo TEXT NOT NULL,
                    source_commit TEXT NOT NULL,
                    manifest_path TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    searchable_text TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS operator_io (
                    operator_id TEXT NOT NULL,
                    direction TEXT NOT NULL,
                    media_type TEXT NOT NULL,
                    schema_path TEXT NOT NULL,
                    required INTEGER NOT NULL,
                    name TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS operator_runtime (
                    operator_id TEXT PRIMARY KEY,
                    backend TEXT NOT NULL,
                    image_ref TEXT NOT NULL,
                    entrypoint TEXT NOT NULL,
                    workflow_path TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS operator_metrics (
                    operator_id TEXT NOT NULL,
                    metric_name TEXT NOT NULL,
                    metric_type TEXT NOT NULL,
                    description TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS operator_validation (
                    operator_id TEXT NOT NULL,
                    validation_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    dataset_id TEXT NOT NULL,
                    run_dir TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS operator_tags (
                    operator_id TEXT NOT NULL,
                    tag TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS operator_edges (
                    upstream_id TEXT NOT NULL,
                    downstream_id TEXT NOT NULL,
                    relation TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_operator_io_lookup
                ON operator_io(direction, media_type)
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_operator_metrics_lookup
                ON operator_metrics(metric_name)
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_operator_tags_lookup
                ON operator_tags(tag)
                """
            )


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
        "name": name,
        "family": "benchmark",
        "version": version,
        "status": status,
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
    return {
        "product_id": product_id,
        "name": name,
        "family": "github2workspace",
        "version": version,
        "status": status,
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
            "workflow_path": str(wdl_path) if wdl_path.exists() else "",
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
            "wdl": str(wdl_path) if wdl_path.exists() else "",
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


def _benchmark_output_items(
    case_manifest: dict[str, object],
) -> list[dict[str, object]]:
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


def _nested_str(payload: dict[str, object], parent: str, key: str) -> str:
    item = payload.get(parent)
    if not isinstance(item, dict):
        return ""
    value = item.get(key)
    return "" if value is None else str(value)


def _list_of_dicts(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _searchable_text(payload: dict[str, object]) -> str:
    parts = [
        str(payload.get("product_id", "")),
        str(payload.get("name", "")),
        str(payload.get("family", "")),
        str(payload.get("status", "")),
        json.dumps(payload.get("source", {}), ensure_ascii=False, sort_keys=True),
        json.dumps(payload.get("runtime", {}), ensure_ascii=False, sort_keys=True),
        json.dumps(payload.get("tags", []), ensure_ascii=False, sort_keys=True),
    ]
    return "\n".join(parts)


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()
