"""Run the versioned complex QA suite v1 into experiments/skill_tests."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from experiments.skill_tests.judge import (
    judge_results,
    write_judge_summary_json,
    write_judge_summary_zh,
)
from experiments.skill_tests.runner import batch_root, load_batch_cases, run_cases, utc_date


DEFAULT_BATCH_NAME = "complex-qa-suite-v1"
DEFAULT_BATCH_FILE = batch_root() / "complex-qa-suite-v1.md"


def default_output_root() -> Path:
    return Path(__file__).resolve().parent / "runs" / DEFAULT_BATCH_NAME


def default_snapshot_root() -> Path:
    return Path(__file__).resolve().parent / "snapshots" / DEFAULT_BATCH_NAME


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", default=utc_date())
    parser.add_argument("--batch-file", type=Path, default=DEFAULT_BATCH_FILE)
    parser.add_argument("--output-root", type=Path, default=default_output_root())
    parser.add_argument(
        "--snapshot-root", type=Path, default=default_snapshot_root()
    )
    parser.add_argument("--judge-model", default="openai:gpt-5.4")
    parser.add_argument("--max-parallel", type=int, default=4)
    parser.add_argument("--judge-max-parallel", type=int, default=4)
    parser.add_argument("--judge-only", action="store_true")
    return parser


def load_existing_bundle(*, output_root: Path, snapshot_root: Path, run_date: str) -> dict[str, object]:
    result_dir = output_root / run_date
    summary_path = result_dir / "summary.json"
    payload = json.loads(summary_path.read_text(encoding="utf-8"))
    pinned_snapshot_path = snapshot_root / run_date / "CAPABILITY_SNAPSHOT_ZH.md"
    return {
        "date": run_date,
        "result_dir": result_dir,
        "summary_path": summary_path,
        "summary_zh_path": result_dir / "SUMMARY_ZH.md",
        "capability_snapshot_path": result_dir / "CAPABILITY_SNAPSHOT_ZH.md",
        "pinned_snapshot_path": pinned_snapshot_path if pinned_snapshot_path.exists() else None,
        "results": payload["results"],
    }


def main() -> int:
    args = build_parser().parse_args()
    if args.judge_only:
        bundle = load_existing_bundle(
            output_root=args.output_root,
            snapshot_root=args.snapshot_root,
            run_date=args.date,
        )
    else:
        cases = load_batch_cases(args.batch_file)
        bundle = run_cases(
            cases,
            run_date=args.date,
            output_root=args.output_root,
            pinned_snapshot_root=args.snapshot_root,
            max_parallel=args.max_parallel,
        )
    judged_results = judge_results(
        bundle["results"],
        run_date=args.date,
        model_spec=args.judge_model,
        max_parallel=args.judge_max_parallel,
    )
    judge_summary_path = write_judge_summary_json(
        bundle["result_dir"] / "judge_summary.json",
        judged_results,
        run_date=args.date,
    )
    judge_summary_zh_path = write_judge_summary_zh(
        bundle["result_dir"] / "JUDGE_SUMMARY_ZH.md",
        judged_results,
        run_date=args.date,
    )
    print(
        json.dumps(
            {
                "batch_file": str(args.batch_file),
                "output_root": str(args.output_root),
                "snapshot_root": str(args.snapshot_root),
                "max_parallel": args.max_parallel,
                "judge_max_parallel": args.judge_max_parallel,
                "result_dir": str(bundle["result_dir"]),
                "summary_path": str(bundle["summary_path"]),
                "summary_zh_path": str(bundle["summary_zh_path"]),
                "capability_snapshot_path": str(bundle["capability_snapshot_path"]),
                "judge_summary_path": str(judge_summary_path),
                "judge_summary_zh_path": str(judge_summary_zh_path),
                "pinned_snapshot_path": (
                    str(bundle["pinned_snapshot_path"])
                    if bundle["pinned_snapshot_path"] is not None
                    else None
                ),
                "case_count": len(bundle["results"]),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
