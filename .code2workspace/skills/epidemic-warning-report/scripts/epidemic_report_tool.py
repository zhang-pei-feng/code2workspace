#!/usr/bin/env python3
"""Scaffold and compose epidemic warning reports."""

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
        "file": "01_official-monitoring.md",
        "title": "Official Monitoring",
        "subagent": "epidemic-monitor-analyst",
        "purpose": "Summarize official surveillance, trends, and high-level monitoring signals.",
    },
    {
        "file": "02_source-catalog.md",
        "title": "Source Catalog and Channel Context",
        "subagent": "epidemic-source-cartographer",
        "purpose": "Map relevant source channels, source types, and monitoring coverage gaps.",
    },
    {
        "file": "03_variant-risk.md",
        "title": "Variant and Local DB Evidence",
        "subagent": "epidemic-variant-analyst",
        "purpose": "Summarize lineage, mutation, and local database risk evidence.",
    },
    {
        "file": "04_literature-clinical.md",
        "title": "Literature and Clinical Evidence",
        "subagent": "epidemic-clinical-analyst",
        "purpose": "Summarize literature, vaccine progress, neutralization evidence, and clinical signals.",
    },
    {
        "file": "05_actions.md",
        "title": "Actions",
        "subagent": "epidemic-report-composer",
        "purpose": "Synthesize prevention and preparedness actions after evidence lanes are complete.",
    },
)
REQUIRED_LANE_FILES = tuple(lane["file"] for lane in LANE_SPECS[:4])
DEFAULT_MIN_REPORT_CHARS = 5000
LANE_CLASS_BY_FILE = {
    "01_official-monitoring.md": "official_monitoring",
    "02_source-catalog.md": "source_catalog",
    "03_variant-risk.md": "variant_local_db",
    "04_literature-clinical.md": "literature_clinical",
    "05_actions.md": "actions",
}
SECTION_TITLE_BY_FILE = {
    "01_official-monitoring.md": "Monitoring Overview",
    "02_source-catalog.md": "Key Risk Signals",
    "03_variant-risk.md": "Variant / Pathogen Notes",
    "04_literature-clinical.md": "Literature and Clinical Context",
    "05_actions.md": "Prevention and Preparedness Actions",
}


def _parse_lane_file(path: Path) -> dict[str, object]:
    """Parse one lane file into diagnostics-friendly fields."""
    if not path.exists():
        return {
            "exists": False,
            "title": path.stem,
            "skills": [],
            "sources": [],
            "evidence_lines": [],
            "has_evidence": False,
            "missing_reasons": ["lane file not found"],
        }

    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return {
            "exists": True,
            "title": path.stem,
            "skills": [],
            "sources": [],
            "evidence_lines": [],
            "has_evidence": False,
            "missing_reasons": ["lane file is empty"],
        }

    lines = text.splitlines()
    title = lines[0].lstrip("# ").strip() or path.stem
    skills: list[str] = []
    sources: list[str] = []
    evidence_lines: list[str] = []
    for raw in lines[1:]:
        stripped = raw.strip()
        if not stripped:
            continue
        lowered = stripped.lower()
        if lowered.startswith("subagent:") or lowered.startswith("purpose:"):
            continue
        if lowered.startswith("skill:"):
            skills.append(stripped.split(":", 1)[1].strip())
            continue
        if lowered.startswith("source:"):
            sources.append(stripped.split(":", 1)[1].strip())
            continue
        evidence_lines.append(stripped)

    missing_reasons: list[str] = []
    if not skills:
        missing_reasons.append("missing Skill metadata")
    if not sources:
        missing_reasons.append("missing Source metadata")
    if not evidence_lines:
        missing_reasons.append("missing evidence narrative")

    return {
        "exists": True,
        "title": title,
        "skills": skills,
        "sources": sources,
        "evidence_lines": evidence_lines,
        "has_evidence": bool(skills and sources and evidence_lines),
        "missing_reasons": missing_reasons,
    }


def _lane_section_text(
    *,
    lane_file: str,
    lane_info: dict[str, object],
) -> str:
    """Render the final text for one report section."""
    evidence_lines = [str(item) for item in lane_info["evidence_lines"]]
    if evidence_lines:
        return "\n".join(evidence_lines)

    reasons = ", ".join(str(item) for item in lane_info["missing_reasons"])
    lane_class = LANE_CLASS_BY_FILE.get(lane_file, lane_file)
    return (
        f"_This lane is incomplete. Missing or insufficient {lane_class} evidence: {reasons}. "
        "The report cannot treat this evidence layer as fully covered._"
    )


def cmd_init(args: argparse.Namespace) -> int:
    run_dir = (
        Path(args.output_dir).resolve()
        if args.output_dir
        else create_skill_run_dir(
            "epidemic-warning-report",
            args.pathogen or "mixed-pathogens",
            args.region or "global",
            args.topic,
        )
    )
    lanes_dir = ensure_dir(run_dir / "lanes")
    ensure_dir(run_dir / "evidence")
    ensure_dir(run_dir / "exports")
    ensure_dir(run_dir / "research_steps")

    for lane in LANE_SPECS:
        path = lanes_dir / lane["file"]
        if not path.exists():
            write_text(
                path,
                (
                    f"# {lane['title']}\n\n"
                    f"Subagent: {lane['subagent']}\n"
                    f"Purpose: {lane['purpose']}\n\n"
                ),
            )

    manifest = {
        "run_dir": str(run_dir),
        "topic": args.topic,
        "pathogen": args.pathogen or "mixed",
        "region": args.region or "global",
        "period": args.period or "recent",
        "risk_level": args.risk_level or "pending",
        "min_report_chars": int(args.min_report_chars or DEFAULT_MIN_REPORT_CHARS),
        "lanes_dir": str(lanes_dir),
        "required_lane_files": list(REQUIRED_LANE_FILES),
        "recommended_subagents": [
            {
                "name": lane["subagent"],
                "lane_file": lane["file"],
                "purpose": lane["purpose"],
            }
            for lane in LANE_SPECS
        ],
        "required_sections": [
            "Executive Summary",
            "Situation Framing",
            "Monitoring Overview",
            "Key Risk Signals",
            "Variant / Pathogen Notes",
            "Source and Coverage Analysis",
            "Literature and Clinical Context",
            "Risk Level Rationale",
            "Prevention and Preparedness Actions",
            "Operational Recommendations",
            "Uncertainty and Data Gaps",
            "Sources",
        ],
    }
    write_json(run_dir / "manifest.json", manifest)
    write_text(
        run_dir / "request.md",
        (
            "# Epidemic Warning Report Request\n\n"
            f"- Topic: {args.topic}\n"
            f"- Pathogen: {manifest['pathogen']}\n"
            f"- Region: {manifest['region']}\n"
            f"- Period: {manifest['period']}\n"
            f"- Initial risk level: {manifest['risk_level']}\n"
            f"- Minimum report characters: {manifest['min_report_chars']}\n"
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
    lane_file = args.lane_file
    steps_dir = ensure_dir(run_dir / "research_steps")
    log_path = steps_dir / f"{Path(lane_file).stem}.jsonl"
    payload = {
        "lane_file": lane_file,
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


def cmd_compose(args: argparse.Namespace) -> int:
    run_dir = Path(args.run_dir).resolve()
    manifest = read_json(run_dir / "manifest.json")
    lanes_dir = run_dir / "lanes"
    lane_info_by_file = collect_lane_info(
        lanes_dir,
        lane_files=[lane["file"] for lane in LANE_SPECS],
    )

    risk_level = args.risk_level or manifest.get("risk_level", "pending")
    topic = manifest.get("topic", "Epidemic Warning Report")
    pathogen = manifest.get("pathogen", "mixed")
    region = manifest.get("region", "global")
    period = manifest.get("period", "recent")
    min_report_chars = int(manifest.get("min_report_chars", DEFAULT_MIN_REPORT_CHARS))

    missing_required_lanes = [
        lane_file
        for lane_file in REQUIRED_LANE_FILES
        if not bool(lane_info_by_file[lane_file]["has_evidence"])
    ]
    source_classes_present = sorted(
        LANE_CLASS_BY_FILE[lane_file]
        for lane_file in REQUIRED_LANE_FILES
        if bool(lane_info_by_file[lane_file]["has_evidence"])
    )
    if missing_required_lanes:
        missing_lane_lines = [
            f"- `{lane_file}` incomplete: {', '.join(str(item) for item in lane_info_by_file[lane_file]['missing_reasons'])}"
            for lane_file in missing_required_lanes
        ]
    else:
        missing_lane_lines = [
            "- All four required lanes provided evidence with `Skill:` and `Source:` metadata."
        ]

    sections = [
        {
            "title": "Executive Summary",
            "body": args.summary or "Complete this summary after reviewing the lane notes and evidence files.",
        },
        {
            "title": "Situation Framing",
            "body": (
                "This report integrates official monitoring, source-channel context, "
                "variant or lineage evidence when relevant, and literature or clinical "
                "signals. The intent is to support epidemic preparedness and early "
                "warning rather than produce a minimal status memo."
            ),
        },
        {
            "title": "Monitoring Overview",
            "body": render_lane_evidence(
                "01_official-monitoring.md",
                lane_info_by_file["01_official-monitoring.md"],
            ),
            "lane_file": "01_official-monitoring.md",
        },
        {
            "title": "Key Risk Signals",
            "body": render_lane_evidence(
                "02_source-catalog.md",
                lane_info_by_file["02_source-catalog.md"],
            ),
            "lane_file": "02_source-catalog.md",
        },
        {
            "title": "Source and Coverage Analysis",
            "body": (
                "This section should explain which institutions and monitoring "
                "channels are covering the topic, what type of source each one is, "
                "which regions are well-covered, and where the monitoring picture is "
                "still thin or fragmented."
            ),
        },
        {
            "title": "Cross-Source Interpretation",
            "body": (
                "Compare the surveillance, source-channel, variant, and literature "
                "lanes here. Highlight where sources converge, where they differ, and "
                "which signals are strong enough to influence preparedness decisions."
            ),
        },
        {
            "title": "Variant / Pathogen Notes",
            "body": render_lane_evidence(
                "03_variant-risk.md",
                lane_info_by_file["03_variant-risk.md"],
            ),
            "lane_file": "03_variant-risk.md",
        },
        {
            "title": "Risk Level Rationale",
            "body": (
                "Explain explicitly why the final risk level is low, moderate, "
                "elevated, or high. Tie the judgment back to surveillance signals, "
                "source reliability, pathogen or variant context, and clinical or "
                "vaccine developments."
            ),
        },
        {
            "title": "Prevention and Preparedness Actions",
            "body": render_lane_evidence(
                "05_actions.md",
                lane_info_by_file["05_actions.md"],
            ),
            "lane_file": "05_actions.md",
        },
        {
            "title": "Operational Recommendations",
            "body": (
                "Translate the evidence above into concrete recommendations for "
                "surveillance, sequencing, clinical readiness, communication, and "
                "follow-up analysis."
            ),
        },
        {
            "title": "Uncertainty and Data Gaps",
            "body": "_Review lane notes for blind spots, unavailable sources, auth restrictions, and regional reporting gaps._",
        },
        {
            "title": "Missing Or Incomplete Required Lanes",
            "body": "\n".join(missing_lane_lines),
        },
        {
            "title": "Literature and Clinical Context",
            "body": render_lane_evidence(
                "04_literature-clinical.md",
                lane_info_by_file["04_literature-clinical.md"],
            ),
            "lane_file": "04_literature-clinical.md",
        },
    ]

    payload = write_composed_report(
        run_dir=run_dir,
        title=str(topic),
        sections=sections,
        lane_info_by_file=lane_info_by_file,
        header_lines=[
            f"- Output directory: `{run_dir}`",
            f"- Pathogen focus: `{pathogen}`",
            f"- Region: `{region}`",
            f"- Time window: `{period}`",
            f"- Risk level: `{risk_level}`",
        ],
        required_lane_files=list(REQUIRED_LANE_FILES),
        min_report_chars=min_report_chars,
        source_section_mode="by_lane",
        extra_diagnostics={
            "risk_level": risk_level,
            "min_report_chars": min_report_chars,
            "required_lane_files": list(REQUIRED_LANE_FILES),
            "source_classes_present": source_classes_present,
            "source_class_count": len(source_classes_present),
        },
    )
    print(
        json.dumps(
            {
                "run_dir": str(run_dir),
                "report_path": payload["report_path"],
                "diagnostics_path": payload["diagnostics_path"],
                "risk_level": risk_level,
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
    parser = argparse.ArgumentParser(description="Epidemic warning report helper.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init = subparsers.add_parser("init", help="Create a new report run directory.")
    init.add_argument("--topic", required=True)
    init.add_argument("--pathogen")
    init.add_argument("--region")
    init.add_argument("--period")
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
