#!/usr/bin/env python3
"""Build a generic local planning contract without keyword routing."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

SHARED_HELPER_DIR = Path(__file__).resolve().parents[2] / "_shared-superagent-helpers" / "scripts"
import sys

if str(SHARED_HELPER_DIR) not in sys.path:
    sys.path.insert(0, str(SHARED_HELPER_DIR))

from common import create_skill_run_dir, ensure_dir, read_json, slugify, write_json, write_text


PLAN_CONTRACT_VERSION = "planning-guide/v2"

BENCHMARK_MARKERS = (
    "benchmark",
    "compare workflows",
    "workflow comparison",
    "docker + wdl",
    "wdl benchmark",
    "跑一下benchmark",
    "跑 benchmark",
    "工具",
    "相同的数据",
    "workflow reuse",
)

PAPER2WORKSPACE_MARKERS = (
    "github repo",
    "github仓库",
    "仓库变成有工作流的工作空间",
    "有工作流的工作空间",
    "repository-to-workspace",
    "repo-to-workspace",
    "runnable workspace",
    "workflow workspace",
)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[4]


def _skills_root() -> Path:
    return _repo_root() / ".code2workspace" / "skills"


def _agents_root() -> Path:
    return _repo_root() / ".code2workspace" / "agents"


def _parse_frontmatter(path: Path) -> dict[str, str]:
    content = path.read_text(encoding="utf-8")
    match = re.match(r"^---\s*\n(.*?)\n---\s*\n?(.*)$", content, re.DOTALL)
    metadata: dict[str, str] = {"body": content.strip()}
    if not match:
        return metadata

    frontmatter = match.group(1)
    body = match.group(2).strip()
    metadata["body"] = body
    for line in frontmatter.splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        metadata[key.strip()] = value.strip().strip("'\"")
    return metadata


def _discover_skills() -> list[dict[str, str]]:
    entries: list[dict[str, str]] = []
    for skill_md in sorted(_skills_root().glob("*/SKILL.md")):
        metadata = _parse_frontmatter(skill_md)
        name = metadata.get("name", skill_md.parent.name)
        if name in {"planning-guide", "planning-orchestrator"}:
            continue
        entries.append(
            {
                "type": "skill",
                "name": name,
                "description": metadata.get("description", ""),
                "path": str(skill_md),
            }
        )
    return entries


def _discover_subagents() -> list[dict[str, str]]:
    entries: list[dict[str, str]] = []
    for agent_md in sorted(_agents_root().glob("*/AGENTS.md")):
        metadata = _parse_frontmatter(agent_md)
        entries.append(
            {
                "type": "subagent",
                "name": metadata.get("name", agent_md.parent.name),
                "description": metadata.get("description", ""),
                "path": str(agent_md),
            }
        )
    return entries


def _word_like_units(task: str) -> list[str]:
    return re.findall(r"[\u4e00-\u9fff]+|[A-Za-z0-9._/+:-]+", task)


def _sentence_like_segments(task: str) -> list[str]:
    raw = re.split(r"[\n\r]+|[。！？!?；;]", task)
    return [segment.strip() for segment in raw if segment.strip()]


def _normalize_task(task: str) -> str:
    return task.casefold()


def _contains_any(task: str, markers: tuple[str, ...]) -> bool:
    normalized = _normalize_task(task)
    return any(marker.casefold() in normalized for marker in markers)


def _recommended_helper_names() -> set[str]:
    return {item["name"] for item in [*_discover_skills(), *_discover_subagents()]}


def _classify_task(task: str) -> dict[str, Any]:
    helpers = _recommended_helper_names()
    benchmark_match = _contains_any(task, BENCHMARK_MARKERS) and (
        "benchmark-workflow-orchestrator" in helpers
    )
    paper_match = _contains_any(task, PAPER2WORKSPACE_MARKERS) and (
        "paper2workspace-orchestrator" in helpers
    )

    if benchmark_match and paper_match:
        return {
            "domain": "multi-lane",
            "task_type": "multi-lane",
            "recommended_skill": None,
            "dispatch_candidate": None,
            "selected_skill": None,
            "fresh_run_required": True,
            "needs_isolated_workspace": True,
            "subtasks": [
                {
                    "lane_id": "workspace",
                    "title": "Workspace",
                    "selected_skill": "paper2workspace-orchestrator",
                    "goal": "Turn the repository into a runnable workflow workspace.",
                },
                {
                    "lane_id": "benchmark",
                    "title": "Benchmark",
                    "selected_skill": "benchmark-workflow-orchestrator",
                    "goal": "Benchmark multiple tools and compare real results.",
                },
            ],
        }
    if benchmark_match:
        return {
            "domain": "benchmark",
            "task_type": "benchmark",
            "recommended_skill": "benchmark-workflow-orchestrator",
            "dispatch_candidate": "benchmark-workflow-orchestrator",
            "selected_skill": "benchmark-workflow-orchestrator",
            "fresh_run_required": True,
            "needs_isolated_workspace": True,
            "subtasks": [],
        }
    if paper_match:
        return {
            "domain": "paper2workspace",
            "task_type": "paper2workspace",
            "recommended_skill": "paper2workspace-orchestrator",
            "dispatch_candidate": "paper2workspace-orchestrator",
            "selected_skill": "paper2workspace-orchestrator",
            "fresh_run_required": True,
            "needs_isolated_workspace": True,
            "subtasks": [],
        }
    return {
        "domain": "generic",
        "task_type": "general",
        "recommended_skill": None,
        "dispatch_candidate": None,
        "selected_skill": None,
        "fresh_run_required": False,
        "needs_isolated_workspace": False,
        "subtasks": [],
    }


def _is_complex(task: str) -> bool:
    units = _word_like_units(task)
    segments = _sentence_like_segments(task)
    has_list_shape = bool(re.search(r"(^|\n)\s*(?:[-*]|\d+\.)\s+", task))
    has_multiple_paths = len(re.findall(r"(?:^|\s)(?:\./|/)[^\s]+", task)) >= 2
    return (
        len(task.strip()) >= 20
        or len(units) >= 10
        or len(segments) >= 2
        or "\n" in task
        or has_list_shape
        or has_multiple_paths
    )


def _intent(task: str, complexity: str) -> dict[str, Any]:
    has_explicit_constraints = bool(
        re.search(r"https?://|`[^`]+`|(?:^|\s)(?:\./|/)[^\s]+", task)
    )
    return {
        "task_shape": "multi-scope" if complexity == "complex" else "single-scope",
        "has_explicit_constraints": has_explicit_constraints,
        "local_context_first": True,
        "verification_needed": True,
    }


def _lanes(complexity: str) -> list[dict[str, str]]:
    if complexity == "simple":
        return [
            {
                "lane_id": "main",
                "title": "Main",
                "purpose": "Handle the task directly with minimal staging.",
            }
        ]
    return [
        {
            "lane_id": "understanding",
            "title": "Understanding",
            "purpose": "Clarify the goal, constraints, and missing information.",
        },
        {
            "lane_id": "source-selection",
            "title": "Source Selection",
            "purpose": "Choose the right evidence sources before execution.",
        },
        {
            "lane_id": "execution",
            "title": "Execution",
            "purpose": "Perform the main task path with minimal wasted work.",
        },
        {
            "lane_id": "verification",
            "title": "Verification",
            "purpose": "Check results against the task outcome and success criteria.",
        },
    ]


def _recommended_lanes(task: str, classification: dict[str, Any]) -> list[dict[str, Any]]:
    if classification["domain"] == "benchmark":
        return [
            {
                "lane_id": "benchmark",
                "title": "Benchmark",
                "purpose": "Run or audit the benchmark path with the benchmark orchestrator skill.",
                "selected_skill": "benchmark-workflow-orchestrator",
            },
            {
                "lane_id": "analysis",
                "title": "Analysis",
                "purpose": "Summarize shared datasets, artifact quality, and blockers for the user.",
                "selected_skill": "benchmark-workflow-orchestrator",
            },
        ]
    if classification["domain"] == "paper2workspace":
        return [
            {
                "lane_id": "workspace",
                "title": "Workspace",
                "purpose": "Build a runnable workspace and workflow path for the repository.",
                "selected_skill": "paper2workspace-orchestrator",
            },
            {
                "lane_id": "analysis",
                "title": "Analysis",
                "purpose": "Report workspace status, artifacts, and remaining blockers.",
                "selected_skill": "paper2workspace-orchestrator",
            },
        ]
    if classification["domain"] == "multi-lane":
        return list(classification["subtasks"])
    return _lanes("complex" if _is_complex(task) else "simple")


def _phase(phase_id: str, title: str, goal: str, steps: list[str], *, lane_id: str) -> dict[str, Any]:
    return {
        "phase_id": phase_id,
        "title": title,
        "goal": goal,
        "lane_id": lane_id,
        "status": "pending",
        "steps": [
            {
                "step_id": f"{phase_id}-{index + 1:02d}",
                "text": step,
                "status": "pending",
            }
            for index, step in enumerate(steps)
        ],
    }


def _phases(task: str, complexity: str) -> list[dict[str, Any]]:
    if complexity == "simple":
        return [
            _phase(
                "understand",
                "Understand",
                "Confirm the requested outcome and smallest useful action.",
                [
                    "Read the task and restate the expected outcome.",
                    f"Keep the initial execution path scoped to: {task}",
                ],
                lane_id="main",
            ),
            _phase(
                "execute",
                "Execute",
                "Perform the direct task path with minimal branching.",
                [
                    "Use the closest local source of truth first.",
                    "Avoid introducing extra branches unless a blocker appears.",
                ],
                lane_id="main",
            ),
            _phase(
                "verify",
                "Verify",
                "Check the output against the user's requested result.",
                [
                    "Capture the concrete result or artifact path.",
                    "Mark the task complete only when real evidence exists.",
                ],
                lane_id="main",
            ),
        ]

    return [
        _phase(
            "understand",
            "Understand",
            "Clarify the task outcome, constraints, and key unknowns.",
            [
                "Restate the task in operational terms.",
                "List constraints, assumptions, and missing facts before execution.",
            ],
            lane_id="understanding",
        ),
        _phase(
            "source-selection",
            "Source Selection",
            "Choose the cheapest authoritative evidence sources first.",
            [
                "Separate locally discoverable facts from external evidence needs.",
                "Choose evidence sources before implementation or reporting.",
            ],
            lane_id="source-selection",
        ),
        _phase(
            "execute",
            "Execute",
            "Run the main task path with the chosen evidence sources.",
            [
                "Start with the smallest safe execution path.",
                "Revise the plan only when concrete blockers or new facts appear.",
            ],
            lane_id="execution",
        ),
        _phase(
            "verify",
            "Verify",
            "Prove the result with commands, artifacts, or concrete evidence.",
            [
                "Check the result against the requested outcome.",
                "Record what evidence justifies completion.",
            ],
            lane_id="verification",
        ),
    ]


def _source_options() -> list[dict[str, Any]]:
    return [
        {
            "type": "source_option",
            "name": "local-repo-and-runtime",
            "reason": "Start with local code, tests, configs, logs, and runtime output when the answer may already be discoverable in the repository or current environment.",
            "dispatchable": False,
        },
        {
            "type": "source_option",
            "name": "local-data-and-schemas",
            "reason": "Use local databases, schemas, snapshots, exports, and ETL outputs when the task depends on stored data or interface shape.",
            "dispatchable": False,
        },
        {
            "type": "source_option",
            "name": "official-docs-and-specs",
            "reason": "Use official docs, API specs, and primary product documentation when local evidence is incomplete or authority matters.",
            "dispatchable": False,
        },
        {
            "type": "source_option",
            "name": "current-web-sources",
            "reason": "Use current web sources only when freshness materially affects the answer or the required fact cannot be established locally.",
            "dispatchable": False,
        },
    ]


def build_plan(task: str) -> dict[str, Any]:
    complexity = "complex" if _is_complex(task) else "simple"
    classification = _classify_task(task)
    return {
        "contract_version": PLAN_CONTRACT_VERSION,
        "task": task,
        "intent": _intent(task, complexity),
        "complexity": complexity,
        "domain": classification["domain"],
        "task_type": classification["task_type"],
        "recommended_skill": classification["recommended_skill"],
        "dispatch_candidate": classification["dispatch_candidate"],
        "selected_skill": classification["selected_skill"],
        "fresh_run_required": classification["fresh_run_required"],
        "needs_isolated_workspace": classification["needs_isolated_workspace"],
        "subtasks": classification["subtasks"],
        "recommended_sources": _source_options(),
        "available_helpers": [*_discover_skills(), *_discover_subagents()],
        "planning_principles": [
            "Clarify the outcome and success criteria before acting.",
            "Separate local facts from external evidence needs.",
            "Choose the cheapest authoritative source first.",
            "Define the verification path before implementation or conclusions.",
        ],
        "plan_mode": "single-step" if complexity == "simple" else "multi-phase",
        "lanes": _recommended_lanes(task, classification),
        "phases": _phases(task, complexity),
    }


def _write_plan_files(run_dir: Path, payload: dict[str, Any]) -> None:
    write_json(run_dir / "plan.json", payload)
    lines = [
        "# Planning Run",
        "",
        f"- contract_version: `{payload['contract_version']}`",
        f"- task: `{payload['task']}`",
        f"- complexity: `{payload['complexity']}`",
        f"- domain: `{payload['domain']}`",
        f"- recommended_skill: `{payload['recommended_skill'] or 'none'}`",
        f"- dispatch_candidate: `{payload['dispatch_candidate'] or 'none'}`",
        f"- task_type: `{payload['task_type']}`",
        f"- selected_skill: `{payload['selected_skill'] or 'none'}`",
        f"- fresh_run_required: `{payload['fresh_run_required']}`",
        f"- needs_isolated_workspace: `{payload['needs_isolated_workspace']}`",
        f"- plan_mode: `{payload['plan_mode']}`",
        "",
        "## Intent",
        "",
    ]
    lines.extend(f"- `{key}`: `{value}`" for key, value in payload["intent"].items())
    lines.extend(["", "## Planning Principles", ""])
    lines.extend(f"- {item}" for item in payload["planning_principles"])
    lines.extend(["", "## Source Options", ""])
    lines.extend(
        f"- `{item['name']}`: {item['reason']}" for item in payload["recommended_sources"]
    )
    lines.extend(["", "## Available Helpers", ""])
    if payload["available_helpers"]:
        lines.extend(
            f"- `{item['type']}` `{item['name']}`: {item['description']}"
            for item in payload["available_helpers"]
        )
    else:
        lines.append("- No local helper metadata discovered.")
    lines.extend(["", "## Lanes", ""])
    lines.extend(
        f"- `{lane['lane_id']}`: {lane.get('purpose') or lane.get('goal') or ''}"
        for lane in payload["lanes"]
    )
    lines.extend(["", "## Phases", ""])
    lines.extend(f"- `{phase['phase_id']}`: {phase['goal']}" for phase in payload["phases"])
    write_text(run_dir / "plan.md", "\n".join(lines) + "\n")


def cmd_classify(args: argparse.Namespace) -> int:
    print(json.dumps(build_plan(args.task), ensure_ascii=False, indent=2))
    return 0


def cmd_init(args: argparse.Namespace) -> int:
    plan = build_plan(args.task)
    run_dir = Path(args.output_dir) if args.output_dir else create_skill_run_dir("planning-guide", slugify(args.task, "task"))
    ensure_dir(run_dir)
    manifest = {
        **plan,
        "run_dir": str(run_dir),
        "dispatch": {
            "status": "pending",
            "adapter": None,
            "downstream_run_dir": None,
            "helper_script": None,
        },
    }
    write_json(run_dir / "manifest.json", manifest)
    _write_plan_files(run_dir, plan)
    print(json.dumps({"run_dir": str(run_dir), **plan}, ensure_ascii=False, indent=2))
    return 0


def cmd_dispatch(args: argparse.Namespace) -> int:
    run_dir = Path(args.run_dir).resolve()
    manifest = read_json(run_dir / "manifest.json")
    if manifest.get("recommended_skill"):
        dispatch = {
            "status": "recommended-skill-ready",
            "adapter": manifest["recommended_skill"],
            "helper_script": None,
            "downstream_run_dir": None,
            "reason": "Soft routing recommendation only. The agent should prefer the recommended orchestrator skill, but execution is not forced.",
        }
    else:
        dispatch = {
            "status": "generic-plan-ready",
            "adapter": None,
            "helper_script": None,
            "downstream_run_dir": None,
            "reason": "Planning remains guidance-only. Review the plan contract and choose helpers deliberately instead of relying on automatic dispatch.",
        }
    manifest["dispatch"] = dispatch
    write_json(run_dir / "manifest.json", manifest)
    write_json(run_dir / "dispatch.json", dispatch)
    print(json.dumps({"run_dir": str(run_dir), **dispatch}, ensure_ascii=False, indent=2))
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    run_dir = Path(args.run_dir).resolve()
    manifest = read_json(run_dir / "manifest.json")
    dispatch = read_json(run_dir / "dispatch.json") if (run_dir / "dispatch.json").exists() else manifest.get("dispatch", {})
    print(
        json.dumps(
            {
                "run_dir": str(run_dir),
                "task": manifest["task"],
                "complexity": manifest["complexity"],
                "domain": manifest["domain"],
                "intent": manifest["intent"],
                "recommended_skill": manifest["recommended_skill"],
                "dispatch_candidate": manifest["dispatch_candidate"],
                "recommended_sources": manifest["recommended_sources"],
                "available_helpers": manifest.get("available_helpers", []),
                "plan_mode": manifest["plan_mode"],
                "lanes": manifest["lanes"],
                "phases": manifest["phases"],
                "dispatch": dispatch,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    classify = subparsers.add_parser("classify", help="Classify one task into a generic plan shape")
    classify.add_argument("--task", required=True)
    classify.set_defaults(func=cmd_classify)

    init = subparsers.add_parser("init", help="Create one generic planning run")
    init.add_argument("--task", required=True)
    init.add_argument("--output-dir")
    init.set_defaults(func=cmd_init)

    dispatch = subparsers.add_parser("dispatch", help="Finalize planning without automatic routing")
    dispatch.add_argument("--run-dir", required=True)
    dispatch.set_defaults(func=cmd_dispatch)

    status = subparsers.add_parser("status", help="Inspect planning state")
    status.add_argument("--run-dir", required=True)
    status.set_defaults(func=cmd_status)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
