#!/usr/bin/env python3
"""Scaffold and compose multi-source report runs."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SHARED_HELPER_DIR = (
    Path(__file__).resolve().parents[2] / "_shared-superagent-helpers" / "scripts"
)
if str(SHARED_HELPER_DIR) not in sys.path:
    sys.path.insert(0, str(SHARED_HELPER_DIR))

from common import create_skill_run_dir, ensure_dir, read_json, write_json, write_text
from report_composer import collect_lane_info, render_lane_evidence, write_composed_report


LANE_SPECS = (
    {
        "file": "01_monitoring.md",
        "title": "Monitoring And Operational Evidence",
        "worker_label": "evidence-lane-worker",
        "purpose": "Gather official monitoring signals, operational changes, and concrete surveillance interpretation.",
        "recommended_skills": [
            "respiratory-disease-data-fetcher",
            "respiratory-disease-wide-monitor",
        ],
    },
    {
        "file": "02_source-catalog.md",
        "title": "Source Catalog And Coverage Evidence",
        "worker_label": "evidence-lane-worker",
        "purpose": "Map source provenance, source types, dashboards, channels, coverage gaps, and evidence reliability.",
        "recommended_skills": [
            "epietl-api",
            "respiratory-disease-wide-monitor",
        ],
    },
    {
        "file": "03_local-data.md",
        "title": "Local Structured Data Or Database Evidence",
        "worker_label": "evidence-lane-worker",
        "purpose": "Use local structured data, local DB evidence, or repository-local curated tables where relevant.",
        "recommended_skills": [
            "virus-variation-query",
        ],
    },
    {
        "file": "04_literature-web.md",
        "title": "Literature, Technical, And Web Evidence",
        "worker_label": "evidence-lane-worker",
        "purpose": "Collect paper, technical, and primary-source web evidence that complements the monitoring and data lanes.",
        "recommended_skills": [
            "academic-search",
        ],
    },
    {
        "file": "05_synthesis.md",
        "title": "Synthesis And Recommendations",
        "worker_label": "synthesis-pass",
        "purpose": "Synthesize agreements, disagreements, implications, and practical recommendations across the evidence lanes.",
        "recommended_skills": [
            "multi-source-report",
        ],
    },
)
REQUIRED_LANE_FILES = tuple(lane["file"] for lane in LANE_SPECS[:4])
DEFAULT_MIN_REPORT_CHARS = 5000
DEFAULT_MAX_TABLES = 3


def cmd_init(args: argparse.Namespace) -> int:
    run_dir = (
        Path(args.output_dir).resolve()
        if args.output_dir
        else create_skill_run_dir("multi-source-report", args.topic)
    )
    lanes_dir = ensure_dir(run_dir / "lanes")
    ensure_dir(run_dir / "evidence")
    ensure_dir(run_dir / "exports")
    ensure_dir(run_dir / "research_steps")

    for lane in LANE_SPECS:
        path = lanes_dir / lane["file"]
        if path.exists():
            continue
        recommended = "".join(f"- {item}\n" for item in lane["recommended_skills"])
        write_text(
            path,
            (
                f"# {lane['title']}\n\n"
                f"Worker: {lane['worker_label']}\n"
                f"Purpose: {lane['purpose']}\n"
                "Recommended Skills:\n"
                f"{recommended}\n"
                "When the lane contains trustworthy numeric evidence, also add one or more "
                "`Table Candidate:` blocks with Metric/Value/Unit/Time/Scope/Source/Note fields.\n"
            ),
        )

    manifest = {
        "run_dir": str(run_dir),
        "topic": args.topic,
        "report_mode": args.report_mode,
        "risk_level": args.risk_level or "pending",
        "min_report_chars": int(args.min_report_chars or DEFAULT_MIN_REPORT_CHARS),
        "prefer_tables": True,
        "max_tables": DEFAULT_MAX_TABLES,
        "lanes_dir": str(lanes_dir),
        "required_lane_files": list(REQUIRED_LANE_FILES),
        "recommended_lane_workers": [
            {
                "label": lane["worker_label"],
                "lane_file": lane["file"],
                "purpose": lane["purpose"],
                "recommended_skills": list(lane["recommended_skills"]),
            }
            for lane in LANE_SPECS
        ],
    }
    write_json(run_dir / "manifest.json", manifest)
    write_text(
        run_dir / "research_request.md",
        (
            "# Multi-Source Report Request\n\n"
            f"- Topic: {args.topic}\n"
            f"- Report mode: {args.report_mode}\n"
            f"- Initial risk level: {manifest['risk_level']}\n"
            f"- Minimum report characters: {manifest['min_report_chars']}\n"
            f"- Prefer tables: {manifest['prefer_tables']}\n"
            f"- Max tables: {manifest['max_tables']}\n"
        ),
    )
    print(
        json.dumps(
            {
                "run_dir": str(run_dir),
                "manifest_path": str(run_dir / "manifest.json"),
                "lanes_dir": str(lanes_dir),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def cmd_append_lane_note(args: argparse.Namespace) -> int:
    run_dir = Path(args.run_dir).resolve()
    lane_path = run_dir / "lanes" / args.lane_file
    existing = lane_path.read_text(encoding="utf-8") if lane_path.exists() else ""
    content = args.text.rstrip() + "\n"
    if args.mode == "replace":
        write_text(lane_path, content)
    else:
        write_text(lane_path, existing + content)
    print(
        json.dumps(
            {
                "lane_path": str(lane_path),
                "mode": args.mode,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def cmd_record_research_step(args: argparse.Namespace) -> int:
    run_dir = Path(args.run_dir).resolve()
    steps_dir = ensure_dir(run_dir / "research_steps")
    log_path = steps_dir / f"{Path(args.lane_file).stem}.jsonl"
    payload = {
        "lane_file": args.lane_file,
        "round": args.round,
        "tool": args.tool,
        "summary": args.summary,
        "continue_search": args.continue_search,
        "source": args.source,
    }
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
    print(
        json.dumps(
            {
                "research_step_log": str(log_path),
                "recorded": payload,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def _render_synthesis_body(lane_info_by_file: dict[str, dict[str, object]]) -> str:
    synthesis = lane_info_by_file.get("05_synthesis.md")
    if synthesis and synthesis.get("has_evidence"):
        return render_lane_evidence("05_synthesis.md", synthesis)
    return (
        "Compare the monitoring, provenance, local-data, and literature lanes here. "
        "Highlight where sources agree, where they conflict, what remains uncertain, "
        "and which recommendations are strong enough to act on."
    )


def _looks_numeric(value: str) -> bool:
    return any(char.isdigit() for char in value)


def _collect_table_rows(
    lane_info_by_file: dict[str, dict[str, object]],
) -> tuple[list[dict[str, str]], list[str]]:
    valid_rows: list[dict[str, str]] = []
    rejection_reasons: list[str] = []

    for lane_file, lane_info in lane_info_by_file.items():
        for candidate in lane_info.get("table_candidates", []):
            row = {
                "title": str(candidate.get("title", "")).strip(),
                "metric": str(candidate.get("metric", "")).strip(),
                "value": str(candidate.get("value", "")).strip(),
                "unit": str(candidate.get("unit", "")).strip(),
                "time": str(candidate.get("time", "")).strip(),
                "scope": str(candidate.get("scope", "")).strip(),
                "source": str(candidate.get("source", "")).strip(),
                "note": str(candidate.get("note", "")).strip(),
                "lane_file": lane_file,
            }
            missing: list[str] = []
            if not row["title"]:
                missing.append("missing title")
            if not row["metric"]:
                missing.append("missing metric")
            if not row["value"]:
                missing.append("missing value")
            elif not _looks_numeric(row["value"]):
                missing.append("value is not numeric")
            if not row["time"]:
                missing.append("missing time")
            if not row["source"]:
                missing.append("missing row-level source")

            if missing:
                rejection_reasons.append(
                    f"{row['title'] or lane_file}: {', '.join(missing)}"
                )
                continue
            valid_rows.append(row)

    return valid_rows, rejection_reasons


def _render_key_data_tables(
    valid_rows: list[dict[str, str]],
    *,
    max_tables: int,
) -> tuple[str, int]:
    if not valid_rows:
        return (
            "No reliable numeric table could be produced from the current evidence. "
            "The report retains narrative analysis only because the available numeric "
            "fragments were incomplete, non-comparable, or insufficiently sourced.",
            0,
        )

    grouped: dict[str, list[dict[str, str]]] = {}
    order: list[str] = []
    for row in valid_rows:
        title = row["title"]
        if title not in grouped:
            grouped[title] = []
            order.append(title)
        grouped[title].append(row)

    lines: list[str] = []
    used_titles = order[:max_tables]
    for title in used_titles:
        lines.extend(
            [
                f"### {title}",
                "",
                "| Metric | Value | Unit | Time | Scope | Source | Note |",
                "| --- | --- | --- | --- | --- | --- | --- |",
            ]
        )
        for row in grouped[title]:
            lines.append(
                "| {metric} | {value} | {unit} | {time} | {scope} | {source} | {note} |".format(
                    metric=row["metric"] or "",
                    value=row["value"] or "",
                    unit=row["unit"] or "",
                    time=row["time"] or "",
                    scope=row["scope"] or "",
                    source=row["source"] or "",
                    note=row["note"] or "",
                )
            )
        lines.append("")

    return "\n".join(lines).strip(), len(used_titles)


def cmd_compose(args: argparse.Namespace) -> int:
    run_dir = Path(args.run_dir).resolve()
    manifest = read_json(run_dir / "manifest.json")
    lanes_dir = run_dir / "lanes"
    lane_info_by_file = collect_lane_info(
        lanes_dir,
        lane_files=[lane["file"] for lane in LANE_SPECS],
    )

    topic = manifest.get("topic", "Multi-Source Report")
    report_mode = str(manifest.get("report_mode", "general"))
    risk_level = args.risk_level or manifest.get("risk_level")
    min_report_chars = int(manifest.get("min_report_chars", DEFAULT_MIN_REPORT_CHARS))
    prefer_tables = bool(manifest.get("prefer_tables", True))
    max_tables = int(manifest.get("max_tables", DEFAULT_MAX_TABLES))
    valid_table_rows, table_rejection_reasons = _collect_table_rows(lane_info_by_file)
    key_data_tables_body, table_count = _render_key_data_tables(
        valid_table_rows,
        max_tables=max_tables,
    )

    sections = [
        {
            "title": "Executive Summary",
            "body": args.summary
            or "This report synthesizes the available evidence lanes and keeps only source-backed conclusions in the final answer.",
        },
        {
            "title": "Request And Approach",
            "body": (
                "This report follows a multi-source workflow: gather focused evidence lanes, "
                "compare them explicitly, retain provenance, and separate strong conclusions "
                "from open gaps."
            ),
        },
        {
            "title": "Monitoring And Operational Evidence",
            "body": render_lane_evidence("01_monitoring.md", lane_info_by_file["01_monitoring.md"]),
            "lane_file": "01_monitoring.md",
        },
        {
            "title": "Source Catalog And Coverage Evidence",
            "body": render_lane_evidence("02_source-catalog.md", lane_info_by_file["02_source-catalog.md"]),
            "lane_file": "02_source-catalog.md",
        },
        {
            "title": "Local Structured Data Or Database Evidence",
            "body": render_lane_evidence("03_local-data.md", lane_info_by_file["03_local-data.md"]),
            "lane_file": "03_local-data.md",
        },
        {
            "title": "Literature, Technical, And Web Evidence",
            "body": render_lane_evidence("04_literature-web.md", lane_info_by_file["04_literature-web.md"]),
            "lane_file": "04_literature-web.md",
        },
        {
            "title": "Cross-Source Synthesis",
            "body": _render_synthesis_body(lane_info_by_file),
            "lane_file": "05_synthesis.md",
        },
    ]

    if prefer_tables:
        sections.append(
            {
                "title": "Key Data Tables",
                "body": key_data_tables_body,
            }
        )

    if report_mode == "risk" or risk_level not in (None, "", "pending"):
        sections.append(
            {
                "title": "Risk Or Severity Framing",
                "body": (
                    "Explain the current risk or severity judgment by tying it back to the "
                    "monitoring, provenance, local-data, and literature lanes, and call out "
                    "what would move the judgment up or down."
                ),
            }
        )

    sections.extend(
        [
            {
                "title": "Recommendations And Actions",
                "body": (
                    "Translate the evidence above into concrete next actions for monitoring, "
                    "communication, analysis, operational follow-up, or research."
                ),
            },
            {
                "title": "Uncertainty And Gaps",
                "body": (
                    "Identify missing sources, thin evidence layers, conflicting signals, "
                    "and follow-up questions that prevent stronger conclusions."
                ),
            },
        ]
    )

    header_lines = [f"- Output directory: `{run_dir}`"]
    if report_mode:
        header_lines.append(f"- Report mode: `{report_mode}`")
    if report_mode == "risk" or risk_level not in (None, "", "pending"):
        header_lines.append(f"- Risk level: `{risk_level or 'pending'}`")

    payload = write_composed_report(
        run_dir=run_dir,
        title=str(topic),
        sections=sections,
        lane_info_by_file=lane_info_by_file,
        header_lines=header_lines,
        required_lane_files=list(REQUIRED_LANE_FILES),
        min_report_chars=min_report_chars,
        source_section_mode="by_lane",
        extra_diagnostics={
            "report_mode": report_mode,
            "risk_level": risk_level or None,
            "min_report_chars": min_report_chars,
            "prefer_tables": prefer_tables,
            "max_tables": max_tables,
            "table_count": table_count,
            "table_candidate_count": sum(
                len(info.get("table_candidates", []))
                for info in lane_info_by_file.values()
            ),
            "table_rows_used": len(valid_table_rows),
            "table_rows_rejected": len(table_rejection_reasons),
            "table_rejection_reasons": table_rejection_reasons,
            "required_lane_files": list(REQUIRED_LANE_FILES),
        },
    )
    print(
        json.dumps(
            {
                "run_dir": str(run_dir),
                "report_path": payload["report_path"],
                "diagnostics_path": payload["diagnostics_path"],
                "risk_level": risk_level or None,
                "report_char_count": payload["report_char_count"],
                "meets_min_report_chars": payload["meets_min_report_chars"],
                "complete": payload["complete"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Multi-source report helper.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init = subparsers.add_parser("init", help="Create a new multi-source report run directory.")
    init.add_argument("--topic", required=True)
    init.add_argument("--report-mode", choices=["general", "risk"], default="general")
    init.add_argument("--risk-level")
    init.add_argument("--min-report-chars", type=int)
    init.add_argument("--output-dir")
    init.set_defaults(func=cmd_init)

    compose = subparsers.add_parser("compose", help="Compose final_report.md from lane notes.")
    compose.add_argument("--run-dir", required=True)
    compose.add_argument("--summary")
    compose.add_argument("--risk-level")
    compose.set_defaults(func=cmd_compose)

    append_lane = subparsers.add_parser("append-lane-note", help="Append or replace one lane note.")
    append_lane.add_argument("--run-dir", required=True)
    append_lane.add_argument("--lane-file", required=True)
    append_lane.add_argument("--text", required=True)
    append_lane.add_argument("--mode", choices=["append", "replace"], default="append")
    append_lane.set_defaults(func=cmd_append_lane_note)

    record = subparsers.add_parser("record-research-step", help="Record one research step for a lane.")
    record.add_argument("--run-dir", required=True)
    record.add_argument("--lane-file", required=True)
    record.add_argument("--round", type=int, required=True)
    record.add_argument("--tool", required=True)
    record.add_argument("--summary", required=True)
    record.add_argument("--continue-search", action="store_true")
    record.add_argument("--source")
    record.set_defaults(func=cmd_record_research_step)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
