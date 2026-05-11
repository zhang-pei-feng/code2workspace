from __future__ import annotations

import argparse
import asyncio
import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from code2workspace.orchestration_runtime import (
    HeuristicSupervisorPlanner,
    classify_task,
    classify_task_with_model,
)
from code2workspace_cli.config import create_model


@dataclass(frozen=True, slots=True)
class RoutingEvalCase:
    family: str
    detail_level: str
    case_id: str
    expected_task_type: str
    source_reference: str
    prompt: str


def _build_cases() -> list[RoutingEvalCase]:
    return [
        RoutingEvalCase(
            family="github2workspace",
            detail_level="boundary-short",
            case_id="github2workspace-boundary-01",
            expected_task_type="github2workspace",
            source_reference=(
                "Boundary-style repo execution prompt with explicit GitHub URL but no workflow jargon"
            ),
            prompt="把 https://github.com/ablab/spades 这个仓库收拾到别人能直接跑起来。",
        ),
        RoutingEvalCase(
            family="github2workspace",
            detail_level="boundary-medium",
            case_id="github2workspace-boundary-02",
            expected_task_type="github2workspace",
            source_reference=(
                "Boundary-style environment reproduction prompt"
            ),
            prompt=(
                "这个 GitHub 项目我想交给别人复现，你先把运行环境和最短验证路径理顺。"
                "仓库地址：https://github.com/ablab/spades"
            ),
        ),
        RoutingEvalCase(
            family="github2workspace",
            detail_level="boundary-semantic",
            case_id="github2workspace-boundary-03",
            expected_task_type="github2workspace",
            source_reference=(
                "Boundary-style repository execution-chain prompt without the word workspace"
            ),
            prompt=(
                "这不是代码解释题，我是想把仓库里的真实入口、依赖和执行链条都打通，"
                "让它能被完整复现。仓库地址：https://github.com/ablab/spades"
            ),
        ),
        RoutingEvalCase(
            family="github2workspace",
            detail_level="boundary-ambiguous",
            case_id="github2workspace-boundary-04",
            expected_task_type="github2workspace",
            source_reference=(
                "Ambiguous prompt that mixes repo inspection and execution readiness"
            ),
            prompt=(
                "请看一下这个仓库，别只告诉我结构，最好顺手把它整理到能验证核心流程。"
                "https://github.com/ablab/spades"
            ),
        ),
        RoutingEvalCase(
            family="github2workspace",
            detail_level="boundary-bioinfo",
            case_id="github2workspace-boundary-05",
            expected_task_type="github2workspace",
            source_reference=(
                "Bioinformatics repo reproduction prompt"
            ),
            prompt=(
                "这是一个真实生物信息学仓库，我需要的不是摘要，而是把实验入口、依赖和验证样例都落到可复现实验环境里。"
                "仓库地址：https://github.com/ablab/spades"
            ),
        ),
        RoutingEvalCase(
            family="benchmark",
            detail_level="boundary-short",
            case_id="benchmark-boundary-01",
            expected_task_type="benchmark",
            source_reference=(
                "Boundary-style shared-dataset comparison prompt"
            ),
            prompt="同一份 short-read-ecoli-srr001666 数据，想横向看看几个组装程序谁跑得更好。",
        ),
        RoutingEvalCase(
            family="benchmark",
            detail_level="boundary-medium",
            case_id="benchmark-boundary-02",
            expected_task_type="benchmark",
            source_reference=(
                "Boundary-style metric-comparison prompt without explicit benchmark wording"
            ),
            prompt=(
                "请围绕同一份装配输入，挑几个可比的工具跑一下，最后按 contig_count、assembly_size、n50 给我一个对照。"
            ),
        ),
        RoutingEvalCase(
            family="benchmark",
            detail_level="boundary-semantic",
            case_id="benchmark-boundary-03",
            expected_task_type="benchmark",
            source_reference=(
                "Boundary-style fair-comparison prompt"
            ),
            prompt=(
                "我不是要你只跑一个流程，而是想在共享输入条件下做一轮公平对照，看不同候选方案输出差别。"
            ),
        ),
        RoutingEvalCase(
            family="benchmark",
            detail_level="boundary-ambiguous",
            case_id="benchmark-boundary-04",
            expected_task_type="benchmark",
            source_reference=(
                "Ambiguous multi-tool evaluation prompt"
            ),
            prompt=(
                "如果几个候选工具都能吃同一份输入，就别只挑一个，帮我跑一下然后横向评估。"
            ),
        ),
        RoutingEvalCase(
            family="benchmark",
            detail_level="boundary-data-centric",
            case_id="benchmark-boundary-05",
            expected_task_type="benchmark",
            source_reference=(
                "Data-centric comparison prompt with no explicit benchmark keyword"
            ),
            prompt=(
                "重点不是仓库本身，而是复用同一批数据去比较几种组装思路的输出差异。"
            ),
        ),
        RoutingEvalCase(
            family="report",
            detail_level="boundary-short",
            case_id="report-boundary-01",
            expected_task_type="report",
            source_reference=(
                "Boundary-style formal assessment prompt"
            ),
            prompt="给 XFG.1.1 出一份正式风险评估件。",
        ),
        RoutingEvalCase(
            family="report",
            detail_level="boundary-medium",
            case_id="report-boundary-02",
            expected_task_type="report",
            source_reference=(
                "Boundary-style WHO-like formal synthesis prompt"
            ),
            prompt=(
                "按 WHO 那种正式评估写法，对 XFG.1.1 做一个分维度结论，别只给口头判断。"
            ),
        ),
        RoutingEvalCase(
            family="report",
            detail_level="boundary-semantic",
            case_id="report-boundary-03",
            expected_task_type="report",
            source_reference=(
                "Formal evidence-brief prompt without explicit 报告 wording"
            ),
            prompt=(
                "围绕 XFG.1.1 输出一份正式证据简报，用来支撑风险等级判断，并把不确定性单列。"
            ),
        ),
        RoutingEvalCase(
            family="report",
            detail_level="boundary-ambiguous",
            case_id="report-boundary-04",
            expected_task_type="report",
            source_reference=(
                "Ambiguous prompt that still implies formal deliverable"
            ),
            prompt=(
                "不是只回答一句话，我要一个能直接放进汇报材料里的正式结论版本，主题是 XFG.1.1 风险。"
            ),
        ),
        RoutingEvalCase(
            family="report",
            detail_level="boundary-monitoring",
            case_id="report-boundary-05",
            expected_task_type="report",
            source_reference=(
                "Monitoring-brief style formal synthesis prompt"
            ),
            prompt=(
                "请把近期 XFG.1.1 的监测信号、严重程度线索和免疫逃逸证据整理成一份正式 brief。"
            ),
        ),
        RoutingEvalCase(
            family="generic",
            detail_level="boundary-short",
            case_id="generic-boundary-01",
            expected_task_type="generic",
            source_reference="General planning prompt",
            prompt="帮我先想想这事怎么推进，给个简单计划。",
        ),
        RoutingEvalCase(
            family="generic",
            detail_level="boundary-code",
            case_id="generic-boundary-02",
            expected_task_type="generic",
            source_reference="Code explanation / analysis prompt",
            prompt="看看当前分支的 orchestrator 代码，讲一下 graph round 的数据怎么流，不用改。",
        ),
        RoutingEvalCase(
            family="generic",
            detail_level="boundary-analysis",
            case_id="generic-boundary-03",
            expected_task_type="generic",
            source_reference="Latest-sensitive analysis question that should stay generic rather than report",
            prompt=(
                "最近两周国内新冠和流感大概是什么态势？先给我一个口头判断，不要正式写作。"
            ),
        ),
        RoutingEvalCase(
            family="generic",
            detail_level="boundary-coding",
            case_id="generic-boundary-04",
            expected_task_type="generic",
            source_reference="Normal coding task unrelated to the three special lanes",
            prompt="给当前 routing 评估脚本顺手补个 CSV 导出，只改代码和测试，不跑实验。",
        ),
        RoutingEvalCase(
            family="generic",
            detail_level="boundary-research",
            case_id="generic-boundary-05",
            expected_task_type="generic",
            source_reference="Scientific question without repo-to-workspace/benchmark/report shape",
            prompt=(
                "BA.3.2 和 XFG.1.1 在 RBD 区域未来还会不会继续趋同进化？先帮我分析一下，区分证据和猜测。"
            ),
        ),
    ]


def _run_id() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")


def _serialize_details(details: dict[str, Any]) -> dict[str, Any]:
    return json.loads(json.dumps(details, ensure_ascii=False, default=str))


async def _evaluate_cases(
    model_spec: str | None,
    *,
    rules_only: bool,
    families: set[str] | None,
    limit: int | None,
) -> dict[str, Any]:
    planner = HeuristicSupervisorPlanner()
    model = None
    model_error: str | None = None
    if not rules_only:
        try:
            model = create_model(model_spec).model if model_spec else create_model().model
        except Exception as exc:
            model_error = f"{type(exc).__name__}: {exc}"
    cases = _build_cases()
    if families:
        cases = [case for case in cases if case.family in families]
    if limit is not None:
        cases = cases[:limit]
    results: list[dict[str, Any]] = []
    for case in cases:
        if model is None:
            classification = classify_task(case.prompt)
            details = {
                "source": "rules_fallback_forced" if rules_only else "rules_fallback_model_unavailable",
                "task_type": classification.primary_type,
                "guidance_ids": list(classification.guidance_ids),
            }
            if model_error is not None:
                details["model_error"] = model_error
        else:
            classification, details = await classify_task_with_model(
                model=model,
                task=case.prompt,
            )
        graph = planner.plan_round(
            task=case.prompt,
            retrieved_cases=[],
            prior_rounds=[],
            classification_override=classification,
        )
        results.append(
            {
                **asdict(case),
                "actual_task_type": classification.primary_type,
                "guidance_ids": list(classification.guidance_ids),
                "classification_details": _serialize_details(details),
                "graph_id": graph.graph_id,
                "graph_task_type": graph.task_type,
                "graph_node_ids": [node.node_id for node in graph.nodes],
                "graph_node_titles": [node.title for node in graph.nodes],
                "correct": classification.primary_type == case.expected_task_type,
            }
        )

    family_summary: dict[str, dict[str, int]] = {}
    for result in results:
        family = str(result["family"])
        bucket = family_summary.setdefault(family, {"total": 0, "correct": 0})
        bucket["total"] += 1
        bucket["correct"] += int(bool(result["correct"]))

    total = len(results)
    correct = sum(int(bool(item["correct"])) for item in results)
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "model_spec": model_spec or "default",
        "rules_only": rules_only,
        "model_available": model is not None,
        "model_error": model_error,
        "total_cases": total,
        "correct_cases": correct,
        "accuracy": (correct / total) if total else 0.0,
        "family_summary": family_summary,
        "cases": results,
    }


def _write_report(output_dir: Path, payload: dict[str, Any]) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "routing_eval.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    lines = [
        "# Supervisor Routing Trigger Evaluation",
        "",
        f"- generated_at: `{payload['generated_at']}`",
        f"- model_spec: `{payload['model_spec']}`",
        f"- rules_only: `{payload['rules_only']}`",
        f"- model_available: `{payload['model_available']}`",
        f"- total_cases: `{payload['total_cases']}`",
        f"- correct_cases: `{payload['correct_cases']}`",
        f"- accuracy: `{payload['accuracy']:.2%}`",
        "",
    ]
    if payload.get("model_error"):
        lines.append(f"- model_error: `{payload['model_error']}`")
        lines.append("")
    lines.extend(
        [
            "## Family Summary",
            "",
            "| family | correct | total | accuracy |",
            "| --- | ---: | ---: | ---: |",
        ]
    )
    for family, summary in payload["family_summary"].items():
        total = int(summary["total"])
        correct = int(summary["correct"])
        accuracy = (correct / total) if total else 0.0
        lines.append(f"| {family} | {correct} | {total} | {accuracy:.2%} |")

    lines.extend(
        [
            "",
            "## Case Results",
            "",
            "| case_id | family | detail | expected | actual | correct | graph_nodes | source |",
            "| --- | --- | --- | --- | --- | --- | --- | --- |",
        ]
    )
    for item in payload["cases"]:
        lines.append(
            "| {case_id} | {family} | {detail_level} | {expected_task_type} | "
            "{actual_task_type} | {correct} | `{graph_nodes}` | {source_reference} |".format(
                case_id=item["case_id"],
                family=item["family"],
                detail_level=item["detail_level"],
                expected_task_type=item["expected_task_type"],
                actual_task_type=item["actual_task_type"],
                correct="yes" if item["correct"] else "no",
                graph_nodes=" -> ".join(item["graph_node_ids"]),
                source_reference=item["source_reference"],
            )
        )

    lines.extend(["", "## Prompts", ""])
    for item in payload["cases"]:
        lines.extend(
            [
                f"### {item['case_id']}",
                "",
                f"- family: `{item['family']}`",
                f"- detail_level: `{item['detail_level']}`",
                f"- expected_task_type: `{item['expected_task_type']}`",
                f"- actual_task_type: `{item['actual_task_type']}`",
                f"- graph_nodes: `{' -> '.join(item['graph_node_ids'])}`",
                f"- classification_source: `{item['classification_details'].get('source', 'unknown')}`",
                "",
                item["prompt"],
                "",
            ]
        )

    (output_dir / "routing_eval.md").write_text(
        "\n".join(lines).rstrip() + "\n",
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Evaluate supervisor routing triggers without running full tasks.",
    )
    parser.add_argument(
        "--model",
        dest="model_spec",
        default=None,
        help="Optional model spec. Defaults to the current CLI default model.",
    )
    parser.add_argument(
        "--output-root",
        default="experiments/harness/runs/supervisor-routing-trigger-eval",
        help="Directory where the evaluation artifacts should be written.",
    )
    parser.add_argument(
        "--rules-only",
        action="store_true",
        help="Skip model loading and evaluate the current rule-fallback routing only.",
    )
    parser.add_argument(
        "--family",
        action="append",
        dest="families",
        help="Optional family filter. Can be repeated, e.g. --family benchmark --family generic.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Optional limit after filtering.",
    )
    args = parser.parse_args()

    output_dir = Path(args.output_root) / _run_id()
    payload = asyncio.run(
        _evaluate_cases(
            args.model_spec,
            rules_only=args.rules_only,
            families=set(args.families) if args.families else None,
            limit=args.limit,
        )
    )
    _write_report(output_dir, payload)
    print(output_dir)


if __name__ == "__main__":
    main()
