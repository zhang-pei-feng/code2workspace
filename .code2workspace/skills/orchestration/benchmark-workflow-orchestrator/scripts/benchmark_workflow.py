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
import threading
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SHARED_HELPER_DIR = Path(__file__).resolve().parents[3] / "_shared-superagent-helpers" / "scripts"
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

FILE_INPUT_SUFFIXES = (
    ".fq",
    ".fastq",
    ".fa",
    ".fasta",
    ".gz",
    ".bam",
    ".bed",
    ".pt",
    ".vcf",
    ".sam",
    ".gtf",
    ".csv",
    ".txt",
    ".pdb",
    ".pdbqt",
)

FAMILY_METRICS = {
    "short-read-assembly": ["contig_count", "n50", "assembly_size"],
    "long-read-assembly": ["contig_count", "n50", "assembly_size"],
    "rna-seq-transcriptome": ["transcript_count", "trinity_fasta_size"],
    "viral-short-read-pipeline": ["consensus_fasta", "variant_outputs", "coverage_summary"],
    "viral-ont-amplicon": ["consensus_fasta", "variant_outputs", "coverage_summary"],
    "unknown": [],
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
        return FAMILY_METRICS.get(self.family, [])

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["metric_keys"] = self.metric_keys
        return payload


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[5]


def _default_benchmark_root() -> Path:
    return _repo_root() / "experiments" / "benchmark"


def _catalog_path(root: Path | None = None) -> Path:
    benchmark_root = root or _default_benchmark_root()
    return benchmark_root / "datasets" / "benchmark_catalog.json"


def _load_catalog(root: Path | None = None) -> tuple[dict[str, Any], dict[str, DatasetSpec], dict[str, RepoCase]]:
    raw = _load_or_discover_catalog(root)
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
            repo_url=str(payload.get("repo_url", "")),
            family=str(payload.get("family", "unknown")),
            dataset_key=str(payload["dataset_key"]),
            image_tag=str(payload.get("image_tag", f"benchmark/{name.casefold()}:latest")),
            repo_native_entry=str(payload.get("repo_native_entry", "")),
            wdl_workflow_name=str(payload.get("wdl_workflow_name", name)),
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


def _load_or_discover_catalog(root: Path | None = None) -> dict[str, Any]:
    benchmark_root = (root or _default_benchmark_root()).resolve()
    dataset_root = _infer_dataset_root_for_benchmark_root(benchmark_root)
    try:
        raw = json.loads(_catalog_path(benchmark_root).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        raw = {
            "benchmark_root": str(benchmark_root),
            "catalog_file": str(_catalog_path(benchmark_root)),
            "dataset_root": str(dataset_root),
            "downloads_root": str(dataset_root / "downloads"),
            "datasets": {},
            "repo_cases": {},
        }
    raw.setdefault("benchmark_root", str(benchmark_root))
    raw.setdefault("catalog_file", str(_catalog_path(benchmark_root)))
    raw.setdefault("dataset_root", str(dataset_root))
    raw.setdefault("downloads_root", str(dataset_root / "downloads"))
    raw.setdefault("datasets", {})
    raw.setdefault("repo_cases", {})
    _augment_catalog_from_dataset_readmes(raw)
    return _augment_catalog_from_case_dirs(raw, benchmark_root=benchmark_root)


def _infer_dataset_root_for_benchmark_root(benchmark_root: Path) -> Path:
    if benchmark_root.name.casefold() in {"circrna", "cirrna", "免疫逃逸", "新冠病毒组装"}:
        candidates = [
            benchmark_root.parent / "datasets",
            benchmark_root / "datasets",
        ]
    else:
        candidates = [
            benchmark_root / "datasets",
            benchmark_root.parent / "datasets",
        ]
    for candidate in candidates:
        if candidate.exists():
            return candidate.resolve()
    return candidates[0].resolve()


def _augment_catalog_from_dataset_readmes(raw: dict[str, Any]) -> None:
    datasets = raw.get("datasets")
    if not isinstance(datasets, dict):
        return
    downloads_raw = Path(str(raw.get("downloads_root", "")))
    downloads_root = downloads_raw if downloads_raw.is_absolute() else _repo_root() / downloads_raw
    if not downloads_root.exists():
        return
    for dataset_dir in sorted(path for path in downloads_root.iterdir() if path.is_dir()):
        key = dataset_dir.name
        if key in datasets:
            continue
        expected_files = _expected_dataset_files_from_readme(dataset_dir / "README.md")
        datasets[key] = {
            "dataset_id": key,
            "description": f"Shared benchmark dataset declared by {dataset_dir / 'README.md'}.",
            "fallback_urls": [],
            "family": _family_for_dataset_key(key),
            "files": [
                {"logical_name": _logical_input_name(name, index), "uri": str(dataset_dir / name), "filename": name}
                for index, name in enumerate(expected_files, start=1)
            ],
            "local_candidates": [str(dataset_dir / name) for name in expected_files],
            "shared_between": [],
            "source": "shared benchmark dataset directory",
            "source_urls": [],
        }


def _expected_dataset_files_from_readme(path: Path) -> list[str]:
    if not path.exists():
        return []
    names: list[str] = []
    for match in re.finditer(r"`([^`]+)`", path.read_text(encoding="utf-8", errors="replace")):
        name = match.group(1).strip()
        if name and not name.endswith("/"):
            names.append(name)
    return sorted(dict.fromkeys(names))


def _augment_catalog_from_case_dirs(raw: dict[str, Any], *, benchmark_root: Path) -> dict[str, Any]:
    datasets = raw.get("datasets")
    repo_cases = raw.get("repo_cases")
    if not isinstance(datasets, dict) or not isinstance(repo_cases, dict):
        return raw

    discovered: dict[str, dict[str, Any]] = {}
    for case_dir in _discover_case_dirs(benchmark_root):
        case = _case_payload_from_dir(benchmark_root, case_dir)
        if case is not None:
            discovered[str(case["repo_name"])] = case

    for repo_name, case in discovered.items():
        remapped_dataset = _shared_dataset_key_for_case(benchmark_root, case)
        if remapped_dataset:
            case["dataset_key"] = remapped_dataset
        repo_cases.setdefault(repo_name, case)

    for case in discovered.values():
        dataset_key = str(case["dataset_key"])
        shared_between = sorted(
            repo
            for repo, payload in repo_cases.items()
            if isinstance(payload, dict) and str(payload.get("dataset_key")) == dataset_key
        )
        existing = datasets.get(dataset_key)
        if isinstance(existing, dict):
            existing_shared = [str(item) for item in existing.get("shared_between", []) if isinstance(item, str)]
            existing["shared_between"] = sorted(set(existing_shared + shared_between))
            continue
        datasets[dataset_key] = {
            "dataset_id": dataset_key,
            "description": "Shared benchmark inputs inferred from local WDL input JSON files.",
            "fallback_urls": [],
            "family": case.get("family", "unknown"),
            "files": case.get("dataset_files", []),
            "local_candidates": case.get("local_candidates", []),
            "shared_between": shared_between,
            "source": "local benchmark inputs",
            "source_urls": [],
        }
    return raw


def _shared_dataset_key_for_case(benchmark_root: Path, case: dict[str, Any]) -> str | None:
    lowered_root = str(benchmark_root).casefold()
    repo_name = str(case.get("repo_name", "")).casefold()
    if "circrna" in lowered_root or "cirrna" in lowered_root:
        if repo_name == "aquarium-hb":
            return "circrna-blood-prjna722046"
        return "circrna-hela-rnaser-paired"
    if "免疫逃逸" in lowered_root:
        if repo_name == "esm":
            return "immune-escape-covabdab-structural-bundle"
        if repo_name in {"immunebuilder", "autodock-vina", "imapep"}:
            return "immune-escape-covabdab-structural-bundle"
    return None


def _discover_case_dirs(root: Path) -> list[Path]:
    case_dirs: list[Path] = []
    for input_path in sorted([*root.rglob("inputs.json"), *root.rglob("input.json")]):
        if "datasets" in input_path.parts:
            continue
        case_dir = input_path.parent
        if any(case_dir.glob("*.wdl")):
            case_dirs.append(case_dir)
    return case_dirs


def _case_payload_from_dir(benchmark_root: Path, case_dir: Path) -> dict[str, Any] | None:
    input_path = next((path for path in (case_dir / "inputs.json", case_dir / "input.json") if path.exists()), None)
    wdl_path = next(iter(sorted(case_dir.glob("*.wdl"))), None)
    if input_path is None or wdl_path is None:
        return None
    try:
        inputs = json.loads(input_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(inputs, dict):
        return None
    repo_name = re.sub(r"^\d+[_-]*", "", case_dir.name)
    input_files = _file_input_values(inputs)
    if not input_files:
        return None
    workflow_name = _workflow_name_from_wdl(wdl_path) or repo_name
    family = _family_for_case(repo_name, workflow_name, input_files)
    runtime_image = _runtime_image_from_wdl_text(wdl_path.read_text(encoding="utf-8", errors="replace")) or f"benchmark/{repo_name.casefold()}:latest"
    dockerfile_candidates = []
    local_dockerfile = case_dir / "Dockerfile"
    if local_dockerfile.exists():
        dockerfile_candidates.append(_manifest_path_for(local_dockerfile, benchmark_root=benchmark_root))
    dockerfile_candidates.extend(
        item for item in _known_dockerfile_candidates(repo_name) if item not in dockerfile_candidates
    )
    return {
        "case_dir": _manifest_path_for(case_dir, benchmark_root=benchmark_root),
        "constraints": ["Use benchmark inputs discovered from the local case directory."],
        "dataset_key": _dataset_key_for_input_files(input_files),
        "dockerfile_candidates": dockerfile_candidates,
        "dockerfile_path": dockerfile_candidates[0] if dockerfile_candidates else None,
        "expected_outputs": _expected_outputs_for_family(family),
        "family": family,
        "image_tag": runtime_image,
        "input_json_candidates": [_manifest_path_for(input_path, benchmark_root=benchmark_root)],
        "inputs_path": _manifest_path_for(input_path, benchmark_root=benchmark_root),
        "local_result_candidates": [],
        "repo_native_command_candidates": [],
        "repo_native_entry": _default_repo_native_entry(repo_name),
        "repo_url": _known_repo_url(repo_name),
        "wdl_candidates": [_manifest_path_for(wdl_path, benchmark_root=benchmark_root)],
        "wdl_path": _manifest_path_for(wdl_path, benchmark_root=benchmark_root),
        "wdl_workflow_name": workflow_name,
        "dataset_files": _dataset_files_for_inputs(input_files),
        "local_candidates": input_files,
        "repo_name": repo_name,
    }


def _manifest_path_for(path: Path, *, benchmark_root: Path) -> str:
    resolved = path.resolve()
    try:
        return str(resolved.relative_to(_repo_root()))
    except ValueError:
        pass
    return str(resolved)


def _file_input_values(inputs: dict[str, Any]) -> list[str]:
    values: list[str] = []
    for value in _iter_input_values(inputs):
        if not isinstance(value, str):
            continue
        lowered = value.casefold()
        if any(lowered.endswith(suffix) for suffix in FILE_INPUT_SUFFIXES):
            values.append(value)
    return sorted(dict.fromkeys(values))


def _iter_input_values(value: Any):
    if isinstance(value, dict):
        for item in value.values():
            yield from _iter_input_values(item)
    elif isinstance(value, list):
        for item in value:
            yield from _iter_input_values(item)
    else:
        yield value


def _workflow_name_from_wdl(wdl_path: Path) -> str | None:
    match = re.search(r"\bworkflow\s+([A-Za-z_][A-Za-z0-9_]*)", wdl_path.read_text(encoding="utf-8", errors="replace"))
    return match.group(1) if match else None


def _runtime_image_from_wdl_text(text: str) -> str | None:
    match = re.search(r'docker:\s*"([^"]+)"', text)
    return match.group(1) if match else None


def _dataset_key_for_input_files(input_files: list[str]) -> str:
    joined = "\n".join(input_files).casefold()
    if "srr001666" in joined:
        return "short-read-ecoli-srr001666"
    if "pacbio.fastq" in joined:
        return "long-read-canu-pacbio"
    digest = hashlib.sha1("\n".join(input_files).encode("utf-8")).hexdigest()[:10]
    return f"shared-inputs-{digest}"


def _dataset_files_for_inputs(input_files: list[str]) -> list[dict[str, str]]:
    return [
        {"logical_name": _logical_input_name(value, index), "uri": value, "filename": Path(value).name or f"input_{index}"}
        for index, value in enumerate(input_files, start=1)
    ]


def _logical_input_name(value: str, index: int) -> str:
    lowered = value.casefold()
    if "_1" in lowered or "r1" in lowered or "read1" in lowered:
        return "reads_1"
    if "_2" in lowered or "r2" in lowered or "read2" in lowered:
        return "reads_2"
    if "pacbio" in lowered or lowered.endswith((".fq", ".fastq", ".fq.gz", ".fastq.gz")):
        return "reads" if index == 1 else f"reads_{index}"
    return f"input_{index}"


def _family_for_dataset_key(key: str) -> str:
    lowered = key.casefold()
    if "circrna" in lowered:
        return "circrna"
    if "immune-escape" in lowered:
        return "immune-escape"
    if "short-read" in lowered:
        return "short-read-assembly"
    if "long-read" in lowered:
        return "long-read-assembly"
    return "unknown"


def _family_for_case(repo_name: str, workflow_name: str, input_files: list[str]) -> str:
    lowered = f"{repo_name} {workflow_name} {' '.join(input_files)}".casefold()
    if "spades" in lowered or "megahit" in lowered:
        return "short-read-assembly"
    if "canu" in lowered or "flye" in lowered or "pacbio" in lowered:
        return "long-read-assembly"
    if "trinity" in lowered:
        return "rna-seq-transcriptome"
    if "fieldbio" in lowered or "artic" in lowered:
        return "viral-ont-amplicon"
    if "covid" in lowered or "signal" in lowered:
        return "viral-short-read-pipeline"
    return "unknown"


def _known_repo_url(repo_name: str) -> str:
    known = {
        "spades": "https://github.com/ablab/spades",
        "megahit": "https://github.com/voutcn/megahit",
        "canu": "https://github.com/marbl/canu",
        "Flye": "https://github.com/fenderglass/Flye",
        "trinityrnaseq": "https://github.com/trinityrnaseq/trinityrnaseq",
        "covid-19-signal": "https://github.com/jaleezyy/covid-19-signal",
        "fieldbioinformatics": "https://github.com/artic-network/fieldbioinformatics",
        "biq": "https://github.com/pmenzel/biq",
        "circompara2": "https://github.com/egaffo/circompara2",
        "find-circ": "https://github.com/marvin-jens/find_circ",
    }
    return known.get(repo_name, "")


def _known_dockerfile_candidates(repo_name: str) -> list[str]:
    known = {
        "spades": [".workspaces/oneshot/spades/spades_Dockerfile"],
        "megahit": [
            ".workspaces/oneshot/megahit/megahit_Dockerfile",
            ".workspaces/oneshot/megahit/Dockerfile",
        ],
    }
    return known.get(repo_name, [])


def _default_repo_native_entry(repo_name: str) -> str:
    defaults = {
        "spades": "spades.py -1 <reads_1> -2 <reads_2>",
        "megahit": "megahit -1 <reads_1> -2 <reads_2> -o out",
        "canu": "canu -p ecoli -d out genomeSize=4.8m -pacbio <reads>",
        "Flye": "flye --pacbio-raw <reads> --out-dir out",
        "trinityrnaseq": "Trinity --left <reads_1> --right <reads_2> --seqType fq --output out",
    }
    return defaults.get(repo_name, "")


def _has_repo_native_entry(case_manifest: dict[str, Any]) -> bool:
    entry = str(case_manifest.get("repo_native_entry", "")).strip()
    if entry:
        return True
    candidates = case_manifest.get("repo_native_command_candidates", [])
    return isinstance(candidates, list) and any(isinstance(item, str) and item.strip() for item in candidates)


def _expected_outputs_for_family(family: str) -> list[str]:
    if family in {"short-read-assembly", "long-read-assembly"}:
        return ["assembly.fasta", "contigs.fasta", "final.contigs.fa"]
    if family == "rna-seq-transcriptome":
        return ["Trinity.fasta"]
    if family in {"viral-short-read-pipeline", "viral-ont-amplicon"}:
        return ["consensus.fasta", "variants.vcf", "coverage.tsv"]
    return []


RAW_CATALOG, DATASETS, CASES = _load_catalog()


def _activate_benchmark_root(root: str | Path | None) -> None:
    global RAW_CATALOG, DATASETS, CASES
    if root is None or not str(root).strip():
        RAW_CATALOG, DATASETS, CASES = _load_catalog()
        return
    RAW_CATALOG, DATASETS, CASES = _load_catalog(Path(root).expanduser().resolve())


def _activate_benchmark_root_from_run_dir(run_dir: Path) -> None:
    manifest_path = _root_manifest_path(run_dir)
    if not manifest_path.exists():
        return
    manifest = read_json(manifest_path)
    _activate_benchmark_root(manifest.get("benchmark_root"))


def _resolve_catalog_path(raw: str) -> Path:
    candidate = Path(raw)
    if candidate.is_absolute():
        return candidate
    return _repo_root() / candidate


def _dataset_root() -> Path:
    return _resolve_catalog_path(str(RAW_CATALOG["dataset_root"]))


def _downloads_root() -> Path:
    return _resolve_catalog_path(str(RAW_CATALOG["downloads_root"]))


def _active_catalog_file() -> str:
    return str(RAW_CATALOG.get("catalog_file") or _catalog_path())


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
    repo_root = _repo_root()
    primary = repo_root / raw
    if primary.exists():
        return primary
    if repo_root.parent.name == ".worktrees":
        shared_project_candidate = repo_root.parent.parent / raw
        if shared_project_candidate.exists():
            return shared_project_candidate
    return primary


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


def _root_plan_payload(task: str, run_dir: Path, case_order: list[str]) -> dict[str, Any]:
    return {
        "task": task,
        "run_dir": str(run_dir),
        "phase_order": PHASE_ORDER,
        "benchmark_root": str(RAW_CATALOG.get("benchmark_root", _default_benchmark_root())),
        "catalog_file": _active_catalog_file(),
        "dataset_root": str(_dataset_root()),
        "downloads_root": str(_downloads_root()),
        "case_order": case_order,
        "datasets": {key: spec.to_dict() for key, spec in DATASETS.items()},
        "cases": {name: CASES[name].to_dict() for name in case_order},
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


def _available_dataset_files(dataset: DatasetSpec) -> list[Path]:
    dataset_dir = ensure_dir(_dataset_download_dir(dataset.key))
    candidates = _dataset_target_files(dataset)
    candidates.extend(_resolve_repo_path(item) for item in dataset.local_candidates)
    candidates.extend(path for path in dataset_dir.rglob("*") if path.is_file())
    unique: dict[str, Path] = {}
    for candidate in candidates:
        if candidate.exists() and candidate.is_file():
            unique[str(candidate.resolve())] = candidate.resolve()
    return list(unique.values())


def _dataset_target_files(dataset: DatasetSpec) -> list[Path]:
    dataset_dir = ensure_dir(_dataset_download_dir(dataset.key))
    return [dataset_dir / item.filename for item in dataset.files]


def _rewrite_inputs_with_dataset_files(
    inputs: dict[str, Any],
    dataset_files: list[Path],
) -> tuple[dict[str, Any], dict[str, str], list[str]]:
    selected: dict[str, str] = {}
    missing: list[str] = []

    def rewrite(value: Any, key_hint: str) -> Any:
        if isinstance(value, dict):
            return {nested_key: rewrite(nested_value, nested_key) for nested_key, nested_value in value.items()}
        if isinstance(value, list):
            rewritten_items: list[Any] = []
            for index, item in enumerate(value, start=1):
                rewritten_items.append(rewrite(item, f"{key_hint}_{index}"))
            return rewritten_items
        if not isinstance(value, str) or not _looks_like_file_input(value):
            return value
        match = _match_dataset_file_for_input(key_hint, value, dataset_files)
        logical_name = _logical_name_from_input_key(key_hint, len(selected) + 1)
        if match is None:
            missing.append(key_hint)
            return value
        selected[logical_name] = str(match)
        if not match.exists():
            missing.append(key_hint)
        return str(match)

    return {key: rewrite(value, key) for key, value in inputs.items()}, selected, missing


def _looks_like_file_input(value: str) -> bool:
    lowered = value.casefold()
    return any(lowered.endswith(suffix) for suffix in FILE_INPUT_SUFFIXES)


def _logical_name_from_input_key(key: str, index: int) -> str:
    raw = key.rsplit(".", 1)[-1]
    normalized = re.sub(r"[^A-Za-z0-9_]+", "_", raw).strip("_")
    return normalized or f"input_{index}"


def _match_dataset_file_for_input(key_hint: str, old_value: str, files: list[Path]) -> Path | None:
    if not files:
        return None
    old_name = Path(old_value).name.casefold()
    for path in files:
        if path.name.casefold() == old_name:
            return path
    key = key_hint.casefold()
    ranked = sorted(files, key=lambda item: item.name.casefold())
    if any(marker in key for marker in ("fastq1", "read1", "reads_1", "r1")):
        return _first_file_matching(ranked, (".fastq.gz", ".fq.gz", ".fastq", ".fq"), ("_1", "r1"))
    if any(marker in key for marker in ("fastq2", "read2", "reads_2", "r2")):
        return _first_file_matching(ranked, (".fastq.gz", ".fq.gz", ".fastq", ".fq"), ("_2", "r2"))
    if "gtf" in key or "annotation" in key:
        return _first_file_matching(ranked, (".gtf",), ())
    if "bed" in key:
        return _first_file_matching(ranked, (".bed",), ())
    if "sam" in key:
        return _first_file_matching(ranked, (".sam",), ())
    if "bam" in key or "unmap" in key:
        return _first_file_matching(ranked, (".bam",), ())
    if "junction" in key or "circ" in key and "list" in key:
        return _first_file_matching(ranked, (".txt", ".csv"), ("circ", "junction"))
    if "meta" in key:
        return _first_file_matching(ranked, (".csv",), ("meta",))
    if "reference_file" in key:
        return _first_file_matching(ranked, (".txt",), ("reference", "circ"))
    if "pdbqt" in old_name or "pdbqt" in key:
        return _first_file_matching(ranked, (".pdbqt",), ())
    if "pdb" in old_name or "pdb" in key:
        return _first_file_matching(ranked, (".pdb",), ())
    if "fasta" in key or "genome" in key or "reference" in key or "ref" in key:
        return _first_file_matching(ranked, (".fa", ".fasta"), ())
    if "csv" in old_name or "escape" in key or "dms" in key:
        return _first_file_matching(ranked, (".csv",), ())
    return _first_file_matching(ranked, tuple(FILE_INPUT_SUFFIXES), ())


def _first_file_matching(files: list[Path], suffixes: tuple[str, ...], name_markers: tuple[str, ...]) -> Path | None:
    for path in files:
        lowered = path.name.casefold()
        if suffixes and not lowered.endswith(suffixes):
            continue
        if name_markers and not any(marker in lowered for marker in name_markers):
            continue
        return path
    return None


def _selected_input_files_are_ready(selected_input_files: dict[str, str]) -> bool:
    if not selected_input_files:
        return False
    for raw_path in selected_input_files.values():
        if any(token in raw_path for token in ("*", "?", "[")):
            return False
        if not Path(raw_path).exists():
            return False
    return True


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
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("w", encoding="utf-8") as log_handle:
        process = subprocess.Popen(
            command,
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        assert process.stdout is not None

        def _stream_output() -> None:
            for chunk in process.stdout:
                log_handle.write(chunk)
                log_handle.flush()

        reader = threading.Thread(target=_stream_output, daemon=True)
        reader.start()
        try:
            returncode = process.wait(timeout=timeout_seconds)
        except subprocess.TimeoutExpired:
            process.kill()
            returncode = process.wait()
        reader.join(timeout=5)
        log_handle.flush()

    elapsed = round(time.time() - started_at, 3)
    return {
        "attempted": True,
        "completed": True,
        "success": returncode == 0,
        "returncode": returncode,
        "elapsed_seconds": elapsed,
        "command": command,
        "log_path": str(log_path),
    }


def _docker_image_exists(image_ref: str) -> bool:
    try:
        completed = subprocess.run(
            ["docker", "image", "inspect", image_ref],
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        return False
    return completed.returncode == 0


def _docker_mirror_candidates() -> list[str]:
    raw = os.environ.get("CODE2WORKSPACE_DOCKER_MIRRORS")
    if raw:
        return [item.strip().rstrip("/") for item in raw.split(",") if item.strip()]
    return ["docker.m.daocloud.io", "hub.rat.dev"]


def _dockerfile_local_sources(dockerfile_path: Path | None) -> list[str]:
    if dockerfile_path is None or not dockerfile_path.exists():
        return []
    sources: list[str] = []
    for raw_line in dockerfile_path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        instruction, _, rest = line.partition(" ")
        if instruction.upper() not in {"COPY", "ADD"} or not rest.strip():
            continue
        tokens = shlex.split(rest, comments=True)
        while tokens and tokens[0].startswith("--"):
            tokens.pop(0)
        if len(tokens) < 2:
            continue
        for source in tokens[:-1]:
            if source.startswith(("http://", "https://")) or source == "-":
                continue
            sources.append(source)
    return sources


def _source_root_for_materialization(source: str) -> str | None:
    first = source.strip().lstrip("./").split("/", 1)[0]
    if not first or any(char in first for char in "*?["):
        return None
    return first


def _dockerfile_source_roots(dockerfile_path: Path | None) -> list[str]:
    roots: list[str] = []
    for source in _dockerfile_local_sources(dockerfile_path):
        root = _source_root_for_materialization(source)
        if root and root not in roots:
            roots.append(root)
    return roots


def _copy_missing_tree(source_dir: Path, target_dir: Path) -> int:
    copied = 0
    for item in source_dir.rglob("*"):
        relative = item.relative_to(source_dir)
        if ".git" in relative.parts:
            continue
        target = target_dir / relative
        if item.is_dir():
            target.mkdir(parents=True, exist_ok=True)
            continue
        if target.exists():
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(item, target)
        copied += 1
    return copied


def _materialize_missing_docker_context_sources(
    *,
    dockerfile_path: Path | None,
    context_dir: Path,
    case_manifest: dict[str, Any],
    timeout_seconds: int,
) -> list[dict[str, Any]]:
    repo_url = str(case_manifest.get("repo_url", "")).strip()
    if not repo_url:
        return []
    materialized: list[dict[str, Any]] = []
    source_roots = _dockerfile_source_roots(dockerfile_path)
    if not source_roots:
        return materialized
    source_root = context_dir / ".prebuild_sources"
    ensure_dir(source_root)
    repo_name = str(case_manifest.get("repo_name", "")).strip() or "repo"
    clone_dir = source_root / re.sub(r"[^A-Za-z0-9_.-]+", "_", repo_name)
    if not clone_dir.exists():
        clone = subprocess.run(
            ["git", "clone", "--depth", "1", repo_url, str(clone_dir)],
            capture_output=True,
            text=True,
            timeout=min(timeout_seconds, 600),
            check=False,
        )
        materialized.append(
            {
                "repo_url": repo_url,
                "clone_dir": str(clone_dir),
                "returncode": clone.returncode,
                "tail": (clone.stdout + clone.stderr)[-1000:],
            }
        )
        if clone.returncode != 0:
            return materialized
    else:
        materialized.append({"repo_url": repo_url, "clone_dir": str(clone_dir), "returncode": 0, "cached": True})
    for root in source_roots:
        target_dir = context_dir / root
        copied = _copy_missing_tree(clone_dir, target_dir)
        materialized.append(
            {
                "source_root": root,
                "target_dir": str(target_dir),
                "copied_files": copied,
            }
        )
    return materialized


def _dockerfile_base_images(dockerfile_path: Path | None) -> list[str]:
    if dockerfile_path is None or not dockerfile_path.exists():
        return []
    images: list[str] = []
    for raw_line in dockerfile_path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        instruction, _, rest = line.partition(" ")
        if instruction.upper() != "FROM" or not rest.strip():
            continue
        tokens = shlex.split(rest, comments=True)
        while tokens and tokens[0].startswith("--"):
            tokens.pop(0)
        if not tokens:
            continue
        image = tokens[0]
        if image.lower() == "scratch" or "$" in image:
            continue
        images.append(image)
    return images


def _mirror_image_ref(image_ref: str, mirror: str) -> str | None:
    registry_or_name = image_ref.split("/", 1)[0]
    has_registry = "." in registry_or_name or ":" in registry_or_name or registry_or_name == "localhost"
    if has_registry:
        return None
    if "/" in image_ref:
        return f"{mirror}/{image_ref}"
    return f"{mirror}/library/{image_ref}"


def _preload_base_images_from_mirrors(dockerfile_path: Path | None, *, timeout_seconds: int) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for image_ref in _dockerfile_base_images(dockerfile_path):
        if _docker_image_exists(image_ref):
            results.append({"image": image_ref, "status": "present"})
            continue
        image_result: dict[str, Any] = {"image": image_ref, "status": "missing", "attempts": []}
        for mirror in _docker_mirror_candidates():
            mirror_ref = _mirror_image_ref(image_ref, mirror)
            if mirror_ref is None:
                continue
            pull = subprocess.run(
                ["docker", "pull", mirror_ref],
                capture_output=True,
                text=True,
                timeout=min(timeout_seconds, 300),
                check=False,
            )
            attempt = {
                "mirror": mirror,
                "mirror_ref": mirror_ref,
                "returncode": pull.returncode,
                "tail": (pull.stdout + pull.stderr)[-1000:],
            }
            image_result["attempts"].append(attempt)
            if pull.returncode != 0:
                continue
            tag = subprocess.run(
                ["docker", "tag", mirror_ref, image_ref],
                capture_output=True,
                text=True,
                timeout=60,
                check=False,
            )
            attempt["tag_returncode"] = tag.returncode
            if tag.returncode == 0 and _docker_image_exists(image_ref):
                image_result["status"] = "preloaded"
                image_result["mirror_ref"] = mirror_ref
                break
        results.append(image_result)
    return results


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


def _extract_output_artifacts_from_outputs_json(outputs_path: Path) -> list[str]:
    if not outputs_path.exists():
        return []
    try:
        payload = json.loads(outputs_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []

    artifacts: list[str] = []

    def visit(value: Any) -> None:
        if isinstance(value, str):
            candidate = Path(value)
            if candidate.exists() and candidate.is_file():
                artifacts.append(str(candidate))
            return
        if isinstance(value, list):
            for item in value:
                visit(item)
            return
        if isinstance(value, dict):
            for item in value.values():
                visit(item)

    visit(payload)
    seen: set[str] = set()
    ordered: list[str] = []
    for artifact in artifacts:
        if artifact in seen:
            continue
        seen.add(artifact)
        ordered.append(artifact)
    return ordered


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
    _activate_benchmark_root(args.benchmark_root)
    payload = {
        "benchmark_root": str(RAW_CATALOG.get("benchmark_root", _default_benchmark_root())),
        "catalog_file": _active_catalog_file(),
        "dataset_root": str(_dataset_root()),
        "downloads_root": str(_downloads_root()),
        "dataset_count": len(DATASETS),
        "datasets": {key: spec.to_dict() for key, spec in DATASETS.items()},
        "repo_cases": {name: case.to_dict() for name, case in CASES.items()},
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def cmd_init(args: argparse.Namespace) -> int:
    _activate_benchmark_root(args.benchmark_root)
    run_dir = Path(args.output_dir) if args.output_dir else create_skill_run_dir("benchmark-workflow-orchestrator", "runs")
    ensure_dir(run_dir)
    ensure_dir(_cases_root(run_dir))
    ensure_dir(_dataset_root())
    ensure_dir(_downloads_root())
    ensure_dir(run_dir / "logs")
    case_order = list(args.repos) if args.repos else list(CASES)
    unknown = [repo for repo in case_order if repo not in CASES]
    if unknown:
        raise SystemExit(f"Unknown benchmark repo case(s) for {RAW_CATALOG.get('benchmark_root')}: {', '.join(unknown)}")
    root_payload = _root_plan_payload(args.task, run_dir, case_order)
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
    for name in case_order:
        case = CASES[name]
        lines.append(f"- `{name}` -> dataset `{case.dataset_key}` / family `{case.family}`")
        case_dir = _case_dir(run_dir, name)
        ensure_dir(case_dir / "docker")
        ensure_dir(case_dir / "wdl")
        ensure_dir(case_dir / "run")
        manifest = _initial_case_manifest(case, run_dir)
        _save_case_manifest(run_dir, name, manifest)
        _write_case_readme(case_dir, manifest, DATASETS[case.dataset_key])
    write_text(run_dir / "benchmark_plan.md", "\n".join(lines) + "\n")
    print(json.dumps({"run_dir": str(run_dir), "case_count": len(case_order), "case_order": case_order}, ensure_ascii=False, indent=2))
    return 0


def cmd_resolve_datasets(args: argparse.Namespace) -> int:
    run_dir = Path(args.run_dir).resolve()
    _activate_benchmark_root_from_run_dir(run_dir)
    manifest = _load_root_manifest(run_dir)
    payload = {
        "run_dir": str(run_dir),
        "benchmark_root": str(RAW_CATALOG.get("benchmark_root", _default_benchmark_root())),
        "catalog_file": _active_catalog_file(),
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
    _activate_benchmark_root_from_run_dir(run_dir)
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
        "catalog_file": _active_catalog_file(),
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
    source_inputs_payload: dict[str, Any] | None = None
    rewritten_inputs_payload: dict[str, Any] | None = None
    rewritten_selected_inputs: dict[str, str] = {}
    missing_input_keys: list[str] = []
    if source_inputs_path is not None and source_inputs_path.exists():
        try:
            source_inputs_payload = json.loads(source_inputs_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            source_inputs_payload = None
        if isinstance(source_inputs_payload, dict):
            rewritten_inputs_payload, rewritten_selected_inputs, missing_input_keys = _rewrite_inputs_with_dataset_files(
                source_inputs_payload,
                [*_dataset_target_files(dataset), *_available_dataset_files(dataset)],
            )
            if rewritten_selected_inputs:
                selection = {
                    **selection,
                    "selected_input_source": "shared_dataset_rewrite",
                    "selected_input_files": rewritten_selected_inputs,
                    "selection_complete": not missing_input_keys,
                    "selection_reason": (
                        "Rewrote the case input template using files from the selected shared dataset."
                        if not missing_input_keys
                        else "Rewrote part of the case input template using shared dataset files; some file inputs are still unmapped."
                    ),
                    "missing_input_keys": missing_input_keys,
                }
                write_json(case_dir / "dataset_selection.json", selection)
    dataset_manifest.update(selection)
    write_json(case_dir / "dataset_manifest.json", dataset_manifest)
    if source_wdl_path is not None and source_wdl_path.exists():
        shutil.copy2(source_wdl_path, case_dir / "wdl" / source_wdl_path.name)
    if rewritten_inputs_payload is not None:
        write_json(case_dir / "wdl" / "inputs.json", rewritten_inputs_payload)
        if source_inputs_path is not None and source_inputs_path.exists():
            shutil.copy2(source_inputs_path, case_dir / "wdl" / "inputs.original.json")
    elif source_inputs_path is not None and source_inputs_path.exists():
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
    case_manifest["missing_input_keys"] = selection.get("missing_input_keys", [])
    case_manifest["selection_reason"] = selection["selection_reason"]
    _save_case_manifest(run_dir, repo, case_manifest)
    print(json.dumps({"repo": repo, "dataset_key": dataset.key, "case_dir": str(case_dir)}, ensure_ascii=False, indent=2))
    return 0


def cmd_execution_ready(args: argparse.Namespace) -> int:
    run_dir = Path(args.run_dir).resolve()
    _activate_benchmark_root_from_run_dir(run_dir)
    repo = args.repo
    case_manifest = _load_case_manifest(run_dir, repo)
    case = CASES[repo]
    dockerfile_path = _resolve_repo_path(case.dockerfile_path) if case.dockerfile_path else _first_existing(case.dockerfile_candidates)
    if dockerfile_path is not None and not dockerfile_path.exists():
        dockerfile_path = None
    wdl_path = _resolve_repo_path(case.wdl_path) if case.wdl_path else _first_existing(case.wdl_candidates)
    if wdl_path is not None and not wdl_path.exists():
        wdl_path = None
    staged_input_json_path = _case_dir(run_dir, repo) / "wdl" / "inputs.json"
    input_json_path = staged_input_json_path if staged_input_json_path.exists() else (_resolve_repo_path(case.inputs_path) if case.inputs_path else _first_existing(case.input_json_candidates))
    if input_json_path is not None and not input_json_path.exists():
        input_json_path = None
    local_result_candidates = [str(_resolve_repo_path(item)) for item in case.local_result_candidates if _resolve_repo_path(item).exists()]
    runtime_image = _runtime_image_from_wdl(wdl_path) if wdl_path is not None else case.image_tag
    selected_input_files = {
        str(key): str(value)
        for key, value in dict(case_manifest.get("selected_input_files") or {}).items()
        if isinstance(key, str) and isinstance(value, str)
    }
    missing_input_keys = [
        str(item)
        for item in case_manifest.get("missing_input_keys", [])
        if isinstance(item, str) and item.strip()
    ]
    inputs_ready = _selected_input_files_are_ready(selected_input_files) and not missing_input_keys
    payload = {
        "repo": repo,
        "dockerfile_path": None if dockerfile_path is None else str(dockerfile_path),
        "wdl_path": None if wdl_path is None else str(wdl_path),
        "inputs_json_path": None if input_json_path is None else str(input_json_path),
        "repo_native_command_candidates": list(case.repo_native_command_candidates),
        "local_result_candidates": local_result_candidates,
        "runtime_image": runtime_image,
        "ready": wdl_path is not None and input_json_path is not None and bool(runtime_image) and inputs_ready,
        "inputs_ready": inputs_ready,
        "missing_input_keys": missing_input_keys,
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
    _activate_benchmark_root_from_run_dir(run_dir)
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
    base_image_preload: list[dict[str, Any]] = []
    source_materialization: list[dict[str, Any]] = []
    if _docker_image_exists(image_tag):
        status = {
            "attempted": False,
            "completed": True,
            "success": True,
            "returncode": 0,
            "elapsed_seconds": 0.0,
            "command": [],
            "log_path": str(log_path),
            "image_present": True,
            "reason": "Image already exists locally; skipped rebuild.",
        }
        log_path.write_text("", encoding="utf-8")
    elif args.build_command:
        status = _run_build_command(args.build_command, cwd=context_dir, log_path=log_path, timeout_seconds=args.timeout_seconds)
    elif dockerfile_path is not None and dockerfile_path.exists():
        base_image_preload = _preload_base_images_from_mirrors(
            dockerfile_path,
            timeout_seconds=args.timeout_seconds,
        )
        source_materialization = _materialize_missing_docker_context_sources(
            dockerfile_path=dockerfile_path,
            context_dir=context_dir,
            case_manifest=case_manifest,
            timeout_seconds=args.timeout_seconds,
        )
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
    if base_image_preload:
        status["base_image_preload"] = base_image_preload
    if source_materialization:
        status["source_materialization"] = source_materialization
    write_json(docker_dir / "status.json", status)
    case_manifest["phase_status"]["prebuild"] = "completed" if status["success"] else ("failed" if status["attempted"] else "pending")
    _save_case_manifest(run_dir, repo, case_manifest)
    print(json.dumps({"repo": repo, "image_tag": image_tag, **status}, ensure_ascii=False, indent=2))
    return 0


def cmd_run_repo_native(args: argparse.Namespace) -> int:
    run_dir = Path(args.run_dir).resolve()
    _activate_benchmark_root_from_run_dir(run_dir)
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


def cmd_run_wdl(args: argparse.Namespace) -> int:
    run_dir = Path(args.run_dir).resolve()
    _activate_benchmark_root_from_run_dir(run_dir)
    repo = args.repo
    case_manifest = _load_case_manifest(run_dir, repo)
    case_dir = _case_dir(run_dir, repo)
    wdl_dir = case_dir / "wdl"
    ensure_dir(wdl_dir)

    workflow_path = wdl_dir / "workflow.wdl"
    if not workflow_path.exists():
        workflow_path = next(iter(sorted(wdl_dir.glob("*.wdl"))), None)
    inputs_path = wdl_dir / "inputs.json"
    if workflow_path is None or not workflow_path.exists():
        raise SystemExit(f"No staged workflow found for {repo}. Run prepare-case first.")
    if not inputs_path.exists():
        raise SystemExit(f"No staged inputs.json found for {repo}. Run prepare-case first.")

    outputs_path = wdl_dir / "outputs.json"
    log_path = wdl_dir / "miniwdl_run.log"
    command = [
        str(_repo_root() / "scripts" / "run-miniwdl.sh"),
        str(workflow_path),
        "-i",
        str(inputs_path),
        "-o",
        str(outputs_path),
    ]
    status = _run_logged_command(command, cwd=wdl_dir, log_path=log_path, timeout_seconds=args.timeout_seconds)
    status["workflow_path"] = str(workflow_path)
    status["inputs_path"] = str(inputs_path)
    status["outputs_path"] = str(outputs_path)
    status["output_artifacts"] = _extract_output_artifacts_from_outputs_json(outputs_path)
    write_json(wdl_dir / "status.json", status)

    case_manifest.setdefault("benchmark_notes", {})
    case_manifest["benchmark_notes"]["wdl_status"] = str(wdl_dir / "status.json")
    case_manifest["benchmark_notes"]["wdl_log"] = str(log_path)
    case_manifest["benchmark_notes"]["wdl_failure_reason"] = status.get("failure_reason")
    _save_case_manifest(run_dir, repo, case_manifest)
    print(json.dumps({"repo": repo, **status}, ensure_ascii=False, indent=2))
    return 0


def cmd_run_wdl(args: argparse.Namespace) -> int:
    run_dir = Path(args.run_dir).resolve()
    _activate_benchmark_root_from_run_dir(run_dir)
    repo = args.repo
    case_manifest = _load_case_manifest(run_dir, repo)
    case_dir = _case_dir(run_dir, repo)
    wdl_dir = case_dir / "wdl"
    ensure_dir(wdl_dir)

    workflow_candidates = [wdl_dir / "workflow.wdl", *sorted(wdl_dir.glob("*.wdl"))]
    workflow_path = next((path for path in workflow_candidates if path.exists()), None)
    inputs_path = wdl_dir / "inputs.json"
    if workflow_path is None:
        raise SystemExit(f"No staged workflow found for {repo}. Run prepare-case first.")
    if not inputs_path.exists():
        raise SystemExit(f"No staged inputs.json found for {repo}. Run prepare-case first.")

    outputs_path = wdl_dir / "outputs.json"
    log_path = wdl_dir / "miniwdl_run.log"
    command = [
        str(_repo_root() / "scripts" / "run-miniwdl.sh"),
        str(workflow_path),
        "-i",
        str(inputs_path),
        "-o",
        str(outputs_path),
    ]
    status = _run_logged_command(command, cwd=wdl_dir, log_path=log_path, timeout_seconds=args.timeout_seconds)
    status["workflow_path"] = str(workflow_path)
    status["inputs_path"] = str(inputs_path)
    status["outputs_path"] = str(outputs_path)
    status["output_artifacts"] = _extract_output_artifacts_from_outputs_json(outputs_path)
    write_json(wdl_dir / "status.json", status)

    case_manifest.setdefault("benchmark_notes", {})
    case_manifest["benchmark_notes"]["wdl_status"] = str(wdl_dir / "status.json")
    case_manifest["benchmark_notes"]["wdl_log"] = str(log_path)
    case_manifest["benchmark_notes"]["wdl_failure_reason"] = status.get("failure_reason")
    _save_case_manifest(run_dir, repo, case_manifest)
    print(json.dumps({"repo": repo, **status}, ensure_ascii=False, indent=2))
    return 0


def cmd_analyze_case(args: argparse.Namespace) -> int:
    run_dir = Path(args.run_dir).resolve()
    _activate_benchmark_root_from_run_dir(run_dir)
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
    _activate_benchmark_root_from_run_dir(run_dir)
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
        "benchmark_root": str(RAW_CATALOG.get("benchmark_root", _default_benchmark_root())),
        "catalog_file": _active_catalog_file(),
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

    init = subparsers.add_parser("init", help="Create a benchmark run directory from discovered benchmark cases.")
    init.add_argument("--task", required=True)
    init.add_argument("--output-dir")
    init.add_argument("--benchmark-root", help="Directory to scan for benchmark WDL and input JSON assets.")
    init.add_argument("--repos", nargs="+")
    init.set_defaults(func=cmd_init)

    catalog = subparsers.add_parser("catalog-datasets", help="Print the dataset catalog used by the benchmark skill.")
    catalog.add_argument("--benchmark-root", help="Directory to scan for benchmark WDL and input JSON assets.")
    catalog.set_defaults(func=cmd_catalog_datasets)

    resolve = subparsers.add_parser("resolve-datasets", help="Resolve the fixed dataset mapping for the benchmark run.")
    resolve.add_argument("--run-dir", required=True)
    resolve.set_defaults(func=cmd_resolve_datasets)

    prepare = subparsers.add_parser("prepare-case", help="Materialize one repo case manifest, inputs, and agent task.")
    prepare.add_argument("--repo", required=True)
    prepare.add_argument("--run-dir", required=True)
    prepare.set_defaults(func=cmd_prepare_case)

    execution_ready = subparsers.add_parser("execution-ready", help="Resolve dockerfile/WDL/input/runtime candidates for one repo case.")
    execution_ready.add_argument("--repo", required=True)
    execution_ready.add_argument("--run-dir", required=True)
    execution_ready.set_defaults(func=cmd_execution_ready)

    prebuild = subparsers.add_parser("prebuild-image", help="Run or record one repo image prebuild.")
    prebuild.add_argument("--repo", required=True)
    prebuild.add_argument("--run-dir", required=True)
    prebuild.add_argument("--dockerfile-path")
    prebuild.add_argument("--context-dir")
    prebuild.add_argument("--image-tag")
    prebuild.add_argument("--timeout-seconds", type=int, default=14400)
    prebuild.add_argument("--build-command", nargs=argparse.REMAINDER)
    prebuild.set_defaults(func=cmd_prebuild_image)

    run_repo_native = subparsers.add_parser("run-repo-native", help="Execute one repo-native benchmark run in Docker and write run/status.json.")
    run_repo_native.add_argument("--repo", required=True)
    run_repo_native.add_argument("--run-dir", required=True)
    run_repo_native.add_argument("--image")
    run_repo_native.add_argument("--shell-command")
    run_repo_native.add_argument("--entrypoint", default="/bin/bash")
    run_repo_native.add_argument("--no-shell", action="store_true")
    run_repo_native.add_argument("--timeout-seconds", type=int, default=7200)
    run_repo_native.set_defaults(func=cmd_run_repo_native)

    run_wdl = subparsers.add_parser("run-wdl", help="Execute one staged benchmark WDL run and write wdl/status.json.")
    run_wdl.add_argument("--repo", required=True)
    run_wdl.add_argument("--run-dir", required=True)
    run_wdl.add_argument("--timeout-seconds", type=int, default=7200)
    run_wdl.set_defaults(func=cmd_run_wdl)

    analyze = subparsers.add_parser("analyze-case", help="Analyze one case from local WDL and benchmark artifacts.")
    analyze.add_argument("--repo", required=True)
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
