"""Summarize SWE-bench Lite pilot runs into thesis-facing JSON/CSV/Markdown bundles."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def build_instance_rows(
    manifest: dict[str, Any],
    evaluation_payload: dict[str, Any],
) -> list[dict[str, Any]]:
    by_id = {
        str(row.get("instance_id", "")): row
        for row in evaluation_payload.get("instances", [])
        if row.get("instance_id")
    }
    rows: list[dict[str, Any]] = []
    for instance_id in manifest.get("instance_ids", []):
        source = dict(by_id.get(str(instance_id), {}))
        rows.append(
            {
                "instance_id": str(instance_id),
                "patch_generated": bool(source.get("patch_generated")),
                "resolved": bool(source.get("resolved")),
                "runtime_seconds": float(source.get("runtime_seconds", 0.0)),
            }
        )
    return rows


def build_run_row(
    instance_rows: list[dict[str, Any]],
    *,
    manifest: dict[str, Any],
) -> dict[str, Any]:
    attempted = len(instance_rows)
    resolved = sum(1 for row in instance_rows if row.get("resolved"))
    patch_generated = sum(1 for row in instance_rows if row.get("patch_generated"))
    average_runtime = (
        sum(float(row.get("runtime_seconds", 0.0)) for row in instance_rows) / attempted
        if attempted
        else 0.0
    )
    resolved_rate = f"{(resolved / attempted * 100):.1f}%" if attempted else "0.0%"
    return {
        "run_id": str(manifest.get("run_id", "")),
        "dataset_name": str(manifest.get("dataset_name", "")),
        "subset_name": str(manifest.get("subset_name", "")),
        "subset_size": len(manifest.get("instance_ids", [])),
        "attempted": attempted,
        "resolved": resolved,
        "resolved_rate": resolved_rate,
        "patch_generated": patch_generated,
        "avg_runtime_per_task_seconds": round(average_runtime, 1),
        "notes": str(manifest.get("notes", "")),
    }


def build_markdown_summary(
    rows: list[dict[str, Any]],
    *,
    title: str,
) -> str:
    lines = [
        f"# {title}",
        "",
        "| run_id | subset size | attempted | resolved | resolved rate | patch generated | avg runtime per task | notes |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for row in rows:
        lines.append(
            "| {run_id} | {subset_size} | {attempted} | {resolved} | {resolved_rate} | {patch_generated} | {avg_runtime_per_task_seconds}s | {notes} |".format(
                **row
            )
        )
    lines.append("")
    return "\n".join(lines)


def write_summary_bundle(
    output_dir: Path,
    *,
    rows: list[dict[str, Any]],
    instances: list[dict[str, Any]],
    title: str,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "summary.json").write_text(
        json.dumps(
            {
                "title": title,
                "rows": rows,
                "instances": instances,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (output_dir / "SUMMARY_ZH.md").write_text(
        build_markdown_summary(rows, title=title),
        encoding="utf-8",
    )
    with (output_dir / "rows.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "run_id",
                "dataset_name",
                "subset_name",
                "subset_size",
                "attempted",
                "resolved",
                "resolved_rate",
                "patch_generated",
                "avg_runtime_per_task_seconds",
                "notes",
            ],
        )
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
    with (output_dir / "instances.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["instance_id", "patch_generated", "resolved", "runtime_seconds"],
        )
        writer.writeheader()
        for row in instances:
            writer.writerow(row)


def _latest_run_dir(root: Path) -> Path | None:
    if not root.exists():
        return None
    runs = sorted([path for path in root.iterdir() if path.is_dir()])
    return runs[-1] if runs else None


def _collect_run_row(run_dir: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    manifest = _load_json(run_dir / "manifest.json")
    evaluation_payload_path = run_dir / "evaluation_payload.json"
    evaluation_payload = (
        _load_json(evaluation_payload_path)
        if evaluation_payload_path.exists()
        else {"instances": []}
    )
    instance_rows = build_instance_rows(manifest, evaluation_payload)
    return build_run_row(instance_rows, manifest=manifest), instance_rows


def collect_run_rows(
    *,
    runs_root: Path,
    run_dir: Path | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if run_dir is not None:
        run_row, instance_rows = _collect_run_row(run_dir)
        return [run_row], instance_rows

    if not runs_root.exists():
        return [], []

    selected_runs: dict[tuple[str, ...], Path] = {}
    for candidate in sorted(path for path in runs_root.iterdir() if path.is_dir()):
        manifest_path = candidate / "manifest.json"
        evaluation_payload_path = candidate / "evaluation_payload.json"
        if not manifest_path.exists() or not evaluation_payload_path.exists():
            continue
        manifest = _load_json(manifest_path)
        run_key = tuple(str(item) for item in manifest.get("instance_ids", []))
        selected_runs[run_key] = candidate

    run_rows: list[dict[str, Any]] = []
    all_instances: list[dict[str, Any]] = []
    for candidate in sorted(selected_runs.values()):
        run_row, instance_rows = _collect_run_row(candidate)
        run_rows.append(run_row)
        all_instances.extend(instance_rows)
    return run_rows, all_instances


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--run-dir",
        type=Path,
        default=None,
    )
    parser.add_argument(
        "--runs-root",
        type=Path,
        default=repo_root() / "results" / "swebench-lite-pilot" / "runs",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=repo_root() / "results" / "swebench-lite-summary-20260423",
    )
    parser.add_argument(
        "--title",
        default="SWE-bench Lite pilot summary（2026-04-23）",
    )
    args = parser.parse_args()

    run_dir = args.run_dir
    if args.run_dir is None and not args.runs_root.exists():
        args.output_dir.mkdir(parents=True, exist_ok=True)
        write_summary_bundle(args.output_dir, rows=[], instances=[], title=args.title)
        print(
            json.dumps(
                {
                    "output_dir": str(args.output_dir),
                    "row_count": 0,
                    "instance_count": 0,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    if run_dir is None:
        run_rows, instance_rows = collect_run_rows(runs_root=args.runs_root)
    else:
        run_rows, instance_rows = collect_run_rows(runs_root=args.runs_root, run_dir=run_dir)

    write_summary_bundle(args.output_dir, rows=run_rows, instances=instance_rows, title=args.title)
    print(
        json.dumps(
            {
                "output_dir": str(args.output_dir),
                "row_count": len(run_rows),
                "instance_count": len(instance_rows),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
