from __future__ import annotations

import importlib
import json
import subprocess
import sys
import types
from pathlib import Path

import pytest

from experiments.harness.code2workspace_harness.agent import build_proposer_workspace, invoke_deepagents_proposer
from experiments.harness.code2workspace_harness.core import SplitResult, load_experiment, repo_root
from experiments.harness.code2workspace_harness.patching import build_baseline_variant, workspace_override_context
from experiments.harness.code2workspace_harness.runner import run_baseline, run_experiment


BENCHMARK_REPO_CONFIG = (
    repo_root() / "experiments" / "harness" / "configs" / "benchmark_repo_harness.toml"
)


def write_config(
    tmp_path: Path,
    *,
    surface_relpath: str,
    proposer_command: list[str] | None = None,
    better_agent_model: str | None = None,
    better_agent_max_turns: int = 40,
    better_agent_deepagents_root: str | None = None,
) -> Path:
    prompt = tmp_path / "prompt.txt"
    workspace_root = tmp_path / "workspace"
    output_root = tmp_path / "output"
    surface_filename = Path(surface_relpath).name
    prompt.write_text("prompt\n", encoding="utf-8")
    proposer_block = ""
    if proposer_command is not None:
        proposer_block = (
            "\n[proposer]\n"
            f"command = {json.dumps(proposer_command)}\n"
            "max_runtime_minutes = 1\n"
        )
    better_agent_block = ""
    if better_agent_model is not None:
        better_agent_block = (
            "\n[better_agent]\n"
            f'model = "{better_agent_model}"\n'
            f"max_turns = {better_agent_max_turns}\n"
        )
        if better_agent_deepagents_root is not None:
            better_agent_block += f'deepagents_root = "{better_agent_deepagents_root}"\n'
    config = tmp_path / "experiment.toml"
    config.write_text(
        f"""
[experiment]
name = "demo-harness"
workspace_root = "{workspace_root}"
output_root = "{output_root}"
max_iterations = 2
{proposer_block}{better_agent_block}
[surfaces.prompt]
kind = "workspace_file"
target = "{surface_relpath}"
filename = "{surface_filename}"
base_file = "{prompt}"

[[cases]]
case_id = "train-case"
repo_url = "https://github.com/example/train-repo"
split = "train"
max_runtime_minutes = 15

[[cases]]
case_id = "holdout-case"
repo_url = "https://github.com/example/holdout-repo"
split = "holdout"
max_runtime_minutes = 15
""".strip()
        + "\n",
        encoding="utf-8",
    )
    return config


def write_repo_splits_config(
    tmp_path: Path,
    *,
    surface_relpath: str,
) -> Path:
    prompt = tmp_path / "prompt.txt"
    workspace_root = tmp_path / "workspace"
    output_root = tmp_path / "output"
    surface_filename = Path(surface_relpath).name
    prompt.write_text("prompt\n", encoding="utf-8")
    repo_splits = tmp_path / "repo_splits.toml"
    repo_splits.write_text(
        """
[splits]
train = [
  "https://github.com/ablab/spades",
  "https://github.com/marbl/canu",
]
holdout = [
  "https://github.com/cbg-ethz/v-pipe",
]
""".strip()
        + "\n",
        encoding="utf-8",
    )
    config = tmp_path / "repo_split_experiment.toml"
    config.write_text(
        f"""
[experiment]
name = "repo-split-harness"
workspace_root = "{workspace_root}"
output_root = "{output_root}"
max_iterations = 2
repo_splits = "{repo_splits}"
default_max_runtime_minutes = 45

[repo_case_runtime_minutes]
spades = 120
v-pipe = 75

[surfaces.prompt]
kind = "workspace_file"
target = "{surface_relpath}"
filename = "{surface_filename}"
base_file = "{prompt}"
""".strip()
        + "\n",
        encoding="utf-8",
    )
    return config


def test_load_experiment_reads_surfaces_and_cases(tmp_path: Path) -> None:
    surface_relpath = f"experiments/harness/surfaces/{tmp_path.name}_prompt.txt"
    config = write_config(tmp_path, surface_relpath=surface_relpath)

    experiment = load_experiment(config)

    assert experiment.name == "demo-harness"
    assert experiment.max_iterations == 2
    assert experiment.cases[0].case_id == "train-case"
    assert experiment.surfaces["prompt"].base_value == "prompt\n"


def test_load_experiment_reads_better_agent_config(tmp_path: Path) -> None:
    surface_relpath = f"experiments/harness/surfaces/{tmp_path.name}_prompt.txt"
    config = write_config(
        tmp_path,
        surface_relpath=surface_relpath,
        better_agent_model="gpt-test",
        better_agent_max_turns=12,
        better_agent_deepagents_root="/tmp/deepagents",
    )

    experiment = load_experiment(config)

    assert experiment.has_proposer() is True
    assert experiment.proposer_mode == "deepagents"
    assert experiment.better_agent_model == "gpt-test"
    assert experiment.better_agent_max_turns == 12
    assert experiment.better_agent_deepagents_root == Path("/tmp/deepagents")


def test_load_experiment_reads_cases_from_repo_splits(tmp_path: Path) -> None:
    surface_relpath = f"experiments/harness/surfaces/{tmp_path.name}_prompt.txt"
    config = write_repo_splits_config(tmp_path, surface_relpath=surface_relpath)

    experiment = load_experiment(config)

    assert experiment.name == "repo-split-harness"
    assert len(experiment.cases) == 3
    assert [case.split for case in experiment.cases] == ["train", "train", "holdout"]
    assert experiment.cases[0].case_id == "spades-train"
    assert experiment.cases[0].max_runtime_minutes == 120
    assert experiment.cases[1].case_id == "canu-train"
    assert experiment.cases[1].max_runtime_minutes == 45
    assert experiment.cases[2].case_id == "v-pipe-holdout"
    assert experiment.cases[2].max_runtime_minutes == 75


def test_benchmark_repo_harness_config_loads_all_eight_real_cases() -> None:
    experiment = load_experiment(BENCHMARK_REPO_CONFIG)

    assert experiment.name == "benchmark-repo-harness"
    assert len(experiment.cases) == 8
    assert len(experiment.cases_for_split("train")) == 5
    assert len(experiment.cases_for_split("holdout")) == 3
    assert {case.case_id for case in experiment.cases_for_split("train")} == {
        "spades-train",
        "canu-train",
        "megahit-train",
        "Flye-train",
        "trinityrnaseq-train",
    }
    assert {case.case_id for case in experiment.cases_for_split("holdout")} == {
        "v-pipe-holdout",
        "covid-19-signal-holdout",
        "fieldbioinformatics-holdout",
    }


def test_workspace_override_context_restores_file(tmp_path: Path) -> None:
    target = repo_root() / "experiments/harness/surfaces" / f"{tmp_path.name}_override.txt"
    workspace_root = tmp_path / "workspace"
    output_root = tmp_path / "output"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("before\n", encoding="utf-8")
    config = tmp_path / "experiment.toml"
    config.write_text(
        f"""
[experiment]
name = "demo-harness"
workspace_root = "{workspace_root}"
output_root = "{output_root}"

[surfaces.prompt]
kind = "workspace_file"
target = "{target.relative_to(repo_root())}"
filename = "{target.name}"
base_value = "before\\n"

[[cases]]
case_id = "train-case"
repo_url = "https://github.com/example/train-repo"
split = "train"
max_runtime_minutes = 15
""".strip()
        + "\n",
        encoding="utf-8",
    )
    experiment = load_experiment(config)
    variant = build_baseline_variant(experiment)
    variant = type(variant)(
        label=variant.label,
        changed_surfaces=("prompt",),
        values={"prompt": "after\n"},
    )

    try:
        with workspace_override_context(experiment, variant):
            assert target.read_text(encoding="utf-8") == "after\n"
        assert target.read_text(encoding="utf-8") == "before\n"
    finally:
        if target.exists():
            target.unlink()


def test_run_baseline_uses_existing_oneshot_runner_contract(tmp_path: Path, monkeypatch) -> None:
    surface_relpath = f"experiments/harness/surfaces/{tmp_path.name}_prompt.txt"
    config = write_config(tmp_path, surface_relpath=surface_relpath)
    experiment = load_experiment(config)

    def fake_run_repo_task(repo_url, *, workspace_root, output_root, max_runtime_minutes):
        run_dir = output_root / repo_url.rsplit("/", 1)[-1] / "run"
        run_dir.mkdir(parents=True, exist_ok=True)
        summary_path = run_dir / "summary.json"
        manifest_path = run_dir / "manifest.json"
        summary_path.write_text(
            json.dumps({"status": "completed", "completed": True}) + "\n",
            encoding="utf-8",
        )
        manifest_path.write_text("{}", encoding="utf-8")
        return {
            "repo_url": repo_url,
            "repo_name": repo_url.rsplit("/", 1)[-1],
            "run_dir": run_dir,
            "returncode": 0,
            "completed": True,
            "status": "completed",
            "summary_path": summary_path,
            "manifest_path": manifest_path,
        }

    monkeypatch.setattr("experiments.harness.code2workspace_harness.runner.run_repo_task", fake_run_repo_task)

    run_root = run_baseline(experiment=experiment, split="train")

    assert run_root.joinpath("variants", "baseline.json").exists()
    assert run_root.joinpath("history", "visible", "train", "baseline", "result.json").exists()


def test_run_experiment_materializes_candidate_and_accepts_improvement(tmp_path: Path, monkeypatch) -> None:
    surface_relpath = f"experiments/harness/surfaces/{tmp_path.name}_prompt.txt"
    proposer = tmp_path / "proposer.py"
    proposer.write_text(
        f"""
from __future__ import annotations

import os
from pathlib import Path

current = Path(os.environ["CODE2WORKSPACE_HARNESS_CURRENT"])
proposal = Path(os.environ["CODE2WORKSPACE_HARNESS_PROPOSAL"])
(current / "{Path(surface_relpath).name}").write_text("better prompt\\n", encoding="utf-8")
proposal.write_text("# Proposal\\n\\n- Summary: improve visible repo outcomes\\n", encoding="utf-8")
""".strip()
        + "\n",
        encoding="utf-8",
    )
    config = write_config(
        tmp_path,
        surface_relpath=surface_relpath,
        proposer_command=[sys.executable, str(proposer)],
    )
    experiment = load_experiment(config)
    surface_target = repo_root() / surface_relpath
    surface_target.parent.mkdir(parents=True, exist_ok=True)
    if surface_target.exists():
        original = surface_target.read_text(encoding="utf-8")
    else:
        original = None

    def fake_run_repo_task(repo_url, *, workspace_root, output_root, max_runtime_minutes):
        current_prompt = surface_target.read_text(encoding="utf-8")
        passed = current_prompt == "better prompt\n"
        run_dir = output_root / repo_url.rsplit("/", 1)[-1] / "run"
        run_dir.mkdir(parents=True, exist_ok=True)
        summary_path = run_dir / "summary.json"
        manifest_path = run_dir / "manifest.json"
        summary_path.write_text(
            json.dumps(
                {
                    "status": "completed" if passed else "finished",
                    "completed": passed,
                    "returncode": 0,
                }
            )
            + "\n",
            encoding="utf-8",
        )
        manifest_path.write_text("{}", encoding="utf-8")
        (run_dir / "agent.log").write_text("agent log\n", encoding="utf-8")
        (run_dir / "prompt.txt").write_text(current_prompt, encoding="utf-8")
        return {
            "repo_url": repo_url,
            "repo_name": repo_url.rsplit("/", 1)[-1],
            "run_dir": run_dir,
            "returncode": 0,
            "completed": passed,
            "status": "completed" if passed else "finished",
            "summary_path": summary_path,
            "manifest_path": manifest_path,
        }

    monkeypatch.setattr("experiments.harness.code2workspace_harness.runner.run_repo_task", fake_run_repo_task)

    try:
        report = run_experiment(experiment=experiment, max_iterations=1)
    finally:
        if original is None:
            if surface_target.exists():
                surface_target.unlink()
        else:
            surface_target.write_text(original, encoding="utf-8")

    run_root = Path(report.run_root)
    assert report.final.changed_surfaces == ("prompt",)
    assert len(report.iterations) == 1
    assert report.iterations[0].candidate is not None
    assert report.iterations[0].candidate.accepted is True
    assert run_root.joinpath("history", "visible", "iterations", "001", "decision.json").exists()
    assert run_root.joinpath("history", "visible", "iterations", "001", "proposer_workspace", "surface_manifest.json").exists()
    assert run_root.joinpath("history", "visible", "iterations", "001", "proposer_workspace", "train_failures.json").exists()
    assert run_root.joinpath("history", "visible", "iterations", "001", "proposer_workspace", "result.json").exists()
    assert run_root.joinpath("history", "private", "holdout", "iter-001", "result.json").exists()
    assert run_root.joinpath("report.json").exists()


def test_multi_source_report_helper_survives_surface_override(tmp_path: Path) -> None:
    helper = (
        repo_root()
        / ".code2workspace"
        / "skills"
        / "multi-source-report"
        / "scripts"
        / "report_tool.py"
    )
    skill_file = (
        repo_root()
        / ".code2workspace"
        / "skills"
        / "multi-source-report"
        / "SKILL.md"
    )
    config = tmp_path / "experiment.toml"
    config.write_text(
        f"""
[experiment]
name = "epidemic-surface-demo"
workspace_root = "{tmp_path / "workspace"}"
output_root = "{tmp_path / "output"}"

[surfaces.report_skill]
kind = "workspace_file"
target = "{skill_file.relative_to(repo_root())}"
filename = "SKILL.md"
base_value = {json.dumps(skill_file.read_text(encoding="utf-8"))}

[[cases]]
case_id = "train-case"
repo_url = "https://github.com/example/train-repo"
split = "train"
max_runtime_minutes = 15
""".strip()
        + "\n",
        encoding="utf-8",
    )
    experiment = load_experiment(config)
    baseline = build_baseline_variant(experiment)
    variant = type(baseline)(
        label="skill-edit",
        changed_surfaces=("report_skill",),
        values={"report_skill": baseline.values["report_skill"] + "\n<!-- test override -->\n"},
    )
    out_dir = tmp_path / "report-run"

    with workspace_override_context(experiment, variant):
        completed = subprocess.run(
            [
                sys.executable,
                str(helper),
                "init",
                "--topic",
                "Harness regression report",
                "--output-dir",
                str(out_dir),
            ],
            cwd=repo_root(),
            capture_output=True,
            text=True,
            check=False,
        )

    assert completed.returncode == 0
    assert out_dir.joinpath("manifest.json").exists()
    assert out_dir.joinpath("lanes", "01_monitoring.md").exists()


def test_run_experiment_supports_deepagents_proposer(tmp_path: Path, monkeypatch) -> None:
    surface_relpath = f"experiments/harness/surfaces/{tmp_path.name}_prompt.txt"
    config = write_config(
        tmp_path,
        surface_relpath=surface_relpath,
        better_agent_model="gpt-test",
    )
    experiment = load_experiment(config)
    surface_target = repo_root() / surface_relpath
    surface_target.parent.mkdir(parents=True, exist_ok=True)
    if surface_target.exists():
        original = surface_target.read_text(encoding="utf-8")
    else:
        original = None

    def fake_deepagents_proposer(*, experiment, workspace) -> None:
        del experiment
        workspace.surface_files["prompt"].write_text("better prompt\n", encoding="utf-8")
        workspace.proposal_file.write_text(
            "# Proposal\n\n- Summary: improve deepagents outer loop\n",
            encoding="utf-8",
        )
        (workspace.root / "outer_agent_result.json").write_text(
            json.dumps({"final_message": "updated prompt"}, indent=2) + "\n",
            encoding="utf-8",
        )

    def fake_run_repo_task(repo_url, *, workspace_root, output_root, max_runtime_minutes):
        del workspace_root, max_runtime_minutes
        current_prompt = surface_target.read_text(encoding="utf-8")
        passed = current_prompt == "better prompt\n"
        run_dir = output_root / repo_url.rsplit("/", 1)[-1] / "run"
        run_dir.mkdir(parents=True, exist_ok=True)
        summary_path = run_dir / "summary.json"
        manifest_path = run_dir / "manifest.json"
        summary_path.write_text(
            json.dumps(
                {
                    "status": "completed" if passed else "finished",
                    "completed": passed,
                    "returncode": 0,
                }
            )
            + "\n",
            encoding="utf-8",
        )
        manifest_path.write_text("{}", encoding="utf-8")
        return {
            "repo_url": repo_url,
            "repo_name": repo_url.rsplit("/", 1)[-1],
            "run_dir": run_dir,
            "returncode": 0,
            "completed": passed,
            "status": "completed" if passed else "finished",
            "summary_path": summary_path,
            "manifest_path": manifest_path,
        }

    monkeypatch.setattr(
        "experiments.harness.code2workspace_harness.agent.invoke_deepagents_proposer",
        fake_deepagents_proposer,
    )
    monkeypatch.setattr("experiments.harness.code2workspace_harness.runner.run_repo_task", fake_run_repo_task)

    try:
        report = run_experiment(experiment=experiment, max_iterations=1)
    finally:
        if original is None:
            if surface_target.exists():
                surface_target.unlink()
        else:
            surface_target.write_text(original, encoding="utf-8")

    run_root = Path(report.run_root)
    assert report.final.changed_surfaces == ("prompt",)
    assert report.iterations[0].candidate is not None
    assert report.iterations[0].candidate.accepted is True
    assert run_root.joinpath(
        "history", "visible", "iterations", "001", "proposer_workspace", "outer_agent_result.json"
    ).exists()


def test_invoke_deepagents_proposer_uses_imported_backend_and_records_result(
    tmp_path: Path,
    monkeypatch,
) -> None:
    surface_relpath = f"experiments/harness/surfaces/{tmp_path.name}_prompt.txt"
    config = write_config(
        tmp_path,
        surface_relpath=surface_relpath,
        better_agent_model="gpt-test",
        better_agent_max_turns=7,
        better_agent_deepagents_root="/tmp/deepagents",
    )
    experiment = load_experiment(config)
    baseline = build_baseline_variant(experiment)
    layout_root = tmp_path / "layout"
    from experiments.harness.code2workspace_harness.core import RunLayout

    layout = RunLayout(output_root=layout_root, experiment_name=experiment.name)
    train_result = SplitResult(
        split="train",
        variant=baseline.key,
        passed=0,
        total=1,
        outcomes=(),
    )
    workspace = build_proposer_workspace(
        experiment=experiment,
        current=baseline,
        train_result=train_result,
        layout=layout,
        iteration=1,
    )

    class FakeFilesystemBackend:
        def __init__(self, *, root_dir: str, virtual_mode: bool) -> None:
            self.root_dir = root_dir
            self.virtual_mode = virtual_mode

    class FakeHumanMessage:
        def __init__(self, *, content: str) -> None:
            self.content = content

    class FakeAIMessage:
        type = "ai"

        def __init__(self, content: str) -> None:
            self.content = content

    class FakeAgent:
        def __init__(self, backend: FakeFilesystemBackend) -> None:
            self.backend = backend

        def invoke(self, payload, *, config):
            assert config == {"recursion_limit": 7}
            assert payload["messages"][0].content.startswith("Read /task.md first.")
            root = Path(self.backend.root_dir)
            root.joinpath("current", Path(surface_relpath).name).write_text(
                "better prompt\n",
                encoding="utf-8",
            )
            root.joinpath("proposal.md").write_text(
                "# Proposal\n\n- Summary: improved through imported deepagents path\n",
                encoding="utf-8",
            )
            return {"messages": [FakeAIMessage("updated prompt")]}

    def fake_create_deep_agent(*, model, system_prompt, backend):
        assert model == "gpt-test"
        assert "Better Agent" in system_prompt
        assert backend.virtual_mode is True
        return FakeAgent(backend)

    original_import_module = importlib.import_module

    def fake_import_module(name: str):
        if name == "deepagents":
            return types.SimpleNamespace(create_deep_agent=fake_create_deep_agent)
        if name == "deepagents.backends":
            return types.SimpleNamespace(FilesystemBackend=FakeFilesystemBackend)
        if name == "langchain_core.messages":
            return types.SimpleNamespace(HumanMessage=FakeHumanMessage)
        return original_import_module(name)

    monkeypatch.setattr(
        "experiments.harness.code2workspace_harness.agent.importlib.import_module",
        fake_import_module,
    )

    invoke_deepagents_proposer(experiment=experiment, workspace=workspace)

    result_path = workspace.root / "outer_agent_result.json"
    request_path = workspace.root / "outer_agent_request.json"
    assert workspace.surface_files["prompt"].read_text(encoding="utf-8") == "better prompt\n"
    assert "improved through imported deepagents path" in workspace.proposal_file.read_text(
        encoding="utf-8"
    )
    assert result_path.exists()
    assert request_path.exists()
    payload = json.loads(result_path.read_text(encoding="utf-8"))
    request = json.loads(request_path.read_text(encoding="utf-8"))
    assert payload["final_message"] == "updated prompt"
    assert request["deepagents_root"] == "/tmp/deepagents"
    assert request["max_turns"] == 7


def test_invoke_deepagents_proposer_writes_error_artifact_on_failure(tmp_path: Path, monkeypatch) -> None:
    surface_relpath = f"experiments/harness/surfaces/{tmp_path.name}_prompt.txt"
    config = write_config(
        tmp_path,
        surface_relpath=surface_relpath,
        better_agent_model="gpt-test",
    )
    experiment = load_experiment(config)
    baseline = build_baseline_variant(experiment)
    from experiments.harness.code2workspace_harness.core import RunLayout

    layout = RunLayout(output_root=tmp_path / "layout", experiment_name=experiment.name)
    workspace = build_proposer_workspace(
        experiment=experiment,
        current=baseline,
        train_result=SplitResult(
            split="train",
            variant=baseline.key,
            passed=0,
            total=1,
            outcomes=(),
        ),
        layout=layout,
        iteration=1,
    )

    original_import_module = importlib.import_module

    def fake_import_module(name: str):
        if name == "deepagents":
            raise ImportError("missing deepagents runtime")
        return original_import_module(name)

    monkeypatch.setattr(
        "experiments.harness.code2workspace_harness.agent.importlib.import_module",
        fake_import_module,
    )

    with pytest.raises(RuntimeError, match="Could not import deepagents"):
        invoke_deepagents_proposer(experiment=experiment, workspace=workspace)

    error_path = workspace.root / "outer_agent_error.json"
    assert error_path.exists()
    payload = json.loads(error_path.read_text(encoding="utf-8"))
    assert payload["error_type"] == "RuntimeError"
    assert "Could not import deepagents" in payload["error"]
