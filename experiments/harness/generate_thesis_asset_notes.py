"""Generate caption-ready notes for the thesis assets backed by checked-in summaries."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _load_rows(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return list(payload.get("rows", []))


def _format_names(names: list[str]) -> str:
    cleaned = [name for name in names if name]
    if not cleaned:
        return "（无）"
    return "、".join(f"`{name}`" for name in cleaned)


def _count_by(rows: list[dict[str, Any]], key: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        value = str(row.get(key, ""))
        if not value:
            continue
        counts[value] = counts.get(value, 0) + 1
    return counts


def build_asset_notes(
    *,
    oneshot_summary_path: Path,
    benchmark_summary_path: Path,
    project_skill_summary_path: Path,
    two_hour_summary_path: Path,
    swebench_summary_path: Path | None = None,
) -> list[dict[str, str]]:
    oneshot_rows = _load_rows(oneshot_summary_path)
    project_rows = _load_rows(project_skill_summary_path)
    benchmark_rows = _load_rows(benchmark_summary_path)
    two_hour_rows = _load_rows(two_hour_summary_path)
    swebench_rows = _load_rows(swebench_summary_path) if swebench_summary_path and swebench_summary_path.exists() else []

    oneshot_completed = [row["repo"] for row in oneshot_rows if row.get("completed")]
    oneshot_incomplete = [row["repo"] for row in oneshot_rows if not row.get("completed")]
    completion_levels = _count_by(oneshot_rows, "completion_level")
    oneshot_failures = [row for row in oneshot_rows if row.get("failure_category")]
    failure_categories = _count_by(oneshot_failures, "failure_category")
    project_passed = sum(1 for row in project_rows if row.get("status") == "passed")
    selected_skills = sorted(
        {
            row.get("selected_skill", "")
            for row in project_rows
            if row.get("selected_skill") and row.get("selected_skill") != "none"
        }
    )
    mixed_lane = next(
        (row.get("lane_summary", "") for row in project_rows if row.get("task_type") == "multi-lane"),
        "",
    )
    phase_case = next(
        (row.get("phase_summary", "") for row in project_rows if row.get("phase_summary")),
        "",
    )
    routed_cases = sum(
        1
        for row in project_rows
        if row.get("task_type") or row.get("selected_skill") or row.get("lane_summary") or row.get("phase_summary")
    )

    completed_repos = [row["repo"] for row in two_hour_rows if row.get("completed")]
    timed_out_repos = [
        row["repo"]
        for row in two_hour_rows
        if not row.get("completed") and row.get("status") == "timed_out"
    ]
    retry_rows = [
        row["repo"]
        for row in two_hour_rows
        if row.get("channel") == "direct retry" and row.get("completed")
    ]

    success_tools = [row["tool"] for row in benchmark_rows if str(row.get("status", "")).startswith("成功")]
    partial_tools = [row["tool"] for row in benchmark_rows if "部分成功" in str(row.get("status", ""))]
    blocked_tools = [
        row["tool"]
        for row in benchmark_rows
        if row["tool"] not in success_tools and row["tool"] not in partial_tools
    ]
    dataset_groups = sorted({row.get("dataset_group", "") for row in benchmark_rows if row.get("dataset_group")})

    notes: list[dict[str, str]] = [
        {
            "asset_id": "table_5_2",
            "asset_name": "表 5-2 历史 one-shot baseline 结果表",
            "caption": (
                f"表 5-2 汇总了 {len(oneshot_rows)} 个历史 one-shot run；"
                f"其中 {_format_names(oneshot_completed)} 形成历史完成样本，"
                "其余样本则用于说明进入真实执行但尚未稳定闭环的典型状态。"
            ),
            "interpretation": (
                f"历史正向基线主要来自 {_format_names(oneshot_completed)}；"
                f"{_format_names(oneshot_incomplete)} 则说明早期标准化 one-shot baseline 已经能够进入真实构建或真实入口，但还不足以形成当前最强完成证据。"
            ),
            "source_summary": str(oneshot_summary_path.resolve()),
        },
        {
            "asset_id": "figure_5_1",
            "asset_name": "图 5-1 仓库完成状态柱状图",
            "caption": (
                "图 5-1 可直接基于 `results/oneshot-baseline-summary-20260422/rows.csv` "
                "中的 `completion_level` 绘制；当前 level=2 的历史完成样本为 "
                f"`{completion_levels.get('2', 0)}` 个，level=1 的进入真实执行但未闭环样本为 `{completion_levels.get('1', 0)}` 个。"
            ),
            "interpretation": (
                "该图能够直观看出历史 one-shot baseline 已经跨过“只读不执行”阶段，"
                "但最强完成证据仍集中在少数 workflow 仓库。"
            ),
            "source_summary": str(oneshot_summary_path.resolve()),
        },
        {
            "asset_id": "figure_5_2",
            "asset_name": "图 5-2 失败类型分布图",
            "caption": (
                "图 5-2 可直接基于 `results/oneshot-baseline-summary-20260422/rows.csv` "
                "中的 `failure_category` 统计；当前不完全样本主要分布在 "
                + "、".join(f"`{name}` x `{count}`" for name, count in sorted(failure_categories.items()))
                + "。"
            ),
            "interpretation": (
                "失败类型集中在进入真实执行之后的收敛、依赖和接口问题，"
                "而不是单纯停留在仓库阅读阶段，这与本文关于 harness 作用位置的判断一致。"
            ),
            "source_summary": str(oneshot_summary_path.resolve()),
        },
    ]
    if swebench_rows:
        pilot_runs = len(swebench_rows)
        total_attempted = sum(int(row.get("attempted", 0)) for row in swebench_rows)
        total_resolved = sum(int(row.get("resolved", 0)) for row in swebench_rows)
        total_patch_generated = sum(int(row.get("patch_generated", 0)) for row in swebench_rows)
        notes.extend(
            [
                {
                    "asset_id": "table_5_3",
                    "asset_name": "表 5-3 SWE-bench Lite 子集结果表",
                    "caption": (
                        f"表 5-3 汇总了当前 `SWE-bench Lite` {pilot_runs} 条 pilot 运行；"
                        f"当前累计 attempted=`{total_attempted}`，resolved=`{total_resolved}`，"
                        f"patch generated=`{total_patch_generated}`。"
                    ),
                    "interpretation": (
                        "该表将通用软件工程能力验证从“待补实验”推进到多样本真实 pilot 证据；"
                        f"当前已有 {total_resolved} 条 official resolved 样本，说明系统在通用仓库修复上具备可复现的成功案例，"
                        "同时仍保留未 resolved 或 empty-patch 样本以反映评测链与环境稳定性的限制。"
                    ),
                    "source_summary": str(swebench_summary_path.resolve()),
                },
                {
                    "asset_id": "figure_5_3",
                    "asset_name": "图 5-3 SWE-bench Lite 子集 resolved 比例图",
                    "caption": (
                        "图 5-3 可直接基于 `results/swebench-lite-summary-20260423/summary.json` "
                        f"中的 {pilot_runs} 条 pilot 汇总绘制；当前累计 resolved / attempted = `{total_resolved}` / `{total_attempted}`。"
                    ),
                    "interpretation": (
                        "该图用于直观展示当前 agent 在通用软件工程 benchmark 上的多样本 pilot 表现，"
                        "并与 scientific repo 任务线区分开来。"
                    ),
                    "source_summary": str(swebench_summary_path.resolve()),
                },
            ]
        )
    notes.extend(
        [
            {
            "asset_id": "table_5_7",
            "asset_name": "表 5-7 skills 软路由与编排层对比表",
            "caption": (
                f"表 5-7 基于 {routed_cases} 个已落地编排场景，归纳了当前 `Planner:` "
                "规划摘要、目标技能或 lane 摘要、以及分阶段报告状态的可观测输出。"
            ),
            "interpretation": (
                f"当前已验证的软路由编排能力包括 {_format_names(selected_skills)} 的稳定选中、"
                f"mixed task 的 `{mixed_lane or 'n/a'}` 多 lane 摘要，以及 "
                f"`{phase_case or 'n/a'}` 这样的分阶段状态汇总。该表不编造缺失证据的旧路由对照，"
                "而是将现有真实日志整理为高成本仓库任务之前的低成本回归层。"
            ),
            "source_summary": str(project_skill_summary_path.resolve()),
        },
        {
            "asset_id": "table_5_8",
            "asset_name": "表 5-8 project-skill 编排结果表",
            "caption": (
                f"表 5-8 汇总了 {len(project_rows)} 个 case；"
                f"当前 {project_passed}/{len(project_rows)} 全部通过，说明规划摘要、"
                "skill 选择、lane 汇总与分阶段报告已形成稳定可回归信号。"
            ),
            "interpretation": (
                f"当前正确选中的编排技能包括 {_format_names(selected_skills)}；"
                f"mixed case 生成 `{mixed_lane or 'n/a'}` 三 lane，总结 helper 覆盖 `{phase_case or 'n/a'}`。"
            ),
            "source_summary": str(project_skill_summary_path.resolve()),
        },
        {
            "asset_id": "table_5_9",
            "asset_name": "表 5-9 两小时缩减评估结果表",
            "caption": (
                f"表 5-9 汇总了 {len(two_hour_rows)} 条两小时缩减评估记录；"
                f"其中 {_format_names(completed_repos)} 形成真实完成样本，"
                "足以支撑“继续使用 harness”这一工程决策。"
            ),
            "interpretation": (
                f"当前强正向样本是 {_format_names(completed_repos)}；"
                f"{_format_names(timed_out_repos)} 则保留为真实阻塞或长时程样本。"
                f"{(' `' + '`、`'.join(retry_rows) + '` 的 direct retry 额外说明模型服务或调度波动与仓库阻塞需要分开分析。') if retry_rows else ''}"
            ),
            "source_summary": str(two_hour_summary_path.resolve()),
        },
        {
            "asset_id": "table_5_10",
            "asset_name": "表 5-10 benchmark 八工具快照总览表",
            "caption": (
                f"表 5-10 汇总了 {len(benchmark_rows)} 个 benchmark 工具与 "
                f"{len(dataset_groups)} 组共享/独立数据的快照，可直接用于讨论同数据条件下的可比结果与阻塞分布。"
            ),
            "interpretation": (
                f"当前成功工具为 {_format_names(success_tools)}；"
                f"部分成功工具为 {_format_names(partial_tools)}；"
                f"明确阻塞工具为 {_format_names(blocked_tools)}。"
            ),
            "source_summary": str(benchmark_summary_path.resolve()),
        },
        ]
    )
    return notes


def build_markdown_summary(notes: list[dict[str, str]], *, title: str) -> str:
    lines = [
        f"# {title}",
        "",
        "- 该文件用于把已就绪实验结果快速转成论文中的表题、图注和解释句。",
        "",
    ]
    for note in notes:
        lines.extend(
            [
                f"## {note['asset_name']}",
                "",
                f"- Asset ID: `{note['asset_id']}`",
                f"- Caption: {note['caption']}",
                f"- Interpretation: {note['interpretation']}",
                f"- Source: `{note['source_summary']}`",
                "",
            ]
        )
    return "\n".join(lines)


def write_summary_bundle(output_dir: Path, notes: list[dict[str, str]], *, title: str) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "summary.json").write_text(
        json.dumps({"title": title, "notes": notes}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (output_dir / "SUMMARY_ZH.md").write_text(
        build_markdown_summary(notes, title=title),
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--oneshot-summary",
        type=Path,
        default=repo_root() / "results" / "oneshot-baseline-summary-20260422" / "summary.json",
    )
    parser.add_argument(
        "--benchmark-summary",
        type=Path,
        default=repo_root() / "results" / "benchmark-summary-20260421" / "summary.json",
    )
    parser.add_argument(
        "--project-skill-summary",
        type=Path,
        default=repo_root() / "results" / "project-skill-summary-20260422" / "summary.json",
    )
    parser.add_argument(
        "--two-hour-summary",
        type=Path,
        default=repo_root() / "results" / "harness-two-hour-eval" / "summary-20260422" / "summary.json",
    )
    parser.add_argument(
        "--swebench-summary",
        type=Path,
        default=repo_root() / "results" / "swebench-lite-summary-20260423" / "summary.json",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=repo_root() / "results" / "thesis-asset-notes-20260422",
    )
    parser.add_argument(
        "--title",
        default="论文图表说明辅助摘要（2026-04-22）",
    )
    args = parser.parse_args()

    notes = build_asset_notes(
        oneshot_summary_path=args.oneshot_summary,
        benchmark_summary_path=args.benchmark_summary,
        project_skill_summary_path=args.project_skill_summary,
        two_hour_summary_path=args.two_hour_summary,
        swebench_summary_path=args.swebench_summary,
    )
    write_summary_bundle(args.output_dir, notes, title=args.title)
    print(
        json.dumps(
            {
                "output_dir": str(args.output_dir),
                "note_count": len(notes),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
