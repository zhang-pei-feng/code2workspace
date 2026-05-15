"""Tests for the local operator product store."""

from __future__ import annotations

import json
from pathlib import Path  # noqa: TC003

from code2workspace_cli.operator_store import (
    OperatorSearchFilter,
    OperatorStore,
    build_benchmark_operator_manifest,
    build_github2workspace_operator_manifest,
)


def test_operator_store_writes_manifest_and_queries_index(tmp_path: Path) -> None:
    store = OperatorStore(tmp_path / "operator_store")
    run_dir = tmp_path / "workspace" / "orchestration_runs" / "run-1"
    case_dir = run_dir / "cases" / "spades"
    case_dir.mkdir(parents=True)
    manifest = build_benchmark_operator_manifest(
        product_id="benchmark:spades:run-1",
        name="spades",
        version="run-1",
        run_dir=run_dir,
        case_dir=case_dir,
        case_manifest={
            "repo_name": "spades",
            "dataset_key": "short-read-ecoli",
            "metric_keys": ["n50", "contig_count"],
            "expected_outputs": ["contigs.fasta"],
            "selected_input_files": {
                "reads_1": "/data/reads_1.fastq.gz",
                "reads_2": "/data/reads_2.fastq.gz",
            },
        },
        ready_payload={
            "ready": True,
            "runtime_image": "benchmark/spades:test",
            "wdl_path": "/work/spades.wdl",
            "inputs_json_path": "/work/input.json",
        },
        status="registered_ready",
        validation_summary="spades is registered and execution-ready.",
    )

    manifest_path = store.write_manifest(manifest)
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert payload["product_id"] == "benchmark:spades:run-1"
    assert payload["runtime"]["backend"] == "wdl"
    rows = store.search(
        OperatorSearchFilter(
            input_media_type="fastq",
            output_media_type="fasta",
            metric_name="n50",
            status="registered_ready",
        )
    )
    assert rows == [
        {
            "id": "benchmark:spades:run-1",
            "name": "spades",
            "family": "benchmark",
            "version": "run-1",
            "status": "registered_ready",
            "manifest_path": str(manifest_path),
        }
    ]


def test_operator_store_rebuilds_index_from_file_manifests(tmp_path: Path) -> None:
    store = OperatorStore(tmp_path / "operator_store")
    manifest = {
        "product_id": "benchmark:esm:run-1",
        "name": "esm",
        "family": "benchmark",
        "version": "run-1",
        "status": "blocked",
        "source": {"repo_url": "", "commit": ""},
        "runtime": {
            "backend": "wdl",
            "image_ref": "",
            "entrypoint": "",
            "workflow_path": "esm.wdl",
        },
        "inputs": [
            {
                "name": "input_json",
                "media_type": "json",
                "schema_path": "",
                "required": True,
            }
        ],
        "outputs": [],
        "metrics": [],
        "validation": {
            "validation_id": "benchmark-register:run-1:esm",
            "status": "blocked",
            "dataset_id": "immune-escape",
            "run_dir": "/tmp/run-1",
            "summary": "missing selected input file",
            "created_at": "2026-05-14T00:00:00+00:00",
        },
        "tags": ["benchmark", "blocked"],
    }
    manifest_path = store.write_manifest(manifest)
    store.db_path.unlink()
    rebuilt = OperatorStore(store.root)
    count = rebuilt.rebuild()

    assert count == 1
    rows = rebuilt.search(OperatorSearchFilter(status="blocked"))
    assert rows[0]["manifest_path"] == str(manifest_path)


def test_github2workspace_manifest_indexes_docker_product(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    docker_result = workspace / "results" / "docker_test" / "spades_test"
    docker_result.mkdir(parents=True)
    (workspace / "spades_Dockerfile").write_text(
        "FROM ubuntu:24.04\n",
        encoding="utf-8",
    )
    (workspace / "spades.wdl").write_text("version 1.0\n", encoding="utf-8")
    (docker_result / "contigs.fasta").write_text(">c1\nAAAA\n", encoding="utf-8")
    store = OperatorStore(tmp_path / "operator_store")

    manifest = build_github2workspace_operator_manifest(
        product_id="github2workspace:spades:run-1",
        name="spades",
        version="run-1",
        workspace_root=workspace,
        run_dir=workspace / "orchestration_runs" / "run-1",
        status="docker_validated",
        source_repo="https://github.com/ablab/spades",
        validation_summary="Docker succeeded; WDL partial.",
    )
    manifest_path = store.write_manifest(manifest)

    rows = store.search(
        OperatorSearchFilter(
            output_media_type="fasta",
            status="docker_validated",
            tag="github2workspace",
        )
    )
    assert rows[0]["id"] == "github2workspace:spades:run-1"
    assert rows[0]["manifest_path"] == str(manifest_path)


def test_github2workspace_manifest_marks_synthetic_input_tag(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    docker_result = workspace / "results" / "docker_test" / "canu_run"
    docker_result.mkdir(parents=True)
    wdl_result = workspace / "results" / "wdl_result"
    wdl_result.mkdir(parents=True)
    (workspace / "canu_Dockerfile").write_text("FROM ubuntu:22.04\n", encoding="utf-8")
    (workspace / "canu.wdl").write_text("version 1.0\n", encoding="utf-8")
    (workspace / "inputs.json").write_text(
        json.dumps({"canu_workflow.reads": str(workspace / "results" / "wdl_file" / "toy_reads.fastq")}),
        encoding="utf-8",
    )
    (wdl_result / "outputs.json").write_text("{}", encoding="utf-8")

    manifest = build_github2workspace_operator_manifest(
        product_id="github2workspace:canu:run-1",
        name="canu",
        version="run-1",
        workspace_root=workspace,
        run_dir=workspace / "orchestration_runs" / "run-1",
        status="partial",
        source_repo="https://github.com/marbl/canu",
        validation_summary="Synthetic inputs were used, so this is partial.",
    )

    assert "synthetic-inputs" in manifest["tags"]
