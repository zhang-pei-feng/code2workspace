"""Capability-to-tool and guidance registry for the supervisor runtime."""

from __future__ import annotations

from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import Literal

from code2workspace.orchestration_runtime import CapabilityBundle
from code2workspace_cli.generic_experience_store import (
    generated_guidance_path,
    retrieve_experience_guidance_lines,
)

ImplementationKind = Literal["tool", "guidance", "hybrid"]


@dataclass(frozen=True, slots=True)
class CapabilitySpec:
    """Execution contract for one capability bundle."""

    name: CapabilityBundle
    implementation_kind: ImplementationKind
    tool_names: tuple[str, ...]
    summary: str


CAPABILITY_REGISTRY: dict[CapabilityBundle, CapabilitySpec] = {
    "repo_fetch": CapabilitySpec(
        name="repo_fetch",
        implementation_kind="hybrid",
        tool_names=("execute", "read_file", "ls", "glob"),
        summary="Repository fetch and source-tree inspection via shell/file tools.",
    ),
    "docker_build_run": CapabilitySpec(
        name="docker_build_run",
        implementation_kind="hybrid",
        tool_names=("execute", "read_file", "write_file", "edit_file", "ls"),
        summary="Container image build, runtime checks, and log capture.",
    ),
    "wdl_run": CapabilitySpec(
        name="wdl_run",
        implementation_kind="hybrid",
        tool_names=("execute", "read_file", "write_file", "edit_file", "ls"),
        summary="WDL/Cromwell preparation, execution, and validation.",
    ),
    "data_filter": CapabilitySpec(
        name="data_filter",
        implementation_kind="hybrid",
        tool_names=("execute", "read_file", "write_file"),
        summary="Data selection, reshaping, and extraction.",
    ),
    "operator_filter": CapabilitySpec(
        name="operator_filter",
        implementation_kind="guidance",
        tool_names=("read_file", "execute"),
        summary="Tool/operator selection based on task constraints.",
    ),
    "metric_compute": CapabilitySpec(
        name="metric_compute",
        implementation_kind="hybrid",
        tool_names=("execute", "read_file", "write_file"),
        summary="Metric calculation and result-table generation.",
    ),
    "summarize": CapabilitySpec(
        name="summarize",
        implementation_kind="guidance",
        tool_names=("read_file", "write_file"),
        summary="User-facing summary, synthesis, and closeout text.",
    ),
    "validate": CapabilitySpec(
        name="validate",
        implementation_kind="guidance",
        tool_names=("read_file", "ls", "execute"),
        summary="Artifact, log, and prerequisite validation.",
    ),
    "plan": CapabilitySpec(
        name="plan",
        implementation_kind="guidance",
        tool_names=("read_file", "write_file"),
        summary="Planning, decomposition, and execution-order decisions.",
    ),
    "task_manage": CapabilitySpec(
        name="task_manage",
        implementation_kind="guidance",
        tool_names=("read_file", "write_file", "ls"),
        summary="Run bookkeeping, artifact organization, and task-state transitions.",
    ),
    "web_search": CapabilitySpec(
        name="web_search",
        implementation_kind="tool",
        tool_names=("web_search",),
        summary="Search the web for targeted sources and evidence.",
    ),
    "web_fetch": CapabilitySpec(
        name="web_fetch",
        implementation_kind="tool",
        tool_names=("fetch_url",),
        summary="Fetch and inspect a known web resource directly.",
    ),
    "db_access": CapabilitySpec(
        name="db_access",
        implementation_kind="hybrid",
        tool_names=("execute", "read_file"),
        summary="Structured local database or dataset access.",
    ),
    "api_call": CapabilitySpec(
        name="api_call",
        implementation_kind="hybrid",
        tool_names=("fetch_url", "execute"),
        summary="Structured external or local API calls.",
    ),
}


_NODE_GUIDANCE_DEFAULTS: dict[str, tuple[str, ...]] = {
    "register": (
        "This node is registration-first: confirm staged assets, enumerate tool/case pairs, and separate light missing assets from hard blockers.",
        "If lightweight planning artifacts are missing, describe the minimum artifacts required before execution and record them explicitly.",
    ),
    "inspect": (
        "If the task names a repository URL and the source tree is absent, materialize the repository into the current workspace before deeper inspection.",
        "If the repository is already materialized in the current workspace, inspect that local copy directly instead of re-cloning it.",
        "Prefer concrete build/test entrypoints and bundled datasets over speculative assumptions.",
        "Produce an explicit dependency-risk picture for downstream nodes: note whether the repo has a documented official image, whether it appears self-contained, whether it requires public or private reference data, and whether scripts contain hard-coded author-machine paths or missing functions/resources.",
        "If the task requires real data validation and the repository does not bundle a suitable real dataset, explicitly record that gap for downstream nodes and prefer a small public real dataset with clear provenance over any synthetic substitute.",
    ),
    "build": (
        "If the task requires a container validation on real data, do not satisfy that requirement with synthetic or generated reads.",
        "When the repository lacks bundled real data, you may fetch a small public real dataset with source provenance, save it into the workspace, and reuse the same dataset for both Docker and WDL validation.",
        "Start by consuming the latest inspect artifact from the current run directory instead of re-discovering the repository from scratch.",
        "Within your first actions, perform at least one concrete observable step toward the Docker path such as reading the inspect output, checking for an existing Dockerfile, verifying a documented image, or sketching the smallest build plan in a workspace artifact before running commands.",
        "Use this dependency strategy order unless hard evidence says otherwise: first verify and reuse any repository-documented official image; second build a thin wrapper image around that image if the repo needs local files or a shell-compatible entrypoint; third attempt a full environment rebuild from scratch only when the first two options are unavailable or clearly insufficient.",
        "If you detect private-only references, author-machine absolute paths, missing helper functions/resources, or a dependency solve that is disproportionately expensive for the expected payoff, stop escalating rebuild effort and return a concrete blocker instead of grinding through speculative environment repair.",
    ),
    "retry_build": (
        "Keep retry_build narrow: repair the concrete Docker/runtime blocker first, then complete the smallest missing real-data validation step if it is still required.",
        "Do not generate synthetic reads to satisfy a real-data task requirement; use a real external dataset with recorded provenance or return partial.",
        "Keep the same dependency strategy order on retry: official image first, thin wrapper second, full rebuild last.",
        "If retry evidence shows the rebuild path is dominated by slow dependency solving or private/hard-coded prerequisites, stop and return a blocker rather than doubling down on the same environment reconstruction path.",
    ),
    "init_report": (
        "Keep this node narrow: create request notes, report contract, and lane scaffolding only.",
        "Do not spend this node on heavy research; return as soon as initialization artifacts exist.",
    ),
    "compose_report": (
        "Compose only from lane evidence already gathered or explicitly note which lanes remain incomplete.",
        "For report and assessment deliverables, include a compact evidence-source note that names the main source categories and distinguishes direct evidence from inferred or proxy evidence.",
    ),
    "monitoring_lane": (
        "Focus on official surveillance and operational monitoring only.",
        "Stop once the lane has enough source-backed monitoring evidence for the report.",
    ),
    "local_data_lane": (
        "Focus on structured local data, APIs, registries, or databases relevant to the report topic.",
        "Split local evidence into existing_data already available locally and computed_data that requires selecting a local operator plus dataset/input bundle and running it.",
    ),
    "literature_lane": (
        "Focus on literature, preprints, technical analyses, and primary-source web material.",
    ),
    "init_generic": (
        "Keep this node narrow: define the generic delivery contract, pick the next 1-3 bounded worker units, and record a serial next-step plan by default.",
        "Prefer a gather evidence -> check what is missing -> gather targeted evidence if needed -> summarize flow; use parallel lanes only when independent branches are clearly necessary.",
        "Do not spend this node on broad execution; stop once the worker split and serial plan are concrete enough for the next round.",
        "If the generic task needs prediction or calculation, plan a worker that searches operator_store, selects a compatible dataset/input bundle, and runs the chosen operator to produce computed evidence.",
    ),
    "compose_generic": (
        "Compose a normal long-form user-facing answer from worker outputs; avoid turning the result into a formal report artifact unless the user explicitly asked for one.",
        "For judgment or assessment-style answers, briefly state where the evidence came from and which parts are direct evidence, inferred evidence, or unresolved gaps.",
    ),
    "worker_context": (
        "Focus on constraints, evidence, repository facts, or source-backed context needed for the generic task.",
        "When gathering evidence for a judgment task, record source categories, source dates when relevant, and whether each source directly supports the claim or only provides proxy context.",
        "For generic prediction or calculation tasks, check local operator stores before broad external discovery; if a value must be computed, retrieve the operator and dataset/input bundle and run the concrete local path when available.",
    ),
    "worker_solution": (
        "Focus on implementation, execution, repair, or solution design needed for the generic task.",
    ),
    "benchmark_case": (
        "If the registered benchmark artifacts already define the exact docker/WDL launch command and inputs, execute that concrete path first instead of re-planning.",
        "After the command exits, inspect the expected output directory and return JSON immediately once the primary assembly outputs and logs are present.",
    ),
    "wdl": (
        "Treat the repository's principal operator behavior as the primary WDL target. First author or repair a main-function workflow that wraps the real entrypoint and its true required inputs/outputs.",
        "A separate smoke workflow is allowed as a fallback or compatibility probe, but smoke success alone does not mean the WDL task is complete.",
        "If the repository lacks runnable real inputs for the principal workflow, still save the main-function WDL plus inputs template, record the exact missing prerequisites, and return partial rather than claiming completed.",
        "Do not stop at `miniwdl check`. A syntax-only pass is not a successful WDL validation.",
        "For WDL validation, first distinguish WDL syntax, runner/container compatibility, tool command validity, and output collection failures; repair the smallest failing layer before retrying.",
        "If a repository-native smoke command has a special test mode, do not assume it accepts the same output flags as normal execution. Verify documented flags before adding -o/--output.",
        "For SPAdes specifically, never run `spades.py --test -o ...`: SPAdes rejects --test together with -o. Use either `spades.py --test` without -o and then copy the default `spades_test` directory to declared WDL output paths, or use a normal explicit-read command with -o on a dataset known to work.",
        "If the user requires real data and the repository lacks bundled real inputs, fetch a small public real dataset and record its provenance. Do not fabricate or synthesize reads/FASTA/FASTQ to satisfy that requirement.",
        "Carry the same dependency strategy into WDL authoring: prefer a WDL runtime based on a repository-documented official image, then a thin wrapper image, and only then a from-scratch rebuild.",
        "If the main workflow still depends on private references, author-machine paths, missing functions/resources, or prohibitively expensive environment solving, stop short of fake completion and return partial with those blockers called out explicitly.",
        "When using miniwdl, make the runtime image shell-compatible if needed, but do not keep retrying the same command after a tool-level error is proven.",
        "Before returning completed, read back the successful main-function miniwdl run's workflow.log and outputs.json, confirm exit_code: 0 or equivalent success markers, and cite those exact artifact paths in your summary/artifacts.",
        "Stop as completed only after the main-function WDL writes a non-empty outputs JSON and the declared primary outputs exist. If only smoke outputs exist, return partial.",
    ),
    "retry_wdl": (
        "Retry the principal workflow first. Do not let a smoke-only success replace the repository's main-function WDL validation goal.",
        "Use prior WDL error evidence directly; do not repeat a command already proven invalid.",
        "For SPAdes, repair away from `--test -o ...`: either run `spades.py --test` without -o and copy its default output directory to stable WDL output paths, or run a normal reads-based command with -o on data already validated to assemble successfully.",
        "If the task requires real data, do not switch to synthetic or generated reads during retry. Prefer a small public real dataset with recorded source provenance, or return partial if none is available in scope.",
        "On retry, preserve the dependency strategy order: documented official image first, thin wrapper second, full rebuild last.",
        "If the remaining blockers are private references, hard-coded paths, missing upstream functions/resources, or prohibitively slow dependency resolution, stop retrying and return partial with those blockers rather than spending more rounds on the same reconstruction path.",
        "Do not stop at `miniwdl check`; only a real miniwdl run with outputs.json plus success logs can justify completed.",
        "After each retry, inspect the main-workflow output JSON plus the miniwdl run directory, and return partial with concrete blockers if successful primary outputs still do not exist.",
    ),
}


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


@cache
def _guidance_asset_lines(kind: str, name: str) -> tuple[str, ...]:
    path = (
        _repo_root()
        / ".code2workspace"
        / "skills"
        / "orchestration"
        / "supervisor-guidance"
        / "references"
        / kind
        / f"{name}.md"
    )
    if not path.exists():
        return ()
    lines = [
        line.strip("- ").strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]
    return tuple(line for line in lines if line)


def describe_capabilities(
    bundles: list[CapabilityBundle],
) -> tuple[list[str], list[str], list[str]]:
    """Return summaries, allowed tools, and implementation kinds for bundles."""
    summaries: list[str] = []
    tool_names: list[str] = []
    kinds: list[str] = []
    seen_tools: set[str] = set()
    for bundle in bundles:
        spec = CAPABILITY_REGISTRY[bundle]
        summaries.append(f"- {bundle}: {spec.summary}")
        kinds.append(f"- {bundle}: {spec.implementation_kind}")
        for tool_name in spec.tool_names:
            if tool_name in seen_tools:
                continue
            seen_tools.add(tool_name)
            tool_names.append(tool_name)
    return summaries, tool_names, kinds


def node_guidance_lines(node_id: str) -> list[str]:
    """Return any node-specific execution guidance lines."""
    lines: list[str] = []
    for key, guidance in _NODE_GUIDANCE_DEFAULTS.items():
        if key in node_id:
            asset_lines = _guidance_asset_lines("nodes", key)
            lines.extend(asset_lines or guidance)
    return lines


def family_guidance_lines(guidance_ids: list[str]) -> list[str]:
    """Return any family-level guidance lines for matched guidance ids."""
    lines: list[str] = []
    for guidance_id in guidance_ids:
        lines.extend(_guidance_asset_lines("families", guidance_id))
        if guidance_id == "generic_qa":
            lines.extend(_generated_generic_experience_lines())
    return lines


def _generated_generic_experience_lines() -> tuple[str, ...]:
    path = generated_guidance_path(_repo_root())
    if not path.exists():
        return ()
    loaded = [
        line.strip("- ").strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]
    return tuple(line for line in loaded if line)


def generic_experience_guidance_lines(*, task: str, guidance_ids: list[str]) -> list[str]:
    """Return matched experience guidance for generic family tasks."""
    if "generic_qa" not in guidance_ids:
        return []
    return retrieve_experience_guidance_lines(task=task, root=_repo_root())
