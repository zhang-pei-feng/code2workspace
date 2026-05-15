from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest


def _repo_root() -> Path:
    path = Path(__file__).resolve()
    for parent in path.parents:
        if (parent / ".code2workspace").exists():
            return parent
    msg = "Could not locate repo root from test path"
    raise RuntimeError(msg)


REPO_ROOT = _repo_root()
BENCHMARK_SCRIPT = (
    REPO_ROOT / ".code2workspace" / "skills" / "orchestration" / "benchmark-workflow-orchestrator" / "scripts" / "benchmark_workflow.py"
)


def load_module(path: Path, module_name: str):
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load module from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def run_json_command(*command: str) -> dict[str, object]:
    completed = subprocess.run(
        [sys.executable, *command],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(completed.stdout)

def test_benchmark_orchestrator_prebuild_does_not_count_as_completion(tmp_path: Path) -> None:
    run_dir = tmp_path / "benchmark-run"
    run_json_command(
        str(BENCHMARK_SCRIPT),
        "init",
        "--task",
        "local benchmark smoke",
        "--output-dir",
        str(run_dir),
    )
    run_json_command(str(BENCHMARK_SCRIPT), "resolve-datasets", "--run-dir", str(run_dir))
    run_json_command(str(BENCHMARK_SCRIPT), "prepare-case", "--repo", "spades", "--run-dir", str(run_dir))
    run_json_command(
        str(BENCHMARK_SCRIPT),
        "prebuild-image",
        "--repo",
        "spades",
        "--run-dir",
        str(run_dir),
        "--context-dir",
        str(REPO_ROOT),
        "--build-command",
        sys.executable,
        "-c",
        "print('prebuild ok')",
    )
    summary = run_json_command(str(BENCHMARK_SCRIPT), "summarize", "--run-dir", str(run_dir))

    spades_case = json.loads(run_dir.joinpath("cases", "spades", "summary.json").read_text(encoding="utf-8"))
    assert spades_case["image_build_success"] is True
    assert spades_case["benchmark_run_success"] is False
    assert spades_case["wdl_success"] is False
    assert spades_case["completed"] is False
    assert summary["status"] == "in_progress"


def test_benchmark_orchestrator_materializes_missing_copy_sources_from_repo_url(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = load_module(BENCHMARK_SCRIPT, "benchmark_workflow_source_materialization_test")
    context_dir = tmp_path / "context"
    context_dir.mkdir()
    dockerfile = tmp_path / "Dockerfile"
    dockerfile.write_text("FROM scratch\nCOPY tool_src/ /app/\n", encoding="utf-8")

    def fake_run(command, **kwargs):  # noqa: ANN001
        clone_dir = Path(command[-1])
        clone_dir.mkdir(parents=True)
        (clone_dir / "src").mkdir()
        (clone_dir / "src" / "main.py").write_text("print('ok')\n", encoding="utf-8")
        return subprocess.CompletedProcess(command, 0, stdout="cloned", stderr="")

    monkeypatch.setattr(module.subprocess, "run", fake_run)

    result = module._materialize_missing_docker_context_sources(
        dockerfile_path=dockerfile,
        context_dir=context_dir,
        case_manifest={"repo_name": "tool_src", "repo_url": "https://example.invalid/tool.git"},
        timeout_seconds=30,
    )

    assert (context_dir / "tool_src" / "src" / "main.py").exists()
    assert result[0]["returncode"] == 0
    assert result[-1]["source_root"] == "tool_src"


def test_benchmark_orchestrator_materializes_missing_files_into_existing_source_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = load_module(BENCHMARK_SCRIPT, "benchmark_workflow_existing_root_materialization_test")
    context_dir = tmp_path / "context"
    target_root = context_dir / "tool_src"
    target_root.mkdir(parents=True)
    (target_root / "Dockerfile").write_text("keep-local\n", encoding="utf-8")
    dockerfile = tmp_path / "Dockerfile"
    dockerfile.write_text("FROM scratch\nCOPY tool_src/ /app/\n", encoding="utf-8")

    def fake_run(command, **kwargs):  # noqa: ANN001
        clone_dir = Path(command[-1])
        clone_dir.mkdir(parents=True)
        (clone_dir / "Dockerfile").write_text("upstream-version\n", encoding="utf-8")
        (clone_dir / "src").mkdir()
        (clone_dir / "src" / "main.py").write_text("print('ok')\n", encoding="utf-8")
        return subprocess.CompletedProcess(command, 0, stdout="cloned", stderr="")

    monkeypatch.setattr(module.subprocess, "run", fake_run)

    result = module._materialize_missing_docker_context_sources(
        dockerfile_path=dockerfile,
        context_dir=context_dir,
        case_manifest={"repo_name": "tool_src", "repo_url": "https://example.invalid/tool.git"},
        timeout_seconds=30,
    )

    assert (target_root / "src" / "main.py").exists()
    assert (target_root / "Dockerfile").read_text(encoding="utf-8") == "keep-local\n"
    assert result[-1]["copied_files"] == 1


def test_benchmark_orchestrator_streams_build_log_while_command_is_running(tmp_path: Path) -> None:
    module = load_module(BENCHMARK_SCRIPT, "benchmark_workflow_streaming_log_test")
    log_path = tmp_path / "build.log"
    status_holder: dict[str, object] = {}

    def run_build() -> None:
        status_holder["status"] = module._run_build_command(
            [sys.executable, "-c", "import sys, time; print('phase1', flush=True); time.sleep(1.2); print('phase2', flush=True)"],
            cwd=tmp_path,
            log_path=log_path,
            timeout_seconds=10,
        )

    worker = threading.Thread(target=run_build)
    worker.start()

    deadline = time.time() + 5
    while time.time() < deadline:
        if log_path.exists() and "phase1" in log_path.read_text(encoding="utf-8"):
            break
        time.sleep(0.1)

    assert log_path.exists()
    assert "phase1" in log_path.read_text(encoding="utf-8")
    worker.join()
    assert status_holder["status"]["success"] is True
    assert "phase2" in log_path.read_text(encoding="utf-8")


def test_benchmark_orchestrator_init_supports_repo_subset(tmp_path: Path) -> None:
    run_dir = tmp_path / "benchmark-run"
    payload = run_json_command(
        str(BENCHMARK_SCRIPT),
        "init",
        "--task",
        "subset smoke",
        "--output-dir",
        str(run_dir),
        "--repos",
        "spades",
        "megahit",
    )

    assert payload["case_count"] == 2
    assert payload["case_order"] == ["spades", "megahit"]

    manifest = json.loads(run_dir.joinpath("manifest.json").read_text(encoding="utf-8"))
    assert manifest["case_order"] == ["spades", "megahit"]
    assert (run_dir / "cases" / "spades" / "manifest.json").exists()
    assert (run_dir / "cases" / "megahit" / "manifest.json").exists()
    assert not (run_dir / "cases" / "canu").exists()


def test_benchmark_orchestrator_init_supports_arbitrary_benchmark_root(tmp_path: Path) -> None:
    benchmark_root = tmp_path / "assets"
    alpha_dir = benchmark_root / "group" / "001_alpha"
    beta_dir = benchmark_root / "group" / "002_beta"
    alpha_dir.mkdir(parents=True)
    beta_dir.mkdir(parents=True)
    (alpha_dir / "inputs.json").write_text(json.dumps({"Alpha.reads": "shared/sample.fastq"}), encoding="utf-8")
    (beta_dir / "inputs.json").write_text(json.dumps({"Beta.reads": "shared/sample.fastq"}), encoding="utf-8")
    (alpha_dir / "alpha.wdl").write_text('workflow Alpha {}\nruntime { docker: "benchmark/alpha:test" }\n', encoding="utf-8")
    (beta_dir / "beta.wdl").write_text('workflow Beta {}\nruntime { docker: "benchmark/beta:test" }\n', encoding="utf-8")
    run_dir = tmp_path / "benchmark-run"

    payload = run_json_command(
        str(BENCHMARK_SCRIPT),
        "init",
        "--task",
        "arbitrary root smoke",
        "--benchmark-root",
        str(benchmark_root),
        "--output-dir",
        str(run_dir),
        "--repos",
        "alpha",
        "beta",
    )

    assert payload["case_order"] == ["alpha", "beta"]
    manifest = json.loads(run_dir.joinpath("manifest.json").read_text(encoding="utf-8"))
    assert manifest["benchmark_root"] == str(benchmark_root.resolve())
    assert manifest["cases"]["alpha"]["wdl_path"] == str((alpha_dir / "alpha.wdl").resolve())
    assert manifest["datasets"][manifest["cases"]["alpha"]["dataset_key"]]["shared_between"] == ["alpha", "beta"]


def test_benchmark_orchestrator_catalog_reports_unified_dataset_root() -> None:
    payload = run_json_command(str(BENCHMARK_SCRIPT), "catalog-datasets")
    assert payload["dataset_root"].endswith("experiments/benchmark/datasets")
    assert payload["downloads_root"].endswith("experiments/benchmark/datasets/downloads")
    assert "short-read-ecoli-srr001666" in payload["datasets"]
    assert "long-read-canu-pacbio" in payload["datasets"]
    assert "dockerfile_path" in payload["repo_cases"]["spades"]
    assert payload["repo_cases"]["canu"]["dataset_key"] == "long-read-canu-pacbio"
    assert payload["repo_cases"]["Flye"]["dataset_key"] == "long-read-canu-pacbio"
    assert "v-pipe" not in payload["repo_cases"]
    assert payload["repo_cases"]["spades"]["case_dir"].endswith("001_spades")


def test_benchmark_orchestrator_prepare_case_writes_dataset_selection(tmp_path: Path) -> None:
    run_dir = tmp_path / "benchmark-run"
    run_json_command(
        str(BENCHMARK_SCRIPT),
        "init",
        "--task",
        "selection smoke",
        "--output-dir",
        str(run_dir),
    )
    run_json_command(str(BENCHMARK_SCRIPT), "prepare-case", "--repo", "spades", "--run-dir", str(run_dir))

    selection = json.loads(run_dir.joinpath("cases", "spades", "dataset_selection.json").read_text(encoding="utf-8"))
    manifest = json.loads(run_dir.joinpath("cases", "spades", "manifest.json").read_text(encoding="utf-8"))
    assert selection["dataset_key"] == "short-read-ecoli-srr001666"
    assert manifest["selected_input_source"] in {"catalog.local_candidates", "downloads_root", "catalog_only", "shared_dataset_rewrite"}
    assert manifest["source_case_dir"].endswith("experiments/benchmark/新冠病毒组装/001_spades")
    assert manifest["source_wdl_path"].endswith("experiments/benchmark/新冠病毒组装/001_spades/spades.wdl")
    assert manifest["source_inputs_path"].endswith("experiments/benchmark/新冠病毒组装/001_spades/inputs.json")


def test_benchmark_orchestrator_prepare_case_rewrites_old_inputs_from_shared_dataset(tmp_path: Path) -> None:
    benchmark_root = tmp_path / "benchmark"
    case_dir = benchmark_root / "circrna" / "ACValidator"
    dataset_dir = benchmark_root / "datasets" / "downloads" / "circrna-hela-rnaser-paired"
    case_dir.mkdir(parents=True)
    dataset_dir.mkdir(parents=True)
    (dataset_dir / "README.md").write_text(
        "- `clean_test.sam`\n- `GRCh38.primary_assembly.fa`\n",
        encoding="utf-8",
    )
    (dataset_dir / "clean_test.sam").write_text("@HD\tVN:1.0\n", encoding="utf-8")
    (dataset_dir / "GRCh38.primary_assembly.fa").write_text(">chr1\nACGT\n", encoding="utf-8")
    (case_dir / "input.json").write_text(
        json.dumps(
            {
                "ACValidatorWorkflow.input_sam": "/old/path/clean_test.sam",
                "ACValidatorWorkflow.reference_fasta": "/old/path/ref.fa",
                "ACValidatorWorkflow.coordinate": "1:1-4",
            }
        ),
        encoding="utf-8",
    )
    (case_dir / "workflow.wdl").write_text(
        'workflow ACValidatorWorkflow {}\nruntime { docker: "benchmark/acvalidator:test" }\n',
        encoding="utf-8",
    )
    run_dir = tmp_path / "benchmark-run"

    run_json_command(
        str(BENCHMARK_SCRIPT),
        "init",
        "--task",
        "circRNA shared dataset rewrite",
        "--benchmark-root",
        str(benchmark_root / "circrna"),
        "--output-dir",
        str(run_dir),
        "--repos",
        "ACValidator",
    )
    run_json_command(str(BENCHMARK_SCRIPT), "prepare-case", "--repo", "ACValidator", "--run-dir", str(run_dir))
    ready = run_json_command(str(BENCHMARK_SCRIPT), "execution-ready", "--repo", "ACValidator", "--run-dir", str(run_dir))

    manifest = json.loads(run_dir.joinpath("cases", "ACValidator", "manifest.json").read_text(encoding="utf-8"))
    selection = json.loads(run_dir.joinpath("cases", "ACValidator", "dataset_selection.json").read_text(encoding="utf-8"))
    rewritten_inputs = json.loads(run_dir.joinpath("cases", "ACValidator", "wdl", "inputs.json").read_text(encoding="utf-8"))

    assert manifest["dataset_key"] == "circrna-hela-rnaser-paired"
    assert manifest["selected_input_source"] == "shared_dataset_rewrite"
    assert selection["selected_input_source"] == "shared_dataset_rewrite"
    assert manifest["selected_input_files"]["input_sam"].endswith("clean_test.sam")
    assert manifest["selected_input_files"]["reference_fasta"].endswith("GRCh38.primary_assembly.fa")
    assert rewritten_inputs["ACValidatorWorkflow.input_sam"].endswith("clean_test.sam")
    assert rewritten_inputs["ACValidatorWorkflow.reference_fasta"].endswith("GRCh38.primary_assembly.fa")
    assert ready["inputs_json_path"].endswith("cases/ACValidator/wdl/inputs.json")
    assert ready["inputs_ready"] is True


def test_benchmark_orchestrator_execution_ready_resolves_existing_paths(tmp_path: Path) -> None:
    run_dir = tmp_path / "benchmark-run"
    run_json_command(
        str(BENCHMARK_SCRIPT),
        "init",
        "--task",
        "execution-ready smoke",
        "--output-dir",
        str(run_dir),
    )
    run_json_command(str(BENCHMARK_SCRIPT), "prepare-case", "--repo", "spades", "--run-dir", str(run_dir))
    payload = run_json_command(str(BENCHMARK_SCRIPT), "execution-ready", "--repo", "spades", "--run-dir", str(run_dir))

    assert payload["ready"] is True
    assert str(payload["dockerfile_path"]).endswith(".workspaces/oneshot/spades/spades_Dockerfile")
    assert str(payload["wdl_path"]).endswith("experiments/benchmark/新冠病毒组装/001_spades/spades.wdl")
    assert str(payload["inputs_json_path"]).endswith("cases/spades/wdl/inputs.json")
    assert payload["runtime_image"] == "benchmark/spades:escape_bench"
    assert payload["inputs_ready"] is True


def test_benchmark_orchestrator_execution_ready_stays_false_when_rewritten_inputs_are_missing(
    tmp_path: Path,
) -> None:
    benchmark_root = tmp_path / "benchmark"
    case_dir = benchmark_root / "circrna" / "ACValidator"
    dataset_dir = benchmark_root / "datasets" / "downloads" / "circrna-hela-rnaser-paired"
    case_dir.mkdir(parents=True)
    dataset_dir.mkdir(parents=True)
    (dataset_dir / "README.md").write_text(
        "- `derived/alignments/*.sam`\n- `GRCh38.primary_assembly.fa`\n",
        encoding="utf-8",
    )
    (dataset_dir / "GRCh38.primary_assembly.fa").write_text(">chr1\nACGT\n", encoding="utf-8")
    (case_dir / "input.json").write_text(
        json.dumps(
            {
                "ACValidatorWorkflow.input_sam": "/old/path/clean_test.sam",
                "ACValidatorWorkflow.reference_fasta": "/old/path/ref.fa",
            }
        ),
        encoding="utf-8",
    )
    (case_dir / "workflow.wdl").write_text(
        'workflow ACValidatorWorkflow {}\nruntime { docker: "benchmark/acvalidator:test" }\n',
        encoding="utf-8",
    )
    run_dir = tmp_path / "benchmark-run"

    run_json_command(
        str(BENCHMARK_SCRIPT),
        "init",
        "--task",
        "circRNA missing derived inputs",
        "--benchmark-root",
        str(benchmark_root / "circrna"),
        "--output-dir",
        str(run_dir),
        "--repos",
        "ACValidator",
    )
    run_json_command(str(BENCHMARK_SCRIPT), "prepare-case", "--repo", "ACValidator", "--run-dir", str(run_dir))
    ready = run_json_command(str(BENCHMARK_SCRIPT), "execution-ready", "--repo", "ACValidator", "--run-dir", str(run_dir))

    assert ready["ready"] is False
    assert ready["inputs_ready"] is False
    assert "ACValidatorWorkflow.input_sam" in ready["missing_input_keys"]


def test_benchmark_orchestrator_help_loads_catalog_from_benchmark_tree() -> None:
    completed = subprocess.run(
        [sys.executable, str(BENCHMARK_SCRIPT), "--help"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0
    assert "catalog-datasets" in completed.stdout
    assert "execution-ready" in completed.stdout


def test_benchmark_orchestrator_preferred_image_ref_preserves_existing_tag(tmp_path: Path) -> None:
    module = load_module(BENCHMARK_SCRIPT, "benchmark_workflow_image_ref_test")
    case_dir = tmp_path / "case"
    (case_dir / "docker").mkdir(parents=True)
    (case_dir / "docker" / "request.json").write_text(
        json.dumps({"image_tag": "benchmark/megahit:escape_bench"}),
        encoding="utf-8",
    )

    image = module._preferred_image_ref(
        case_dir,
        {"runtime_image": "benchmark/megahit:escape_bench", "image_tag": "megahit-benchmark"},
    )

    assert image == "benchmark/megahit:escape_bench"


def test_benchmark_orchestrator_analyze_case_extracts_assembly_metrics(tmp_path: Path) -> None:
    run_dir = tmp_path / "benchmark-run"
    case_dir = run_dir / "cases" / "spades"
    case_dir.mkdir(parents=True)
    (case_dir / "docker").mkdir()
    (case_dir / "run").mkdir()
    (case_dir / "wdl").mkdir()
    (case_dir / "wdl" / "contigs.fasta").write_text(
        ">a\nAAAA\n>b\nAA\n>c\nAAAAAA\n",
        encoding="utf-8",
    )
    (case_dir / "wdl" / "status.json").write_text(
        json.dumps(
            {
                "success": True,
                "output_artifacts": [str(case_dir / "wdl" / "contigs.fasta")],
            }
        ),
        encoding="utf-8",
    )
    (case_dir / "docker" / "status.json").write_text(json.dumps({"success": True}), encoding="utf-8")
    (case_dir / "run" / "status.json").write_text(json.dumps({"success": True, "output_artifacts": []}), encoding="utf-8")
    run_dir.joinpath("manifest.json").write_text(
        json.dumps({"case_order": ["spades"]}),
        encoding="utf-8",
    )
    case_manifest = {
        "repo_name": "spades",
        "family": "short-read-assembly",
        "dataset_key": "short-read-ecoli-srr001666",
        "metric_keys": ["contig_count", "n50", "assembly_size"],
        "phase_status": {"analysis": "pending", "summary": "pending"},
        "local_result_candidates": [],
    }
    case_dir.joinpath("manifest.json").write_text(json.dumps(case_manifest), encoding="utf-8")

    payload = run_json_command(str(BENCHMARK_SCRIPT), "analyze-case", "--repo", "spades", "--run-dir", str(run_dir))
    assert payload["metrics"]["contig_count"] == 3
    assert payload["metrics"]["assembly_size"] == 12
    assert payload["metrics"]["n50"] == 6


def test_benchmark_orchestrator_repo_native_mounts_real_input_for_symlinked_dataset(tmp_path: Path) -> None:
    module = load_module(BENCHMARK_SCRIPT, "benchmark_workflow_symlink_test")
    real_dir = tmp_path / "real-data"
    real_dir.mkdir()
    real_fastq = real_dir / "reads.fastq"
    real_fastq.write_text("@r1\nACGT\n+\n!!!!\n", encoding="utf-8")
    downloads_dir = tmp_path / "downloads"
    downloads_dir.mkdir()
    symlink_fastq = downloads_dir / "reads.fastq"
    symlink_fastq.symlink_to(real_fastq)

    mounts, container_inputs = module._build_input_mounts({"reads": str(symlink_fastq)})

    assert mounts == ["-v", f"{real_dir}:/inputs/reads:ro"]
    assert container_inputs == {"reads": "/inputs/reads/reads.fastq"}


def test_benchmark_orchestrator_repo_native_shell_command_overrides_image_entrypoint(tmp_path: Path) -> None:
    module = load_module(BENCHMARK_SCRIPT, "benchmark_workflow_entrypoint_test")
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    reads_1 = data_dir / "reads_1.fastq.gz"
    reads_2 = data_dir / "reads_2.fastq.gz"
    reads_1.write_text("stub\n", encoding="utf-8")
    reads_2.write_text("stub\n", encoding="utf-8")
    work_dir = tmp_path / "run"
    work_dir.mkdir()

    command = module._build_repo_native_shell_command(
        image="megahit:latest",
        shell_command="megahit -1 <reads_1> -2 <reads_2> -o /work/repo_native_output -t 2",
        input_files={"reads_1": str(reads_1), "reads_2": str(reads_2)},
        work_dir=work_dir,
    )

    assert command[:6] == ["docker", "run", "--rm", "--user", "1000:1000", "-v"]
    assert "--entrypoint" in command
    assert "/bin/bash" in command
    assert str(work_dir) + ":/work" in command
    assert command[-2] == "-lc"
    assert command[-1] == "megahit -1 /inputs/reads_1/reads_1.fastq.gz -2 /inputs/reads_2/reads_2.fastq.gz -o /work/repo_native_output -t 2"
