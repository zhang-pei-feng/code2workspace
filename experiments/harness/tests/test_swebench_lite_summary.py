from __future__ import annotations

import csv
import json
from pathlib import Path

from experiments.swebench.run_swebench_lite_pilot import (
    build_prediction_row,
    load_pilot_instance_ids,
    write_predictions_jsonl,
)
from experiments.swebench.summarize_swebench_lite import (
    build_instance_rows,
    build_run_row,
    collect_run_rows,
    main as summarize_main,
    write_summary_bundle,
)


def test_load_pilot_instance_ids_skips_comments_and_blank_lines(tmp_path: Path) -> None:
    source = tmp_path / "pilot_instances.txt"
    source.write_text(
        "# pilot subset\n"
        "sympy__sympy-20590\n"
        "\n"
        "django__django-14915\n"
        "  \n"
        "# keep this stable\n"
        "psf__requests-2317\n",
        encoding="utf-8",
    )

    instance_ids = load_pilot_instance_ids(source)

    assert instance_ids == [
        "sympy__sympy-20590",
        "django__django-14915",
        "psf__requests-2317",
    ]


def test_write_predictions_jsonl_uses_official_minimum_fields(tmp_path: Path) -> None:
    output = tmp_path / "predictions.jsonl"
    rows = [
        build_prediction_row(
            "sympy__sympy-20590",
            "diff --git a/a.py b/a.py\n",
            model_name="code2workspace-pilot",
        ),
        build_prediction_row(
            "django__django-14915",
            "",
            model_name="code2workspace-pilot",
        ),
    ]

    write_predictions_jsonl(output, rows)

    payloads = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()]

    assert payloads == [
        {
            "instance_id": "sympy__sympy-20590",
            "model_name_or_path": "code2workspace-pilot",
            "model_patch": "diff --git a/a.py b/a.py\n",
        },
        {
            "instance_id": "django__django-14915",
            "model_name_or_path": "code2workspace-pilot",
            "model_patch": "",
        },
    ]


def test_build_summary_rows_from_pilot_manifest(tmp_path: Path) -> None:
    manifest = {
        "run_id": "pilot-001",
        "dataset_name": "princeton-nlp/SWE-bench_Lite",
        "subset_name": "dev",
        "instance_ids": [
            "sympy__sympy-20590",
            "django__django-14915",
            "psf__requests-2317",
        ],
        "notes": "pilot subset; max_workers=1",
    }
    evaluation_payload = {
        "instances": [
            {
                "instance_id": "sympy__sympy-20590",
                "patch_generated": True,
                "resolved": True,
                "runtime_seconds": 120.0,
            },
            {
                "instance_id": "django__django-14915",
                "patch_generated": True,
                "resolved": False,
                "runtime_seconds": 210.0,
            },
            {
                "instance_id": "psf__requests-2317",
                "patch_generated": False,
                "resolved": False,
                "runtime_seconds": 30.0,
            },
        ]
    }

    instance_rows = build_instance_rows(manifest, evaluation_payload)
    run_row = build_run_row(instance_rows, manifest=manifest)

    assert [row["instance_id"] for row in instance_rows] == [
        "sympy__sympy-20590",
        "django__django-14915",
        "psf__requests-2317",
    ]
    assert run_row == {
        "run_id": "pilot-001",
        "dataset_name": "princeton-nlp/SWE-bench_Lite",
        "subset_name": "dev",
        "subset_size": 3,
        "attempted": 3,
        "resolved": 1,
        "resolved_rate": "33.3%",
        "patch_generated": 2,
        "avg_runtime_per_task_seconds": 120.0,
        "notes": "pilot subset; max_workers=1",
    }


def test_write_summary_bundle_emits_json_csv_markdown(tmp_path: Path) -> None:
    output_dir = tmp_path / "summary"
    instance_rows = [
        {
            "instance_id": "sympy__sympy-20590",
            "patch_generated": True,
            "resolved": True,
            "runtime_seconds": 120.0,
        },
        {
            "instance_id": "django__django-14915",
            "patch_generated": False,
            "resolved": False,
            "runtime_seconds": 30.0,
        },
    ]
    run_row = {
        "run_id": "pilot-001",
        "dataset_name": "princeton-nlp/SWE-bench_Lite",
        "subset_name": "dev",
        "subset_size": 2,
        "attempted": 2,
        "resolved": 1,
        "resolved_rate": "50.0%",
        "patch_generated": 1,
        "avg_runtime_per_task_seconds": 75.0,
        "notes": "pilot subset",
    }

    write_summary_bundle(
        output_dir,
        rows=[run_row],
        instances=instance_rows,
        title="SWE-bench Lite pilot summary",
    )

    payload = json.loads((output_dir / "summary.json").read_text(encoding="utf-8"))
    markdown = (output_dir / "SUMMARY_ZH.md").read_text(encoding="utf-8")
    with (output_dir / "rows.csv").open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    with (output_dir / "instances.csv").open(encoding="utf-8", newline="") as handle:
        instances = list(csv.DictReader(handle))

    assert payload["title"] == "SWE-bench Lite pilot summary"
    assert payload["rows"][0]["resolved"] == 1
    assert "subset size" in markdown
    assert rows[0]["resolved_rate"] == "50.0%"
    assert instances[0]["instance_id"] == "sympy__sympy-20590"


def test_collect_run_rows_aggregates_multiple_run_dirs(tmp_path: Path) -> None:
    runs_root = tmp_path / "runs"
    run_one = runs_root / "20260422T000001Z"
    run_two = runs_root / "20260422T000002Z"
    run_one.mkdir(parents=True)
    run_two.mkdir(parents=True)

    (run_one / "manifest.json").write_text(
        json.dumps(
            {
                "run_id": "20260422T000001Z",
                "dataset_name": "SWE-bench/SWE-bench_Lite",
                "subset_name": "dev",
                "instance_ids": ["sympy__sympy-20590"],
                "notes": "pilot subset",
            }
        ),
        encoding="utf-8",
    )
    (run_one / "evaluation_payload.json").write_text(
        json.dumps(
            {
                "instances": [
                    {
                        "instance_id": "sympy__sympy-20590",
                        "patch_generated": True,
                        "resolved": True,
                        "runtime_seconds": 120.0,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    (run_two / "manifest.json").write_text(
        json.dumps(
            {
                "run_id": "20260422T000002Z",
                "dataset_name": "SWE-bench/SWE-bench_Lite",
                "subset_name": "dev",
                "instance_ids": ["django__django-14915"],
                "notes": "pilot subset",
            }
        ),
        encoding="utf-8",
    )
    (run_two / "evaluation_payload.json").write_text(
        json.dumps(
            {
                "instances": [
                    {
                        "instance_id": "django__django-14915",
                        "patch_generated": False,
                        "resolved": False,
                        "runtime_seconds": 30.0,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    rows, instances = collect_run_rows(runs_root=runs_root)

    assert [row["run_id"] for row in rows] == ["20260422T000001Z", "20260422T000002Z"]
    assert rows[0]["resolved"] == 1
    assert rows[1]["resolved"] == 0
    assert [row["instance_id"] for row in instances] == [
        "sympy__sympy-20590",
        "django__django-14915",
    ]


def test_collect_run_rows_skips_incomplete_run_dirs(tmp_path: Path) -> None:
    runs_root = tmp_path / "runs"
    complete_run = runs_root / "20260422T000001Z"
    incomplete_run = runs_root / "20260422T000002Z"
    complete_run.mkdir(parents=True)
    incomplete_run.mkdir(parents=True)

    (complete_run / "manifest.json").write_text(
        json.dumps(
            {
                "run_id": "20260422T000001Z",
                "dataset_name": "SWE-bench/SWE-bench_Lite",
                "subset_name": "dev",
                "instance_ids": ["sympy__sympy-20590"],
                "notes": "pilot subset",
            }
        ),
        encoding="utf-8",
    )
    (complete_run / "evaluation_payload.json").write_text(
        json.dumps(
            {
                "instances": [
                    {
                        "instance_id": "sympy__sympy-20590",
                        "patch_generated": True,
                        "resolved": True,
                        "runtime_seconds": 120.0,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    (incomplete_run / "manifest.json").write_text(
        json.dumps(
            {
                "run_id": "20260422T000002Z",
                "dataset_name": "SWE-bench/SWE-bench_Lite",
                "subset_name": "dev",
                "instance_ids": ["django__django-14915"],
                "notes": "pilot subset",
            }
        ),
        encoding="utf-8",
    )

    rows, instances = collect_run_rows(runs_root=runs_root)

    assert [row["run_id"] for row in rows] == ["20260422T000001Z"]
    assert [row["instance_id"] for row in instances] == ["sympy__sympy-20590"]


def test_main_aggregates_all_runs_when_run_dir_not_provided(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runs_root = tmp_path / "runs"
    output_dir = tmp_path / "summary"
    run_one = runs_root / "20260422T000001Z"
    run_two = runs_root / "20260422T000002Z"
    run_one.mkdir(parents=True)
    run_two.mkdir(parents=True)

    for run_dir, instance_id, resolved, runtime_seconds in [
        (run_one, "sympy__sympy-20590", True, 120.0),
        (run_two, "django__django-14915", False, 30.0),
    ]:
        (run_dir / "manifest.json").write_text(
            json.dumps(
                {
                    "run_id": run_dir.name,
                    "dataset_name": "SWE-bench/SWE-bench_Lite",
                    "subset_name": "dev",
                    "instance_ids": [instance_id],
                    "notes": "pilot subset",
                }
            ),
            encoding="utf-8",
        )
        (run_dir / "evaluation_payload.json").write_text(
            json.dumps(
                {
                    "instances": [
                        {
                            "instance_id": instance_id,
                            "patch_generated": True,
                            "resolved": resolved,
                            "runtime_seconds": runtime_seconds,
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )

    monkeypatch.setattr(
        "sys.argv",
        [
            "summarize_swebench_lite.py",
            "--runs-root",
            str(runs_root),
            "--output-dir",
            str(output_dir),
            "--title",
            "pilot summary",
        ],
    )

    assert summarize_main() == 0

    payload = json.loads((output_dir / "summary.json").read_text(encoding="utf-8"))
    assert [row["run_id"] for row in payload["rows"]] == [
        "20260422T000001Z",
        "20260422T000002Z",
    ]


def test_collect_run_rows_keeps_latest_run_for_same_instance_set(tmp_path: Path) -> None:
    runs_root = tmp_path / "runs"
    old_run = runs_root / "20260422T000001Z"
    new_run = runs_root / "20260422T000002Z"
    old_run.mkdir(parents=True)
    new_run.mkdir(parents=True)

    for run_dir, resolved, runtime_seconds in [
        (old_run, False, 30.0),
        (new_run, True, 45.0),
    ]:
        (run_dir / "manifest.json").write_text(
            json.dumps(
                {
                    "run_id": run_dir.name,
                    "dataset_name": "SWE-bench/SWE-bench_Lite",
                    "subset_name": "dev",
                    "instance_ids": ["pylint-dev__astroid-1268"],
                    "notes": "pilot subset",
                }
            ),
            encoding="utf-8",
        )
        (run_dir / "evaluation_payload.json").write_text(
            json.dumps(
                {
                    "instances": [
                        {
                            "instance_id": "pylint-dev__astroid-1268",
                            "patch_generated": True,
                            "resolved": resolved,
                            "runtime_seconds": runtime_seconds,
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )

    rows, instances = collect_run_rows(runs_root=runs_root)

    assert [row["run_id"] for row in rows] == ["20260422T000002Z"]
    assert rows[0]["resolved"] == 1
    assert instances == [
        {
            "instance_id": "pylint-dev__astroid-1268",
            "patch_generated": True,
            "resolved": True,
            "runtime_seconds": 45.0,
        }
    ]
