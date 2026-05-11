from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

from code2workspace.orchestration_runtime import HeuristicSupervisorPlanner
from code2workspace_cli.supervisor_runtime import _build_worker_prompt


@dataclass(frozen=True, slots=True)
class GenericCapabilityCase:
    case_id: str
    category: str
    prompt: str
    target_node: str
    expected_hint: str


CASES: tuple[GenericCapabilityCase, ...] = (
    GenericCapabilityCase(
        case_id="generic-cap-01",
        category="code_fix",
        prompt="帮我修一下这个 Python 项目里导致测试失败的导入错误，并说明最小修复方案。",
        target_node="worker_solution",
        expected_hint="solution lane has enough material for compose",
    ),
    GenericCapabilityCase(
        case_id="generic-cap-02",
        category="data_analysis",
        prompt="请根据本地 CSV 日志判断最近一周错误率上升的主要原因，并给一个处置建议。",
        target_node="worker_solution",
        expected_hint="filtered artifacts",
    ),
    GenericCapabilityCase(
        case_id="generic-cap-03",
        category="incident_triage",
        prompt="我想快速判断这个仓库的启动失败是不是因为缺少系统依赖，请先给排查路径。",
        target_node="worker_context",
        expected_hint="exact files, commands, or runtime constraints",
    ),
    GenericCapabilityCase(
        case_id="generic-cap-04",
        category="solution_comparison",
        prompt="比较一下两种技术方案在当前约束下的风险和落地难度，给我一个建议。",
        target_node="worker_context",
        expected_hint="changes downstream decisions",
    ),
    GenericCapabilityCase(
        case_id="generic-cap-05",
        category="migration_plan",
        prompt="请先整理一个面向执行的迁移计划，重点是依赖梳理、风险点和先后顺序。",
        target_node="init_generic",
        expected_hint="bounded delivery contract",
    ),
)


def _timestamp() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


def _contains_contract(prompt: str) -> dict[str, bool]:
    required = [
        "Execution focus:",
        "Preferred inputs:",
        "Expected outputs:",
        "Stop when:",
        "Avoid:",
    ]
    return {item.rstrip(":").lower().replace(" ", "_"): item in prompt for item in required}


def _evaluate_case(case: GenericCapabilityCase, workspace_root: Path) -> dict[str, object]:
    planner = HeuristicSupervisorPlanner()
    graph = planner.plan_round(task=case.prompt, retrieved_cases=[], prior_rounds=[])
    node = next(item for item in graph.nodes if item.node_id == case.target_node)
    prompt = _build_worker_prompt(node=node, workspace_root=workspace_root)
    contract_checks = _contains_contract(prompt)
    return {
        "case": asdict(case),
        "graph_task_type": graph.task_type,
        "graph_nodes": [item.node_id for item in graph.nodes],
        "guidance_ids": list(graph.metadata.get("guidance_ids", [])),
        "target_node": case.target_node,
        "prompt_line_count": len(prompt.splitlines()),
        "contract_checks": contract_checks,
        "has_family_guidance": "bounded question-answering or problem-solving" in prompt,
        "has_expected_hint": case.expected_hint in prompt,
        "prompt_excerpt": "\n".join(prompt.splitlines()[:40]),
    }


def _render_md(results: list[dict[str, object]]) -> str:
    lines = [
        "# Generic Capability Prompt Evaluation",
        "",
        f"- generated_utc: {datetime.now(UTC).strftime('%Y-%m-%d %H:%M:%S %Z')}",
        f"- case_count: {len(results)}",
        "",
    ]
    for item in results:
        case = item["case"]
        lines.extend(
            [
                f"## {case['case_id']} ({case['category']})",
                "",
                f"- prompt: {case['prompt']}",
                f"- graph_task_type: `{item['graph_task_type']}`",
                f"- graph_nodes: `{', '.join(item['graph_nodes'])}`",
                f"- guidance_ids: `{', '.join(item['guidance_ids'])}`",
                f"- target_node: `{item['target_node']}`",
                f"- has_family_guidance: `{item['has_family_guidance']}`",
                f"- has_expected_hint: `{item['has_expected_hint']}`",
                f"- contract_checks: `{json.dumps(item['contract_checks'], ensure_ascii=False)}`",
                "",
                "```text",
                str(item["prompt_excerpt"]),
                "```",
                "",
            ]
        )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output-root",
        default="experiments/harness/runs/generic-capability-prompt-eval",
    )
    args = parser.parse_args()

    output_root = Path(args.output_root)
    run_dir = output_root / _timestamp()
    run_dir.mkdir(parents=True, exist_ok=True)
    workspace_root = Path.cwd()

    results = [_evaluate_case(case, workspace_root) for case in CASES]
    payload = {
        "generated_utc": datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S %Z"),
        "workspace_root": str(workspace_root),
        "results": results,
    }
    (run_dir / "generic_capability_eval.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (run_dir / "generic_capability_eval.md").write_text(
        _render_md(results),
        encoding="utf-8",
    )
    print(run_dir)


if __name__ == "__main__":
    main()
