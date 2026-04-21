#!/usr/bin/env python3
"""Front-door orchestration helpers for local benchmark workflow tasks."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SHARED_HELPER_DIR = Path(__file__).resolve().parents[2] / "_shared-superagent-helpers" / "scripts"
if str(SHARED_HELPER_DIR) not in sys.path:
    sys.path.insert(0, str(SHARED_HELPER_DIR))

from common import create_skill_run_dir, ensure_dir, read_json, write_json, write_text


PHASE_ORDER = [
    "plan",
    "prebuild",
    "dataset_prep",
    "execution_ready",
    "benchmark_run",
    "analysis",
    "summary",
]

FAMILY_METRICS = {
    "short-read-assembly": ["contig_count", "n50", "assembly_size"],
    "long-read-assembly": ["contig_count", "n50", "assembly_size"],
    "rna-seq-transcriptome": ["transcript_count", "trinity_fasta_size"],
    "viral-short-read-pipeline": ["consensus_fasta", "variant_outputs", "coverage_summary"],
    "viral-ont-amplicon": ["consensus_fasta", "variant_outputs", "coverage_summary"],
}


@dataclass(frozen=True)
class DatasetFile:
    logical_name: str
    uri: str
    filename: str


@dataclass(frozen=True)
class DatasetSpec:
    key: str
    dataset_id: str
    family: str
    description: str
    source: str
    source_urls: tuple[str, ...]
    shared_between: tuple[str, ...]
    files: tuple[DatasetFile, ...]
    local_candidates: tuple[str, ...] = ()
    fallback_urls: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["files"] = [asdict(item) for item in self.files]
        return payload


@dataclass(frozen=True)
class RepoCase:
    repo_name: str
    repo_url: str
    family: str
    dataset_key: str
    image_tag: str
    repo_native_entry: str
    wdl_workflow_name: str
    expected_outputs: tuple[str, ...]
    constraints: tuple[str, ...]
    case_dir: str | None = None
    wdl_path: str | None = None
    inputs_path: str | None = None
    dockerfile_path: str | None = None
    dockerfile_candidates: tuple[str, ...] = ()
    wdl_candidates: tuple[str, ...] = ()
    input_json_candidates: tuple[str, ...] = ()
    repo_native_command_candidates: tuple[str, ...] = ()
    local_result_candidates: tuple[str, ...] = ()

    @property
    def metric_keys(self) -> list[str]:
        return FAMILY_METRICS[self.family]

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["metric_keys"] = self.metric_keys
        return payload


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[4]


def _catalog_path() -> Path:
    return _repo_root() / "experiments" / "benchmark" / "datasets" / "benchmark_catalog.json"


def _load_catalog() -> tuple[dict[str, Any], dict[str, DatasetSpec], dict[str, RepoCase]]:
    raw = json.loads(_catalog_path().read_text(encoding="utf-8"))
    datasets = {
        key: DatasetSpec(
            key=key,
            dataset_id=str(payload["dataset_id"]),
            family=str(payload["family"]),
            description=str(payload["description"]),
            source=str(payload["source"]),
            source_urls=tuple(str(item) for item in payload.get("source_urls", [])),
            shared_between=tuple(str(item) for item in payload.get("shared_between", [])),
            files=tuple(
                DatasetFile(
                    logical_name=str(item["logical_name"]),
                    uri=str(item["uri"]),
                    filename=str(item["filename"]),
                )
                for item in payload.get("files", [])
            ),
            local_candidates=tuple(str(item) for item in payload.get("local_candidates", [])),
            fallback_urls=tuple(str(item) for item in payload.get("fallback_urls", [])),
        )
        for key, payload in raw["datasets"].items()
    }
    cases = {
        name: RepoCase(
            repo_name=name,
            repo_url=str(payload["repo_url"]),
            family=str(payload["family"]),
            dataset_key=str(payload["dataset_key"]),
            image_tag=str(payload["image_tag"]),
            repo_native_entry=str(payload["repo_native_entry"]),
            wdl_workflow_name=str(payload["wdl_workflow_name"]),
            expected_outputs=tuple(str(item) for item in payload.get("expected_outputs", [])),
            constraints=tuple(str(item) for item in payload.get("constraints", [])),
            case_dir=str(payload["case_dir"]) if payload.get("case_dir") else None,
            wdl_path=str(payload["wdl_path"]) if payload.get("wdl_path") else None,
            inputs_path=str(payload["inputs_path"]) if payload.get("inputs_path") else None,
            dockerfile_path=str(payload["dockerfile_path"]) if payload.get("dockerfile_path") else None,
            dockerfile_candidates=tuple(str(item) for item in payload.get("dockerfile_candidates", [])),
            wdl_candidates=tuple(str(item) for item in payload.get("wdl_candidates", [])),
            input_json_candidates=tuple(str(item) for item in payload.get("input_json_candidates", [])),
            repo_native_command_candidates=tuple(str(item) for item in payload.get("repo_native_command_candidates", [])),
            local_result_candidates=tuple(str(item) for item in payload.get("local_result_candidates", [])),
        )
        for name, payload in raw["repo_cases"].items()
    }
    return raw, datasets, cases


RAW_CATALOG, DATASETS, CASES = _load_catalog()


def _dataset_root() -> Path:
    return _repo_root() / RAW_CATALOG["dataset_root"]


def _downloads_root() -> Path:
    return _repo_root() / RAW_CATALOG["downloads_root"]


def _root_manifest_path(run_dir: Path) -> Path:
    return run_dir / "manifest.json"


def _cases_root(run_dir: Path) -> Path:
    return run_dir / "cases"


def _case_dir(run_dir: Path, repo: str) -> Path:
    return _cases_root(run_dir) / repo


def _case_manifest_path(run_dir: Path, repo: str) -> Path:
    return _case_dir(run_dir, repo) / "manifest.json"


def _load_root_manifest(run_dir: Path) -> dict[str, Any]:
    return read_json(_root_manifest_path(run_dir))


def _load_case_manifest(run_dir: Path, repo: str) -> dict[str, Any]:
    return read_json(_case_manifest_path(run_dir, repo))


def _save_case_manifest(run_dir: Path, repo: str, payload: dict[str, Any]) -> None:
    write_json(_case_manifest_path(run_dir, repo), payload)


def _phase_paths(case_dir: Path) -> dict[str, str]:
    return {
        "docker_dir": str(case_dir / "docker"),
        "wdl_dir": str(case_dir / "wdl"),
        "run_dir": str(case_dir / "run"),
    }


def _dataset_download_dir(dataset_key: str) -> Path:
    return _downloads_root() / dataset_key


def _resolve_repo_path(raw: str) -> Path:
    candidate = Path(raw)
    if candidate.is_absolute():
        return candidate
    return _repo_root() / raw


def _first_existing(paths: tuple[str, ...]) -> Path | None:
    for item in paths:
        candidate = _resolve_repo_path(item)
        if candidate.exists():
            return candidate
    return None


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _log_tail(path: Path, *, max_chars: int = 4000) -> str:
    if not path.exists():
        return ""
    text = path.read_text(encoding="utf-8", errors="replace")
    return text[-max_chars:]


def _initial_case_manifest(case: RepoCase, run_dir: Path) -> dict[str, Any]:
    case_dir = _case_dir(run_dir, case.repo_name)
    return {
        **case.to_dict(),
        "case_dir": str(case_dir),
        "paths": _phase_paths(case_dir),
        "phase_status": {
            "plan": "completed",
            "prebuild": "pending",
            "dataset_prep": "pending",
            "execution_ready": "pending",
            "benchmark_run": "pending",
            "analysis": "pending",
            "summary": "pending",
        },
    }


def _write_case_readme(case_dir: Path, payload: dict[str, Any], dataset: DatasetSpec) -> None:
    lines = [
        "# Benchmark Case",
        "",
        f"- repo: `{payload['repo_name']}`",
        f"- repo_url: `{payload['repo_url']}`",
        f"- family: `{payload['family']}`",
        f"- dataset_key: `{payload['dataset_key']}`",
        f"- image_tag: `{payload['image_tag']}`",
        f"- dataset_download_dir: `{_dataset_download_dir(dataset.key)}`",
        "",
        "## Expected Outputs",
        "",
    ]
    lines.extend(f"- `{item}`" for item in payload["expected_outputs"])
    lines.extend(["", "## Metrics", ""])
    lines.extend(f"- `{item}`" for item in payload["metric_keys"])
    write_text(case_dir / "README.md", "\n".join(lines) + "\n")


def _root_plan_payload(task: str, run_dir: Path) -> dict[str, Any]:
    return {
        "task": task,
        "run_dir": str(run_dir),
        "phase_order": PHASE_ORDER,
        "catalog_file": str(_catalog_path()),
        "dataset_root": str(_dataset_root()),
        "downloads_root": str(_downloads_root()),
        "case_order": list(CASES),
        "datasets": {key: spec.to_dict() for key, spec in DATASETS.items()},
        "cases": {name: case.to_dict() for name, case in CASES.items()},
    }


def _case_summary(case_dir: Path) -> dict[str, Any]:
    docker_status = read_json(case_dir / "docker" / "status.json") if (case_dir / "docker" / "status.json").exists() else {}
    run_status = read_json(case_dir / "run" / "status.json") if (case_dir / "run" / "status.json").exists() else {}
    wdl_status = read_json(case_dir / "wdl" / "status.json") if (case_dir / "wdl" / "status.json").exists() else {}
    run_artifacts = [str(item) for item in run_status.get("output_artifacts", [])]
    wdl_artifacts = [str(item) for item in wdl_status.get("output_artifacts", [])]
    image_build_success = bool(docker_status.get("success"))
    benchmark_run_success = bool(run_status.get("success"))
    wdl_success = bool(wdl_status.get("success"))
    completed = image_build_success and benchmark_run_success and wdl_success and bool(run_artifacts or wdl_artifacts)
    return {
        "image_build_success": image_build_success,
        "benchmark_run_success": benchmark_run_success,
        "wdl_success": wdl_success,
        "completed": completed,
        "artifacts": run_artifacts + wdl_artifacts,
    }


def _write_agent_task(case_dir: Path, case: RepoCase, dataset: DatasetSpec) -> None:
    lines = [
        "# Agent Benchmark Task",
        "",
        "This task should be executed by the code2workspace agent with minimal human intervention.",
        "",
        f"- repo: `{case.repo_name}`",
        f"- repo_url: `{case.repo_url}`",
        f"- dataset_root: `{_dataset_root()}`",
        f"- downloads_root: `{_downloads_root()}`",
        f"- dataset_key: `{dataset.key}`",
        f"- candidate_download_dir: `{_dataset_download_dir(dataset.key)}`",
        f"- repo_native_entry: `{case.repo_native_entry}`",
        f"- wdl_workflow_name: `{case.wdl_workflow_name}`",
        "",
        "## Rules",
        "",
        "1. Inspect the dataset catalog and dataset directory before inventing inputs.",
        "2. Prefer an already available file under the unified dataset directory or the listed local candidates.",
        "3. If the unified dataset directory is empty for this dataset, choose the best official local candidate or download from the listed source URLs.",
        "4. Run the shortest honest repo-native validation path first.",
        "5. Then run the matching local WDL path with `java -jar /mnt/data2/bin/cromwell.jar run`.",
        "6. Ensure the WDL runtime points at the local image tag selected for this case.",
        "7. Save all benchmark outputs under this case directory.",
        "8. The supervisor may monitor progress but should not perform the benchmark for you.",
        "",
        "## Dataset Sources",
        "",
    ]
    lines.extend(f"- `{item}`" for item in dataset.source_urls)
    if dataset.local_candidates:
        lines.extend(["", "## Local Candidates", ""])
        lines.extend(f"- `{item}`" for item in dataset.local_candidates)
    lines.extend(["", "## Constraints", ""])
    lines.extend(f"- {item}" for item in case.constraints)
    write_text(case_dir / "agent_task.md", "\n".join(lines) + "\n")
    write_json(
        case_dir / "agent_request.json",
        {
            "task_mode": "autonomous-benchmark",
            "repo_name": case.repo_name,
            "repo_url": case.repo_url,
            "dataset_key": dataset.key,
            "dataset_download_dir": str(_dataset_download_dir(dataset.key)),
            "repo_native_entry": case.repo_native_entry,
            "wdl_workflow_name": case.wdl_workflow_name,
            "expected_outputs": list(case.expected_outputs),
            "constraints": list(case.constraints),
        },
    )


def _select_dataset_files(dataset: DatasetSpec) -> dict[str, Any]:
    dataset_dir = ensure_dir(_dataset_download_dir(dataset.key))
    downloaded = {item.logical_name: str(dataset_dir / item.filename) for item in dataset.files if (dataset_dir / item.filename).exists()}
    if len(downloaded) == len(dataset.files):
        return {
            "selected_input_source": "downloads_root",
            "selected_input_files": downloaded,
            "selection_complete": True,
            "selection_reason": "All expected files are already present in the unified dataset directory.",
        }

    selected: dict[str, str] = {}
    existing_candidates = [str(_resolve_repo_path(item)) for item in dataset.local_candidates if _resolve_repo_path(item).exists()]
    for logical_name, candidate in zip((item.logical_name for item in dataset.files), existing_candidates, strict=False):
        selected[logical_name] = candidate
    return {
        "selected_input_source": "catalog.local_candidates" if selected else "catalog_only",
        "selected_input_files": selected,
        "selection_complete": len(selected) == len(dataset.files),
        "selection_reason": (
            "The unified dataset cache is empty for this dataset, so existing catalog-listed local candidates were selected."
            if selected
            else "No complete local candidate set was found, so the case keeps the target paths declared in the dataset manifest."
        ),
    }


def _write_dataset_selection(case_dir: Path, dataset: DatasetSpec) -> dict[str, Any]:
    selection = {
        "dataset_key": dataset.key,
        "dataset_download_dir": str(_dataset_download_dir(dataset.key)),
        **_select_dataset_files(dataset),
    }
    write_json(case_dir / "dataset_selection.json", selection)
    return selection


def _runtime_image_from_wdl(wdl_path: Path) -> str | None:
    text = wdl_path.read_text(encoding="utf-8")
    match = re.search(r'docker:\s*"([^"]+)"', text)
    return match.group(1) if match else None


def _build_input_mounts(input_files: dict[str, str]) -> tuple[list[str], dict[str, str]]:
    mounts: list[str] = []
    container_inputs: dict[str, str] = {}
    for logical_name, raw_path in input_files.items():
        resolved = Path(raw_path).resolve(strict=True)
        mounts.extend(["-v", f"{resolved.parent}:/inputs/{logical_name}:ro"])
        container_inputs[logical_name] = f"/inputs/{logical_name}/{resolved.name}"
    return mounts, container_inputs


def _replace_input_placeholders(command: str, container_inputs: dict[str, str]) -> str:
    rendered = command
    for logical_name, container_path in container_inputs.items():
        rendered = rendered.replace(f"<{logical_name}>", container_path)
    return rendered


def _default_repo_native_shell_command(case_manifest: dict[str, Any]) -> str:
    output_dir = "/work/repo_native_output"
    defaults = {
        "spades": "/opt/spades/bin/spades.py -1 <reads_1> -2 <reads_2> -t 2 -o /work/repo_native_output",
        "canu": (
            "canu -correct -p ecoli -d /work/repo_native_output genomeSize=4.8m "
            "useGrid=false maxThreads=4 maxMemory=16 stopOnLowCoverage=0 stopAfter=meryl -pacbio <reads>"
        ),
        "megahit": "megahit -1 <reads_1> -2 <reads_2> -o /work/repo_native_output -t 2",
        "Flye": "/opt/Flye/bin/flye --pacbio-raw <reads> --out-dir /work/repo_native_output",
        "trinityrnaseq": "Trinity --left <reads_1> --right <reads_2> --seqType fq --output /work/repo_native_output",
    }
    command = defaults.get(case_manifest["repo_name"], case_manifest["repo_native_entry"])
    command = command.replace(" -o out", f" -o {output_dir}")
    command = command.replace(" --out-dir out", f" --out-dir {output_dir}")
    command = command.replace(" -d run", f" -d {output_dir}")
    return command


def _build_repo_native_shell_command(
    *,
    image: str,
    shell_command: str,
    input_files: dict[str, str],
    work_dir: Path,
    entrypoint: str = "/bin/bash",
) -> list[str]:
    mount_args, container_inputs = _build_input_mounts(input_files)
    rendered_shell = _replace_input_placeholders(shell_command, container_inputs)
    return [
        "docker",
        "run",
        "--rm",
        "--user",
        f"{os.getuid()}:{os.getgid()}",
        *mount_args,
        "-v",
        f"{work_dir}:/work",
        "--entrypoint",
        entrypoint,
        image,
        "-lc",
        rendered_shell,
    ]


def _build_repo_native_exec_command(
    *,
    image: str,
    argv: list[str],
    input_files: dict[str, str],
    work_dir: Path,
) -> list[str]:
    mount_args, container_inputs = _build_input_mounts(input_files)
    rendered_argv = [_replace_input_placeholders(item, container_inputs) for item in argv]
    return [
        "docker",
        "run",
        "--rm",
        "--user",
        f"{os.getuid()}:{os.getgid()}",
        *mount_args,
        "-v",
        f"{work_dir}:/work",
        image,
        *rendered_argv,
    ]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _fasta_stats(path: Path) -> dict[str, Any]:
    lengths: list[int] = []
    current = 0
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            stripped = line.strip()
            if not stripped:
                continue
            if stripped.startswith(">"):
                if current:
                    lengths.append(current)
                current = 0
                continue
            current += len(stripped)
    if current:
        lengths.append(current)
    total = sum(lengths)
    ordered = sorted(lengths, reverse=True)
    running = 0
    n50 = 0
    half = total / 2 if total else 0
    for length in ordered:
        running += length
        if running >= half:
            n50 = length
            break
    return {
        "record_count": len(lengths),
        "assembly_size": total,
        "n50": n50,
    }


def _analysis_for_case(case_dir: Path, case_manifest: dict[str, Any]) -> dict[str, Any]:
    family = case_manifest["family"]
    artifact_paths: list[str] = []
    checksums: dict[str, str] = {}
    metrics: dict[str, Any] = {}

    run_status = read_json(case_dir / "run" / "status.json") if (case_dir / "run" / "status.json").exists() else {}
    wdl_status = read_json(case_dir / "wdl" / "status.json") if (case_dir / "wdl" / "status.json").exists() else {}
    existing_candidates = [_resolve_repo_path(item) for item in case_manifest.get("local_result_candidates", [])]
    expected = [case_dir / "wdl" / item for item in case_manifest.get("expected_outputs", [])]
    status_artifacts = [Path(item) for item in [*run_status.get("output_artifacts", []), *wdl_status.get("output_artifacts", [])]]
    for candidate in [*status_artifacts, *expected, *existing_candidates]:
        if candidate.exists() and candidate.is_file():
            candidate_str = str(candidate)
            if candidate_str in checksums:
                continue
            artifact_paths.append(candidate_str)
            checksums[candidate_str] = _sha256(candidate)

    if family in {"short-read-assembly", "long-read-assembly"}:
        fasta_candidate = next((Path(item) for item in artifact_paths if item.endswith((".fasta", ".fa"))), None)
        if fasta_candidate is not None:
            fasta = _fasta_stats(fasta_candidate)
            metrics["contig_count"] = fasta["record_count"]
            metrics["assembly_size"] = fasta["assembly_size"]
            metrics["n50"] = fasta["n50"]
    elif family == "rna-seq-transcriptome":
        trinity_fasta = next((Path(item) for item in artifact_paths if item.endswith("Trinity.fasta")), None)
        metrics["trinity_fasta_exists"] = trinity_fasta is not None
        if trinity_fasta is not None:
            fasta = _fasta_stats(trinity_fasta)
            metrics["transcript_count"] = fasta["record_count"]
            metrics["assembly_size"] = fasta["assembly_size"]
    elif family in {"viral-short-read-pipeline", "viral-ont-amplicon"}:
        metrics["consensus_exists"] = any(item.endswith(("consensus.fasta", "assembly.fasta")) for item in artifact_paths)
        metrics["variant_outputs_exist"] = any(item.endswith((".vcf", ".tsv", "snvs.vcf")) for item in artifact_paths)
        metrics["coverage_summary_exists"] = any("coverage" in Path(item).name.lower() for item in artifact_paths)

    return {
        "family": family,
        "artifact_paths": artifact_paths,
        "artifact_checksums": checksums,
        "metrics": metrics,
    }


def _run_build_command(command: list[str], *, cwd: Path, log_path: Path, timeout_seconds: int) -> dict[str, Any]:
    started_at = time.time()
    completed = subprocess.run(
        command,
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=timeout_seconds,
        check=False,
    )
    elapsed = round(time.time() - started_at, 3)
    log_path.write_text(completed.stdout + completed.stderr, encoding="utf-8")
    return {
        "attempted": True,
        "completed": True,
        "success": completed.returncode == 0,
        "returncode": completed.returncode,
        "elapsed_seconds": elapsed,
        "command": command,
        "log_path": str(log_path),
    }


def _run_logged_command(command: list[str], *, cwd: Path, log_path: Path, timeout_seconds: int) -> dict[str, Any]:
    started_at = _utc_now_iso()
    started_monotonic = time.time()
    with log_path.open("w", encoding="utf-8") as log_handle:
        try:
            completed = subprocess.run(
                command,
                cwd=cwd,
                stdout=log_handle,
                stderr=subprocess.STDOUT,
                text=True,
                timeout=timeout_seconds,
                check=False,
            )
            returncode = completed.returncode
            success = returncode == 0
            failure_reason = None if success else _log_tail(log_path)
        except subprocess.TimeoutExpired:
            returncode = None
            success = False
            failure_reason = f"Command timed out after {timeout_seconds} seconds.\n{_log_tail(log_path)}"
    return {
        "attempted": True,
        "completed": True,
        "success": success,
        "returncode": returncode,
        "started_at": started_at,
        "finished_at": _utc_now_iso(),
        "elapsed_seconds": round(time.time() - started_monotonic, 3),
        "command": command,
        "log_path": str(log_path),
        "failure_reason": failure_reason,
    }


def _collect_output_artifacts(output_dir: Path) -> list[str]:
    if not output_dir.exists():
        return []
    return sorted(str(path) for path in output_dir.rglob("*") if path.is_file())[:200]


def _preferred_image_ref(case_dir: Path, case_manifest: dict[str, Any]) -> str:
    def normalize(image_ref: str) -> str:
        if "@" in image_ref:
            return image_ref
        tail = image_ref.rsplit("/", 1)[-1]
        if ":" in tail:
            return image_ref
        return f"{image_ref}:latest"

    docker_request = case_dir / "docker" / "request.json"
    if docker_request.exists():
        payload = read_json(docker_request)
        image_tag = payload.get("image_tag")
        if image_tag:
            return normalize(str(image_tag))
    runtime_image = case_manifest.get("runtime_image")
    if runtime_image:
        return normalize(str(runtime_image))
    return normalize(str(case_manifest["image_tag"]))


def cmd_catalog_datasets(args: argparse.Namespace) -> int:
    payload = {
        "catalog_file": str(_catalog_path()),
        "dataset_root": str(_dataset_root()),
        "downloads_root": str(_downloads_root()),
        "dataset_count": len(DATASETS),
        "datasets": {key: spec.to_dict() for key, spec in DATASETS.items()},
        "repo_cases": {name: case.to_dict() for name, case in CASES.items()},
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def cmd_init(args: argparse.Namespace) -> int:
    run_dir = Path(args.output_dir) if args.output_dir else create_skill_run_dir("benchmark-workflow-orchestrator", "runs")
    ensure_dir(run_dir)
    ensure_dir(_cases_root(run_dir))
    ensure_dir(_dataset_root())
    ensure_dir(_downloads_root())
    ensure_dir(run_dir / "logs")
    root_payload = _root_plan_payload(args.task, run_dir)
    write_json(_root_manifest_path(run_dir), root_payload)
    write_json(run_dir / "benchmark_plan.json", root_payload)
    lines = [
        "# Benchmark Plan",
        "",
        f"- task: `{args.task}`",
        f"- run_dir: `{run_dir}`",
        f"- dataset_root: `{_dataset_root()}`",
        "",
        "## Repo Cases",
        "",
    ]
    for name, case in CASES.items():
        lines.append(f"- `{name}` -> dataset `{case.dataset_key}` / family `{case.family}`")
        case_dir = _case_dir(run_dir, name)
        ensure_dir(case_dir / "docker")
        ensure_dir(case_dir / "wdl")
        ensure_dir(case_dir / "run")
        manifest = _initial_case_manifest(case, run_dir)
        _save_case_manifest(run_dir, name, manifest)
        _write_case_readme(case_dir, manifest, DATASETS[case.dataset_key])
    write_text(run_dir / "benchmark_plan.md", "\n".join(lines) + "\n")
    print(json.dumps({"run_dir": str(run_dir), "case_count": len(CASES), "case_order": list(CASES)}, ensure_ascii=False, indent=2))
    return 0


def cmd_resolve_datasets(args: argparse.Namespace) -> int:
    run_dir = Path(args.run_dir).resolve()
    manifest = _load_root_manifest(run_dir)
    payload = {
        "run_dir": str(run_dir),
        "catalog_file": str(_catalog_path()),
        "dataset_root": str(_dataset_root()),
        "downloads_root": str(_downloads_root()),
        "dataset_count": len(DATASETS),
        "datasets": {key: spec.to_dict() for key, spec in DATASETS.items()},
        "repo_to_dataset": {repo: CASES[repo].dataset_key for repo in manifest["case_order"]},
    }
    write_json(run_dir / "dataset_resolution.json", payload)
    lines = [
        "# Dataset Resolution",
        "",
        f"- run_dir: `{run_dir}`",
        f"- dataset_root: `{_dataset_root()}`",
        f"- dataset_count: `{len(DATASETS)}`",
        "",
        "## Mapping",
        "",
    ]
    lines.extend(f"- `{repo}` -> `{dataset_key}`" for repo, dataset_key in payload["repo_to_dataset"].items())
    write_text(run_dir / "dataset_resolution.md", "\n".join(lines) + "\n")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def cmd_prepare_case(args: argparse.Namespace) -> int:
    run_dir = Path(args.run_dir).resolve()
    repo = args.repo
    case_manifest = _load_case_manifest(run_dir, repo)
    case = CASES[repo]
    dataset = DATASETS[case.dataset_key]
    dataset_dir = ensure_dir(_dataset_download_dir(dataset.key))
    case_dir = _case_dir(run_dir, repo)
    source_wdl_path = _resolve_repo_path(case.wdl_path) if case.wdl_path else None
    source_inputs_path = _resolve_repo_path(case.inputs_path) if case.inputs_path else None
    dataset_manifest = {
        **dataset.to_dict(),
        "repo_name": repo,
        "catalog_file": str(_catalog_path()),
        "dataset_root": str(_dataset_root()),
        "downloads_root": str(_downloads_root()),
        "local_cache_dir": str(dataset_dir),
        "target_files": [
            {
                **asdict(item),
                "target_path": str(dataset_dir / item.filename),
            }
            for item in dataset.files
        ],
    }
    selection = _write_dataset_selection(case_dir, dataset)
    dataset_manifest.update(selection)
    write_json(case_dir / "dataset_manifest.json", dataset_manifest)
    if source_wdl_path is not None and source_wdl_path.exists():
        shutil.copy2(source_wdl_path, case_dir / "wdl" / source_wdl_path.name)
    if source_inputs_path is not None and source_inputs_path.exists():
        shutil.copy2(source_inputs_path, case_dir / "wdl" / "inputs.json")
    else:
        input_template = {
            "repo_name": repo,
            "dataset_key": dataset.key,
            "dataset_id": dataset.dataset_id,
            "dataset_root": str(_dataset_root()),
            "dataset_download_dir": str(dataset_dir),
            "repo_native_entry": case.repo_native_entry,
            "wdl_workflow_name": case.wdl_workflow_name,
            "input_files": selection["selected_input_files"] or {
                item.logical_name: str(dataset_dir / item.filename)
                for item in dataset.files
            },
            "expected_outputs": list(case.expected_outputs),
        }
        write_json(case_dir / "wdl" / "inputs.json", input_template)
    write_json(
        case_dir / "run" / "benchmark_request.json",
        {
            "repo_name": repo,
            "family": case.family,
            "repo_native_entry": case.repo_native_entry,
            "constraints": list(case.constraints),
            "autonomous_agent_expected": True,
        },
    )
    _write_agent_task(case_dir, case, dataset)
    case_manifest["phase_status"]["dataset_prep"] = "prepared"
    case_manifest["dataset_download_dir"] = str(dataset_dir)
    case_manifest["source_case_dir"] = str(_resolve_repo_path(case.case_dir)) if case.case_dir else None
    case_manifest["source_wdl_path"] = str(source_wdl_path) if source_wdl_path is not None else None
    case_manifest["source_inputs_path"] = str(source_inputs_path) if source_inputs_path is not None else None
    case_manifest["selected_input_source"] = selection["selected_input_source"]
    case_manifest["selected_input_files"] = selection["selected_input_files"]
    case_manifest["selection_reason"] = selection["selection_reason"]
    _save_case_manifest(run_dir, repo, case_manifest)
    print(json.dumps({"repo": repo, "dataset_key": dataset.key, "case_dir": str(case_dir)}, ensure_ascii=False, indent=2))
    return 0


def cmd_execution_ready(args: argparse.Namespace) -> int:
    run_dir = Path(args.run_dir).resolve()
    repo = args.repo
    case_manifest = _load_case_manifest(run_dir, repo)
    case = CASES[repo]
    dockerfile_path = _resolve_repo_path(case.dockerfile_path) if case.dockerfile_path else _first_existing(case.dockerfile_candidates)
    if dockerfile_path is not None and not dockerfile_path.exists():
        dockerfile_path = None
    wdl_path = _resolve_repo_path(case.wdl_path) if case.wdl_path else _first_existing(case.wdl_candidates)
    if wdl_path is not None and not wdl_path.exists():
        wdl_path = None
    input_json_path = _resolve_repo_path(case.inputs_path) if case.inputs_path else _first_existing(case.input_json_candidates)
    if input_json_path is not None and not input_json_path.exists():
        input_json_path = None
    local_result_candidates = [str(_resolve_repo_path(item)) for item in case.local_result_candidates if _resolve_repo_path(item).exists()]
    runtime_image = _runtime_image_from_wdl(wdl_path) if wdl_path is not None else case.image_tag
    payload = {
        "repo": repo,
        "dockerfile_path": None if dockerfile_path is None else str(dockerfile_path),
        "wdl_path": None if wdl_path is None else str(wdl_path),
        "inputs_json_path": None if input_json_path is None else str(input_json_path),
        "repo_native_command_candidates": list(case.repo_native_command_candidates),
        "local_result_candidates": local_result_candidates,
        "runtime_image": runtime_image,
        "ready": wdl_path is not None and input_json_path is not None and bool(runtime_image),
    }
    write_json(case_dir := _case_dir(run_dir, repo) / "execution_ready.json", payload)
    case_manifest["dockerfile_path"] = payload["dockerfile_path"]
    case_manifest["wdl_path"] = payload["wdl_path"]
    case_manifest["inputs_json_path"] = payload["inputs_json_path"]
    case_manifest["runtime_image"] = payload["runtime_image"]
    case_manifest["repo_native_command_candidates"] = payload["repo_native_command_candidates"]
    case_manifest["local_result_candidates"] = payload["local_result_candidates"]
    case_manifest["phase_status"]["execution_ready"] = "prepared" if payload["ready"] else "partial"
    _save_case_manifest(run_dir, repo, case_manifest)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def cmd_prebuild_image(args: argparse.Namespace) -> int:
    run_dir = Path(args.run_dir).resolve()
    repo = args.repo
    case_manifest = _load_case_manifest(run_dir, repo)
    docker_dir = _case_dir(run_dir, repo) / "docker"
    ensure_dir(docker_dir)
    dockerfile_path = Path(args.dockerfile_path).resolve() if args.dockerfile_path else None
    context_dir = Path(args.context_dir).resolve() if args.context_dir else (_repo_root() / ".workspaces" / "oneshot" / repo)
    image_tag = args.image_tag or case_manifest["image_tag"]
    request = {
        "repo": repo,
        "image_tag": image_tag,
        "dockerfile_path": None if dockerfile_path is None else str(dockerfile_path),
        "context_dir": str(context_dir),
        "build_command": args.build_command or [],
        "timeout_seconds": args.timeout_seconds,
    }
    write_json(docker_dir / "request.json", request)
    log_path = docker_dir / "build.log"
    if args.build_command:
        status = _run_build_command(args.build_command, cwd=context_dir, log_path=log_path, timeout_seconds=args.timeout_seconds)
    elif dockerfile_path is not None and dockerfile_path.exists():
        command = ["docker", "build", "-t", image_tag, "-f", str(dockerfile_path), str(context_dir)]
        status = _run_build_command(command, cwd=context_dir, log_path=log_path, timeout_seconds=args.timeout_seconds)
    else:
        status = {
            "attempted": False,
            "completed": False,
            "success": False,
            "returncode": None,
            "elapsed_seconds": 0.0,
            "command": [],
            "log_path": str(log_path),
            "reason": "No build command or Dockerfile path was provided.",
        }
        log_path.write_text("", encoding="utf-8")
    write_json(docker_dir / "status.json", status)
    case_manifest["phase_status"]["prebuild"] = "completed" if status["success"] else ("failed" if status["attempted"] else "pending")
    _save_case_manifest(run_dir, repo, case_manifest)
    print(json.dumps({"repo": repo, "image_tag": image_tag, **status}, ensure_ascii=False, indent=2))
    return 0


def cmd_run_repo_native(args: argparse.Namespace) -> int:
    run_dir = Path(args.run_dir).resolve()
    repo = args.repo
    case_manifest = _load_case_manifest(run_dir, repo)
    case_dir = _case_dir(run_dir, repo)
    run_dir_path = case_dir / "run"
    output_dir = run_dir_path / "repo_native_output"
    ensure_dir(run_dir_path)
    input_files = dict(case_manifest.get("selected_input_files") or {})
    if not input_files:
        raise SystemExit(f"No selected input files recorded for {repo}. Run prepare-case first.")

    if output_dir.exists():
        shutil.rmtree(output_dir)

    image = args.image or _preferred_image_ref(case_dir, case_manifest)
    shell_command = args.shell_command or _default_repo_native_shell_command(case_manifest)
    log_path = run_dir_path / "repo_native.log"
    if args.no_shell:
        command = _build_repo_native_exec_command(
            image=image,
            argv=shlex.split(shell_command),
            input_files=input_files,
            work_dir=run_dir_path,
        )
    else:
        command = _build_repo_native_shell_command(
            image=image,
            shell_command=f"rm -rf /work/repo_native_output && {shell_command}",
            input_files=input_files,
            work_dir=run_dir_path,
            entrypoint=args.entrypoint,
        )
    status = _run_logged_command(command, cwd=_repo_root(), log_path=log_path, timeout_seconds=args.timeout_seconds)
    status["output_dir"] = str(output_dir)
    status["input_source"] = case_manifest.get("selected_input_source")
    status["input_files"] = input_files
    status["output_artifacts"] = _collect_output_artifacts(output_dir)
    write_json(run_dir_path / "status.json", status)

    case_manifest["phase_status"]["benchmark_run"] = "completed" if status["success"] else "failed"
    case_manifest.setdefault("benchmark_notes", {})
    case_manifest["benchmark_notes"]["repo_native_status"] = str(run_dir_path / "status.json")
    case_manifest["benchmark_notes"]["repo_native_log"] = str(log_path)
    case_manifest["benchmark_notes"]["repo_native_failure_reason"] = status.get("failure_reason")
    _save_case_manifest(run_dir, repo, case_manifest)
    print(json.dumps({"repo": repo, **status}, ensure_ascii=False, indent=2))
    return 0


def cmd_analyze_case(args: argparse.Namespace) -> int:
    run_dir = Path(args.run_dir).resolve()
    repo = args.repo
    case_dir = _case_dir(run_dir, repo)
    case_manifest = _load_case_manifest(run_dir, repo)
    payload = _analysis_for_case(case_dir, case_manifest)
    write_json(case_dir / "analysis.json", payload)
    lines = [
        "# Benchmark Analysis",
        "",
        f"- repo: `{repo}`",
        f"- family: `{payload['family']}`",
        "",
        "## Metrics",
        "",
    ]
    for key, value in payload["metrics"].items():
        lines.append(f"- `{key}`: `{value}`")
    lines.extend(["", "## Artifacts", ""])
    lines.extend(f"- `{item}`" for item in payload["artifact_paths"] or ["(none)"])
    write_text(case_dir / "analysis.md", "\n".join(lines) + "\n")
    case_manifest["phase_status"]["analysis"] = "completed" if payload["artifact_paths"] else "empty"
    _save_case_manifest(run_dir, repo, case_manifest)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def cmd_summarize(args: argparse.Namespace) -> int:
    run_dir = Path(args.run_dir).resolve()
    manifest = _load_root_manifest(run_dir)
    rows = []
    for repo in manifest["case_order"]:
        case_manifest = _load_case_manifest(run_dir, repo)
        case_dir = _case_dir(run_dir, repo)
        analysis_payload = _analysis_for_case(case_dir, case_manifest)
        write_json(case_dir / "analysis.json", analysis_payload)
        write_text(
            case_dir / "analysis.md",
            "\n".join(
                [
                    "# Benchmark Analysis",
                    "",
                    f"- repo: `{repo}`",
                    f"- family: `{analysis_payload['family']}`",
                    "",
                    "## Metrics",
                    "",
                    *[f"- `{key}`: `{value}`" for key, value in analysis_payload["metrics"].items()],
                    "",
                    "## Artifacts",
                    "",
                    *([f"- `{item}`" for item in analysis_payload["artifact_paths"]] or ["- `(none)`"]),
                    "",
                ]
            ),
        )
        summary = _case_summary(case_dir)
        row = {
            "repo": repo,
            "family": case_manifest["family"],
            "dataset_key": case_manifest["dataset_key"],
            "dataset_download_dir": case_manifest.get("dataset_download_dir"),
            "analysis_status": case_manifest["phase_status"].get("analysis"),
            "image_build_success": summary["image_build_success"],
            "benchmark_run_success": summary["benchmark_run_success"],
            "wdl_success": summary["wdl_success"],
            "completed": summary["completed"],
            "metric_keys": case_manifest["metric_keys"],
            "artifact_paths": analysis_payload["artifact_paths"] or summary["artifacts"],
            "artifact_checksums": analysis_payload["artifact_checksums"],
            "metrics": analysis_payload["metrics"],
        }
        rows.append(row)
        case_manifest["phase_status"]["analysis"] = "completed" if analysis_payload["artifact_paths"] else "empty"
        case_manifest["phase_status"]["summary"] = "completed"
        _save_case_manifest(run_dir, repo, case_manifest)
        write_json(case_dir / "benchmark_table.json", {"rows": [row]})
        write_json(case_dir / "summary.json", row)
    completed_cases = sum(1 for row in rows if row["completed"])
    overall_status = (
        "completed"
        if completed_cases == len(rows)
        else ("in_progress" if any(row["image_build_success"] or row["benchmark_run_success"] or row["wdl_success"] for row in rows) else "pending")
    )
    payload = {
        "run_dir": str(run_dir),
        "catalog_file": str(_catalog_path()),
        "dataset_root": str(_dataset_root()),
        "case_count": len(rows),
        "completed_cases": completed_cases,
        "status": overall_status,
        "rows": rows,
    }
    write_json(run_dir / "benchmark_table.json", {"rows": rows})
    write_json(run_dir / "summary.json", payload)
    lines = [
        "# Benchmark Summary",
        "",
        f"- run_dir: `{run_dir}`",
        f"- dataset_root: `{_dataset_root()}`",
        f"- case_count: `{len(rows)}`",
        f"- completed_cases: `{completed_cases}`",
        f"- status: `{overall_status}`",
        "",
        "## Rows",
        "",
    ]
    lines.extend(
        f"- `{row['repo']}`: image_build_success=`{row['image_build_success']}`, benchmark_run_success=`{row['benchmark_run_success']}`, wdl_success=`{row['wdl_success']}`, completed=`{row['completed']}`"
        for row in rows
    )
    write_text(run_dir / "summary.md", "\n".join(lines) + "\n")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Local benchmark workflow orchestrator helper.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init = subparsers.add_parser("init", help="Create a benchmark run directory from the benchmark catalog.")
    init.add_argument("--task", required=True)
    init.add_argument("--output-dir")
    init.set_defaults(func=cmd_init)

    catalog = subparsers.add_parser("catalog-datasets", help="Print the dataset catalog used by the benchmark skill.")
    catalog.set_defaults(func=cmd_catalog_datasets)

    resolve = subparsers.add_parser("resolve-datasets", help="Resolve the fixed dataset mapping for the benchmark run.")
    resolve.add_argument("--run-dir", required=True)
    resolve.set_defaults(func=cmd_resolve_datasets)

    prepare = subparsers.add_parser("prepare-case", help="Materialize one repo case manifest, inputs, and agent task.")
    prepare.add_argument("--repo", required=True, choices=sorted(CASES))
    prepare.add_argument("--run-dir", required=True)
    prepare.set_defaults(func=cmd_prepare_case)

    execution_ready = subparsers.add_parser("execution-ready", help="Resolve dockerfile/WDL/input/runtime candidates for one repo case.")
    execution_ready.add_argument("--repo", required=True, choices=sorted(CASES))
    execution_ready.add_argument("--run-dir", required=True)
    execution_ready.set_defaults(func=cmd_execution_ready)

    prebuild = subparsers.add_parser("prebuild-image", help="Run or record one repo image prebuild.")
    prebuild.add_argument("--repo", required=True, choices=sorted(CASES))
    prebuild.add_argument("--run-dir", required=True)
    prebuild.add_argument("--dockerfile-path")
    prebuild.add_argument("--context-dir")
    prebuild.add_argument("--image-tag")
    prebuild.add_argument("--timeout-seconds", type=int, default=3600)
    prebuild.add_argument("--build-command", nargs=argparse.REMAINDER)
    prebuild.set_defaults(func=cmd_prebuild_image)

    run_repo_native = subparsers.add_parser("run-repo-native", help="Execute one repo-native benchmark run in Docker and write run/status.json.")
    run_repo_native.add_argument("--repo", required=True, choices=sorted(CASES))
    run_repo_native.add_argument("--run-dir", required=True)
    run_repo_native.add_argument("--image")
    run_repo_native.add_argument("--shell-command")
    run_repo_native.add_argument("--entrypoint", default="/bin/bash")
    run_repo_native.add_argument("--no-shell", action="store_true")
    run_repo_native.add_argument("--timeout-seconds", type=int, default=7200)
    run_repo_native.set_defaults(func=cmd_run_repo_native)

    analyze = subparsers.add_parser("analyze-case", help="Analyze one case from local WDL and benchmark artifacts.")
    analyze.add_argument("--repo", required=True, choices=sorted(CASES))
    analyze.add_argument("--run-dir", required=True)
    analyze.set_defaults(func=cmd_analyze_case)

    summarize = subparsers.add_parser("summarize", help="Summarize real per-repo benchmark artifacts.")
    summarize.add_argument("--run-dir", required=True)
    summarize.set_defaults(func=cmd_summarize)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
