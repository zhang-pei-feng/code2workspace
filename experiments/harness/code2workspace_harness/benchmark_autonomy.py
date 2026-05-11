"""Staged benchmark-autonomy experiments for local phase-1 workflow families."""

from __future__ import annotations

import json
import shutil
import subprocess
import time
import tomllib
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from experiments.harness.code2workspace_harness.core import repo_root, resolve_command_tokens, resolve_repo_path, utc_stamp


VALID_TOOL_POLICY = {"fixed", "agent-choice"}
VALID_INPUT_POLICY = {"fixed", "agent-choice"}
VALID_WDL_POLICY = {"fixed", "editable"}
VALID_WDL_EDIT_MODE = {"none", "run-copy", "direct-source"}

_CASE_INPUT_KEYS = {
    "spades": ("SpadesWorkflow.read1", "SpadesWorkflow.read2"),
    "megahit": ("MegahitAssembly.read1", "MegahitAssembly.read2"),
    "canu": ("CanuWorkflow.reads_fastq",),
    "Flye": ("FlyeAssembly.reads",),
}


@dataclass(frozen=True)
class BenchmarkAutonomyLevel:
    level_id: str
    tool_policy: str
    input_policy: str
    wdl_policy: str
    wdl_edit_mode: str
    optional_wdl_edit_modes: tuple[str, ...] = ()


@dataclass(frozen=True)
class BenchmarkAutonomyFamily:
    family_id: str
    label: str
    tool_candidates: tuple[str, ...]
    fixed_tools: tuple[str, ...]
    dataset_candidates: tuple[str, ...]
    fixed_dataset: str
    comparison_group: str


@dataclass(frozen=True)
class BenchmarkAutonomyExperiment:
    path: Path
    name: str
    benchmark_root: Path
    output_root: Path
    agent_command: tuple[str, ...]
    agent_base_args: tuple[str, ...]
    timeout_minutes: int
    report_md_name: str
    report_json_name: str
    families: dict[str, BenchmarkAutonomyFamily]
    levels: dict[str, BenchmarkAutonomyLevel]
    catalog: dict[str, Any]


@dataclass(frozen=True)
class PreparedToolCase:
    tool: str
    source_case_dir: Path
    staged_case_dir: Path
    staged_wdl_path: Path
    staged_inputs_path: Path
    expected_outputs: tuple[str, ...]


@dataclass(frozen=True)
class PreparedBenchmarkAutonomyRun:
    experiment: BenchmarkAutonomyExperiment
    family: BenchmarkAutonomyFamily
    level: BenchmarkAutonomyLevel
    run_root: Path
    workspace_root: Path
    benchmark_root: Path
    dataset_root: Path
    case_root: Path
    contract_path: Path
    prompt_path: Path
    stdout_path: Path
    stderr_path: Path
    transcript_path: Path
    report_md_path: Path
    report_json_path: Path
    summary_md_path: Path
    summary_json_path: Path
    fixed_tools: tuple[str, ...]
    tool_candidates: tuple[str, ...]
    dataset_candidates: tuple[str, ...]
    fixed_input_files: tuple[str, ...]
    candidate_input_files: tuple[str, ...]
    tool_cases: tuple[PreparedToolCase, ...]


@dataclass(frozen=True)
class BenchmarkAutonomyRunResult:
    prepared: PreparedBenchmarkAutonomyRun
    returncode: int
    elapsed_seconds: float
    summary_json_path: Path
    summary_md_path: Path


def _catalog_path(benchmark_root: Path) -> Path:
    return benchmark_root / "datasets" / "benchmark_catalog.json"


def _load_catalog(benchmark_root: Path) -> dict[str, Any]:
    return json.loads(_catalog_path(benchmark_root).read_text(encoding="utf-8"))


def _load_level(level_id: str, payload: dict[str, Any]) -> BenchmarkAutonomyLevel:
    tool_policy = str(payload["tool_policy"])
    input_policy = str(payload["input_policy"])
    wdl_policy = str(payload["wdl_policy"])
    wdl_edit_mode = str(payload["wdl_edit_mode"])
    if tool_policy not in VALID_TOOL_POLICY:
        raise ValueError(f"invalid tool_policy for {level_id}: {tool_policy}")
    if input_policy not in VALID_INPUT_POLICY:
        raise ValueError(f"invalid input_policy for {level_id}: {input_policy}")
    if wdl_policy not in VALID_WDL_POLICY:
        raise ValueError(f"invalid wdl_policy for {level_id}: {wdl_policy}")
    if wdl_edit_mode not in VALID_WDL_EDIT_MODE:
        raise ValueError(f"invalid wdl_edit_mode for {level_id}: {wdl_edit_mode}")
    optional_modes = tuple(str(item) for item in payload.get("optional_wdl_edit_modes", []))
    invalid = [mode for mode in optional_modes if mode not in VALID_WDL_EDIT_MODE or mode == "none"]
    if invalid:
        raise ValueError(f"invalid optional_wdl_edit_modes for {level_id}: {invalid}")
    return BenchmarkAutonomyLevel(
        level_id=level_id,
        tool_policy=tool_policy,
        input_policy=input_policy,
        wdl_policy=wdl_policy,
        wdl_edit_mode=wdl_edit_mode,
        optional_wdl_edit_modes=optional_modes,
    )


def _load_family(family_id: str, payload: dict[str, Any], *, catalog: dict[str, Any]) -> BenchmarkAutonomyFamily:
    tool_candidates = tuple(str(item) for item in payload["tool_candidates"])
    fixed_tools = tuple(str(item) for item in payload.get("fixed_tools", tool_candidates))
    dataset_candidates = tuple(str(item) for item in payload["dataset_candidates"])
    fixed_dataset = str(payload.get("fixed_dataset", dataset_candidates[0]))

    for tool in tool_candidates:
        case_payload = catalog["repo_cases"][tool]
        if str(case_payload["family"]) != family_id:
            raise ValueError(f"tool {tool} does not belong to family {family_id}")
    for dataset_key in dataset_candidates:
        dataset_payload = catalog["datasets"][dataset_key]
        if str(dataset_payload["family"]) != family_id:
            raise ValueError(f"dataset {dataset_key} does not belong to family {family_id}")

    return BenchmarkAutonomyFamily(
        family_id=family_id,
        label=str(payload["label"]),
        tool_candidates=tool_candidates,
        fixed_tools=fixed_tools,
        dataset_candidates=dataset_candidates,
        fixed_dataset=fixed_dataset,
        comparison_group=str(payload["comparison_group"]),
    )


def load_benchmark_autonomy_experiment(path: Path) -> BenchmarkAutonomyExperiment:
    """Load the phase-1 benchmark autonomy experiment config."""
    payload = tomllib.loads(path.read_text(encoding="utf-8"))
    experiment_payload = payload["experiment"]
    benchmark_root = resolve_repo_path(str(experiment_payload["benchmark_root"]))
    catalog = _load_catalog(benchmark_root)
    agent_payload = payload.get("agent", {})
    if not agent_payload.get("command"):
        raise ValueError("benchmark autonomy config requires [agent].command")
    levels = {
        level_id: _load_level(level_id, level_payload)
        for level_id, level_payload in payload.get("levels", {}).items()
    }
    if not levels:
        raise ValueError("benchmark autonomy config requires at least one [levels.<id>] block")
    families = {
        str(item["family_id"]): _load_family(str(item["family_id"]), item, catalog=catalog)
        for item in payload.get("families", [])
    }
    if not families:
        raise ValueError("benchmark autonomy config requires at least one [[families]] block")
    return BenchmarkAutonomyExperiment(
        path=path,
        name=str(experiment_payload["name"]),
        benchmark_root=benchmark_root,
        output_root=resolve_repo_path(str(experiment_payload["output_root"])),
        agent_command=resolve_command_tokens([str(token) for token in agent_payload["command"]]),
        agent_base_args=tuple(str(token) for token in agent_payload.get("base_args", [])),
        timeout_minutes=int(agent_payload.get("timeout_minutes", 120)),
        report_md_name=str(experiment_payload.get("report_md_name", "benchmark_report.md")),
        report_json_name=str(experiment_payload.get("report_json_name", "benchmark_report.json")),
        families=families,
        levels=levels,
        catalog=catalog,
    )


def _copy_dataset_file(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if source.is_dir():
        if destination.exists():
            shutil.rmtree(destination)
        shutil.copytree(source, destination)
        return
    shutil.copy2(source, destination)


def _resolve_dataset_sources(
    experiment: BenchmarkAutonomyExperiment,
    dataset_key: str,
    *,
    target_dir: Path,
) -> dict[str, str]:
    dataset_payload = experiment.catalog["datasets"][dataset_key]
    download_dir = experiment.benchmark_root / "datasets" / "downloads" / dataset_key
    selected: dict[str, str] = {}
    for entry in dataset_payload.get("files", []):
        logical_name = str(entry["logical_name"])
        filename = str(entry["filename"])
        download_candidate = download_dir / filename
        if download_candidate.exists():
            staged_path = target_dir / dataset_key / filename
            _copy_dataset_file(download_candidate, staged_path)
            selected[logical_name] = str(staged_path)
            continue

    if len(selected) == len(dataset_payload.get("files", [])):
        return selected

    local_candidates = [resolve_repo_path(str(item)) for item in dataset_payload.get("local_candidates", [])]
    staged_dataset_dir = target_dir / dataset_key
    if len(dataset_payload.get("files", [])) == 1 and local_candidates:
        source = next((candidate for candidate in local_candidates if candidate.exists()), None)
        if source is not None:
            filename = str(dataset_payload["files"][0]["filename"])
            staged_path = staged_dataset_dir / filename
            _copy_dataset_file(source, staged_path)
            selected[str(dataset_payload["files"][0]["logical_name"])] = str(staged_path)
            return selected

    existing_candidates = [candidate for candidate in local_candidates if candidate.exists()]
    logical_names = [str(entry["logical_name"]) for entry in dataset_payload.get("files", [])]
    for logical_name, source in zip(logical_names, existing_candidates, strict=False):
        staged_path = staged_dataset_dir / source.name
        _copy_dataset_file(source, staged_path)
        selected[logical_name] = str(staged_path)

    if len(selected) != len(dataset_payload.get("files", [])):
        raise FileNotFoundError(f"could not stage complete dataset {dataset_key}")
    return selected


def _rewrite_inputs(tool: str, *, source_inputs: Path, destination_inputs: Path, selected_files: dict[str, str]) -> None:
    payload = json.loads(source_inputs.read_text(encoding="utf-8"))
    keys = _CASE_INPUT_KEYS[tool]
    logical_names = tuple(selected_files)
    for wdl_key, logical_name in zip(keys, logical_names, strict=True):
        payload[wdl_key] = selected_files[logical_name]
    destination_inputs.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _copy_case_directory(
    experiment: BenchmarkAutonomyExperiment,
    *,
    tool: str,
    case_root: Path,
    selected_files: dict[str, str],
) -> PreparedToolCase:
    case_payload = experiment.catalog["repo_cases"][tool]
    source_case_dir = resolve_repo_path(str(case_payload["case_dir"]))
    staged_case_dir = case_root / source_case_dir.name
    staged_case_dir.mkdir(parents=True, exist_ok=True)

    source_wdl_path = resolve_repo_path(str(case_payload["wdl_path"]))
    source_inputs_path = resolve_repo_path(str(case_payload["inputs_path"]))
    staged_wdl_path = staged_case_dir / source_wdl_path.name
    staged_inputs_path = staged_case_dir / source_inputs_path.name
    shutil.copy2(source_wdl_path, staged_wdl_path)
    _rewrite_inputs(tool, source_inputs=source_inputs_path, destination_inputs=staged_inputs_path, selected_files=selected_files)
    return PreparedToolCase(
        tool=tool,
        source_case_dir=source_case_dir,
        staged_case_dir=staged_case_dir,
        staged_wdl_path=staged_wdl_path,
        staged_inputs_path=staged_inputs_path,
        expected_outputs=tuple(str(item) for item in case_payload.get("expected_outputs", [])),
    )


def _workspace_benchmark_paths(run_root: Path) -> tuple[Path, Path, Path]:
    workspace_root = run_root / "workspace"
    benchmark_root = workspace_root / "experiments" / "benchmark"
    dataset_root = benchmark_root / "datasets" / "downloads"
    case_root = benchmark_root / "新冠病毒组装"
    return workspace_root, dataset_root, case_root


def _write_workspace_marker(workspace_root: Path) -> None:
    marker = workspace_root / ".code2workspace" / "project-root.txt"
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(f"{repo_root()}\n", encoding="utf-8")


def _write_subset_catalog(
    experiment: BenchmarkAutonomyExperiment,
    family: BenchmarkAutonomyFamily,
    *,
    benchmark_root: Path,
) -> None:
    benchmark_root.mkdir(parents=True, exist_ok=True)
    datasets = {key: experiment.catalog["datasets"][key] for key in family.dataset_candidates}
    repo_cases = {tool: experiment.catalog["repo_cases"][tool] for tool in family.tool_candidates}
    payload = {
        "dataset_root": "experiments/benchmark/datasets",
        "downloads_root": "experiments/benchmark/datasets/downloads",
        "datasets": datasets,
        "repo_cases": repo_cases,
    }
    catalog_path = benchmark_root / "datasets" / "benchmark_catalog.json"
    catalog_path.parent.mkdir(parents=True, exist_ok=True)
    catalog_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def prepare_benchmark_autonomy_run(
    *,
    experiment: BenchmarkAutonomyExperiment,
    family_id: str,
    level_id: str,
    output_root: Path | None = None,
) -> PreparedBenchmarkAutonomyRun:
    """Stage one isolated family/level run."""
    family = experiment.families[family_id]
    level = experiment.levels[level_id]
    base_output_root = output_root or experiment.output_root
    run_root = base_output_root / experiment.name / utc_stamp() / level.level_id / family.family_id
    workspace_root, dataset_root, case_root = _workspace_benchmark_paths(run_root)
    benchmark_root = workspace_root / "experiments" / "benchmark"
    agent_output_root = run_root / "agent_output"
    logs_dir = run_root / "logs"
    agent_output_root.mkdir(parents=True, exist_ok=True)
    logs_dir.mkdir(parents=True, exist_ok=True)
    _write_workspace_marker(workspace_root)
    _write_subset_catalog(experiment, family, benchmark_root=benchmark_root)

    selected_files = _resolve_dataset_sources(
        experiment,
        family.fixed_dataset,
        target_dir=dataset_root,
    )
    fixed_input_files = tuple(selected_files.values())
    candidate_input_files = tuple(
        str(path)
        for path in sorted((dataset_root / family.fixed_dataset).rglob("*"))
        if path.is_file()
    )
    tool_cases = tuple(
        _copy_case_directory(
            experiment,
            tool=tool,
            case_root=case_root,
            selected_files=selected_files,
        )
        for tool in family.tool_candidates
    )

    contract = {
        "family_id": family.family_id,
        "level_id": level.level_id,
        "tool_policy": level.tool_policy,
        "input_policy": level.input_policy,
        "wdl_policy": level.wdl_policy,
        "wdl_edit_mode": level.wdl_edit_mode,
        "fresh_run_required": True,
        "comparison_group": family.comparison_group,
        "tool_candidates": list(family.tool_candidates),
        "fixed_tools": list(family.fixed_tools),
        "dataset_candidates": list(family.dataset_candidates),
        "fixed_dataset": family.fixed_dataset,
        "fixed_input_files": list(fixed_input_files),
        "case_dirs": {item.tool: str(item.staged_case_dir) for item in tool_cases},
        "wdl_source": {item.tool: str(item.staged_wdl_path) for item in tool_cases},
        "expected_outputs": {item.tool: list(item.expected_outputs) for item in tool_cases},
    }
    contract_path = run_root / "contract.json"
    contract_path.parent.mkdir(parents=True, exist_ok=True)
    contract_path.write_text(json.dumps(contract, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    return PreparedBenchmarkAutonomyRun(
        experiment=experiment,
        family=family,
        level=level,
        run_root=run_root,
        workspace_root=workspace_root,
        benchmark_root=benchmark_root,
        dataset_root=dataset_root,
        case_root=case_root,
        contract_path=contract_path,
        prompt_path=run_root / "prompt.txt",
        stdout_path=logs_dir / "stdout.log",
        stderr_path=logs_dir / "stderr.log",
        transcript_path=logs_dir / "transcript.log",
        report_md_path=agent_output_root / experiment.report_md_name,
        report_json_path=agent_output_root / experiment.report_json_name,
        summary_md_path=run_root / "summary.md",
        summary_json_path=run_root / "summary.json",
        fixed_tools=family.fixed_tools,
        tool_candidates=family.tool_candidates,
        dataset_candidates=family.dataset_candidates,
        fixed_input_files=fixed_input_files,
        candidate_input_files=candidate_input_files,
        tool_cases=tool_cases,
    )


def build_benchmark_autonomy_prompt(prepared: PreparedBenchmarkAutonomyRun) -> str:
    """Build the agent task prompt for one family/level run."""
    lines = [
        "You are running one staged benchmark-autonomy experiment.",
        "",
        f"- family_id: `{prepared.family.family_id}`",
        f"- level_id: `{prepared.level.level_id}`",
        f"- workspace_root: `{prepared.workspace_root}`",
        f"- benchmark_root: `{prepared.benchmark_root}`",
        f"- contract_json: `{prepared.contract_path}`",
        "",
        "Rules:",
        "1. Treat this as a fresh run and do not rely on historical outputs outside the staged workspace.",
        "2. Work only with the staged benchmark assets under the workspace-local `experiments/benchmark` tree.",
        "3. Write the machine-readable report before optional extra retries.",
        f"4. Write JSON report to `{prepared.report_json_path}`.",
        f"5. Write Markdown report to `{prepared.report_md_path}`.",
        "6. The JSON report must include selected_tools, selected_inputs, wdl_modified, wdl_changes, tool_outcomes, comparison_summary, and blockers.",
        "",
    ]

    if prepared.level.tool_policy == "fixed":
        lines.extend(
            [
                f"This level uses a fixed tool set: {', '.join(prepared.fixed_tools)}.",
                "Use the fixed tool set exactly as staged.",
            ]
        )
    else:
        lines.append(
            f"For this level, choose one or more tools from the candidate list: {', '.join(prepared.tool_candidates)}."
        )

    if prepared.level.input_policy == "fixed":
        lines.extend(
            [
                "This level uses fixed input files.",
                f"Use these fixed input files exactly: {', '.join(prepared.fixed_input_files)}.",
            ]
        )
    else:
        lines.extend(
            [
                "For this level, choose the exact input files from the staged dataset directory.",
                f"Candidate dataset directory: `{prepared.dataset_root / prepared.family.fixed_dataset}`.",
            ]
        )

    if prepared.level.wdl_policy == "fixed":
        lines.append("Do not modify the staged WDL files.")
    else:
        lines.append("You may modify the staged WDL copies if needed to make the run honest and executable.")
        lines.append("The default edit mode is run-local copy; do not modify original source WDL files unless you explicitly document a direct-source subvariant.")

    lines.extend(
        [
            "",
            "Expected staged case directories:",
            *[f"- `{tool_case.tool}` -> `{tool_case.staged_case_dir}`" for tool_case in prepared.tool_cases],
            "",
            "The Markdown report must include:",
            "- level summary",
            "- selected tools",
            "- selected inputs",
            "- whether WDL changed",
            "- success/failure table",
            "- shared-dataset comparison inside this family",
            "- blockers",
            "",
            "The machine-readable JSON report should use one tool_outcomes item per attempted or skipped tool with:",
            "- tool",
            "- completion_state",
            "- artifact_paths",
            "- failure_category",
            "- notes",
        ]
    )
    return "\n".join(lines) + "\n"


def _count_occurrences(text: str, needle: str) -> int:
    return text.count(needle)


def _categorize_failure(text: str) -> str:
    lowered = text.lower()
    if "timed out" in lowered:
        return "timeout"
    if "unknown workflow input" in lowered or "required workflow input" in lowered or "cannot coerce" in lowered:
        return "WDL interface error"
    if "workflow failed" in lowered or "miniwdl" in lowered or "wdl" in lowered:
        return "WDL execution/runtime error"
    if "no such file" in lowered or "not found" in lowered or "missing" in lowered or "command not found" in lowered:
        if "input" in lowered or "fastq" in lowered or "fasta" in lowered:
            return "input selection error"
        return "environment/missing dependency"
    if "output" in lowered or "artifact" in lowered:
        return "output validation failure"
    return "environment/missing dependency"


def _normalize_tool_outcomes(
    prepared: PreparedBenchmarkAutonomyRun,
    *,
    agent_report: dict[str, Any] | None,
    combined_logs: str,
) -> list[dict[str, Any]]:
    default_tools = list(prepared.fixed_tools if prepared.level.tool_policy == "fixed" else prepared.tool_candidates)
    report_outcomes = agent_report.get("tool_outcomes", []) if agent_report else []
    normalized: list[dict[str, Any]] = []
    if report_outcomes:
        for item in report_outcomes:
            completion_state = str(item.get("completion_state", "failed"))
            failure_category = item.get("failure_category")
            if not failure_category and completion_state not in {"completed", "succeeded", "success"}:
                failure_category = _categorize_failure(combined_logs)
            normalized.append(
                {
                    "tool": str(item["tool"]),
                    "completion_state": completion_state,
                    "artifact_paths": [str(path) for path in item.get("artifact_paths", [])],
                    "failure_category": failure_category,
                    "notes": item.get("notes"),
                }
            )
        return normalized

    fallback_category = _categorize_failure(combined_logs)
    for tool in default_tools:
        normalized.append(
            {
                "tool": tool,
                "completion_state": "failed",
                "artifact_paths": [],
                "failure_category": fallback_category,
                "notes": "No agent report was written; synthesized from process logs.",
            }
        )
    return normalized


def _summary_markdown(payload: dict[str, Any]) -> str:
    def render_item(value: Any) -> str:
        if isinstance(value, str):
            return value
        return json.dumps(value, ensure_ascii=False, sort_keys=True)

    selected_tools = payload["selected_tools"]
    selected_tools_text = ", ".join(render_item(item) for item in selected_tools) if isinstance(selected_tools, list) else render_item(selected_tools)
    selected_inputs = payload["selected_inputs"]

    lines = [
        "# Benchmark Autonomy Summary",
        "",
        f"- family_id: `{payload['family_id']}`",
        f"- level_id: `{payload['level_id']}`",
        f"- selected_tools: `{selected_tools_text or 'none'}`",
        f"- wdl_modified: `{payload['wdl_modified']}`",
        f"- elapsed_seconds: `{payload['durations']['wall_seconds']}`",
        f"- user_report_path: `{payload['user_report_path']}`",
        "",
        "## Selected Inputs",
        "",
    ]
    if isinstance(selected_inputs, list):
        lines.extend(f"- `{render_item(item)}`" for item in selected_inputs or ["(none)"])
    else:
        lines.append(f"- `{render_item(selected_inputs)}`")
    lines.extend(["", "## Tool Outcomes", ""])
    for item in payload["tool_outcomes"]:
        lines.append(
            f"- `{item['tool']}`: state=`{item['completion_state']}`, failure_category=`{item['failure_category']}`, artifacts=`{len(item['artifact_paths'])}`"
        )
    comparison_summary = payload["comparison_summary"]
    lines.extend(["", "## Comparison", "", render_item(comparison_summary), "", "## Blockers", ""])
    lines.extend(f"- {render_item(item)}" for item in payload["blockers"] or ["(none)"])
    return "\n".join(lines) + "\n"


def run_benchmark_autonomy_case(prepared: PreparedBenchmarkAutonomyRun) -> BenchmarkAutonomyRunResult:
    """Run one prepared family/level case through the non-interactive CLI."""
    prompt = build_benchmark_autonomy_prompt(prepared)
    prepared.prompt_path.write_text(prompt, encoding="utf-8")
    command = [
        *prepared.experiment.agent_command,
        "-n",
        prompt,
        *prepared.experiment.agent_base_args,
    ]

    started = time.time()
    completed = subprocess.run(
        command,
        cwd=prepared.workspace_root,
        capture_output=True,
        text=True,
        timeout=prepared.experiment.timeout_minutes * 60,
        check=False,
    )
    elapsed_seconds = round(time.time() - started, 3)
    prepared.stdout_path.write_text(completed.stdout, encoding="utf-8")
    prepared.stderr_path.write_text(completed.stderr, encoding="utf-8")
    combined_logs = completed.stdout + completed.stderr
    prepared.transcript_path.write_text(combined_logs, encoding="utf-8")

    agent_report = None
    if prepared.report_json_path.exists():
        agent_report = json.loads(prepared.report_json_path.read_text(encoding="utf-8"))

    selected_tools = list(agent_report.get("selected_tools", [])) if agent_report else []
    if not selected_tools and prepared.level.tool_policy == "fixed":
        selected_tools = list(prepared.fixed_tools)
    selected_inputs: Any = agent_report.get("selected_inputs", []) if agent_report else []
    if not selected_inputs and prepared.level.input_policy == "fixed":
        selected_inputs = list(prepared.fixed_input_files)
    tool_outcomes = _normalize_tool_outcomes(prepared, agent_report=agent_report, combined_logs=combined_logs)
    blockers = list(agent_report.get("blockers", [])) if agent_report else []
    if not blockers and completed.returncode != 0:
        blockers = [combined_logs.strip() or "The agent process failed without a detailed report."]
    payload = {
        "family_id": prepared.family.family_id,
        "level_id": prepared.level.level_id,
        "selected_tools": selected_tools,
        "selected_inputs": selected_inputs,
        "wdl_modified": bool(agent_report.get("wdl_modified", False)) if agent_report else False,
        "wdl_changes": [str(item) for item in agent_report.get("wdl_changes", [])] if agent_report else [],
        "tool_outcomes": tool_outcomes,
        "comparison_summary": (
            agent_report.get("comparison_summary")
            if agent_report and agent_report.get("comparison_summary") is not None
            else f"Shared-dataset comparison group: {prepared.family.comparison_group}."
        ),
        "blockers": blockers,
        "durations": {
            "wall_seconds": elapsed_seconds,
        },
        "cost_metrics": {
            "command_count": _count_occurrences(combined_logs, "Calling tool:"),
            "execute_command_count": _count_occurrences(combined_logs, "Calling tool: execute"),
            "docker_command_count": _count_occurrences(combined_logs.lower(), "docker"),
            "wdl_command_count": _count_occurrences(combined_logs.lower(), "miniwdl"),
            "model_call_count": None,
            "token_usage": None,
        },
        "process_returncode": completed.returncode,
        "user_report_path": str(prepared.report_md_path if prepared.report_md_path.exists() else prepared.summary_md_path),
        "agent_report_json_path": str(prepared.report_json_path) if prepared.report_json_path.exists() else None,
    }
    prepared.summary_json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    prepared.summary_md_path.write_text(_summary_markdown(payload), encoding="utf-8")
    return BenchmarkAutonomyRunResult(
        prepared=prepared,
        returncode=int(completed.returncode),
        elapsed_seconds=elapsed_seconds,
        summary_json_path=prepared.summary_json_path,
        summary_md_path=prepared.summary_md_path,
    )


def run_benchmark_autonomy_matrix(
    experiment: BenchmarkAutonomyExperiment,
    *,
    family_ids: tuple[str, ...] | None = None,
    level_ids: tuple[str, ...] | None = None,
    output_root: Path | None = None,
) -> list[BenchmarkAutonomyRunResult]:
    """Run one or more family/level combinations."""
    selected_families = family_ids or tuple(experiment.families)
    selected_levels = level_ids or tuple(experiment.levels)
    results: list[BenchmarkAutonomyRunResult] = []
    for family_id in selected_families:
        for level_id in selected_levels:
            prepared = prepare_benchmark_autonomy_run(
                experiment=experiment,
                family_id=family_id,
                level_id=level_id,
                output_root=output_root,
            )
            results.append(run_benchmark_autonomy_case(prepared))
    return results


def validate_benchmark_autonomy_experiment(experiment: BenchmarkAutonomyExperiment) -> dict[str, Any]:
    """Return a concise validation payload for CLI use."""
    return {
        "name": experiment.name,
        "benchmark_root": str(experiment.benchmark_root),
        "output_root": str(experiment.output_root),
        "families": {
            family_id: asdict(family)
            for family_id, family in experiment.families.items()
        },
        "levels": {
            level_id: asdict(level)
            for level_id, level in experiment.levels.items()
        },
    }
