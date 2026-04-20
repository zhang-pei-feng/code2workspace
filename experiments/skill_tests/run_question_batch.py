"""Run the fixed COVID monitoring question batch into experiments/skill_tests."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from experiments.skill_tests.runner import batch_root, load_batch_cases, run_cases, utc_date


DEFAULT_BATCH_NAME = "covid-monitoring-questions"
DEFAULT_BATCH_FILE = batch_root() / "covid-monitoring-questions-20260421.md"


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
    return parser


def main() -> int:
    args = build_parser().parse_args()
    cases = load_batch_cases(args.batch_file)
    bundle = run_cases(
        cases,
        run_date=args.date,
        output_root=args.output_root,
        pinned_snapshot_root=args.snapshot_root,
    )
    print(
        json.dumps(
            {
                "batch_file": str(args.batch_file),
                "output_root": str(args.output_root),
                "snapshot_root": str(args.snapshot_root),
                "result_dir": str(bundle["result_dir"]),
                "summary_path": str(bundle["summary_path"]),
                "summary_zh_path": str(bundle["summary_zh_path"]),
                "capability_snapshot_path": str(bundle["capability_snapshot_path"]),
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
