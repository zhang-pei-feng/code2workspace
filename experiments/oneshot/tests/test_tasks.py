import json
from pathlib import Path

from experiments.oneshot.run_repo_batch import run_repo_batch
from experiments.oneshot.run_repo_task import RepoPreparationError, run_repo_task
from experiments.oneshot.tasks import (
    build_repo_task_prompt,
    build_repo_task_spec,
    load_repo_urls,
)


def write_completed_artifacts(repo_dir: Path, repo_url: str) -> None:
    spec = build_repo_task_spec(repo_url)
    (repo_dir / spec.dockerfile_name).write_text("FROM debian:bookworm-slim\n", encoding="utf-8")
    (repo_dir / spec.wdl_name).write_text(
        'version 1.0\nworkflow demo { }\n# runtime docker: "spades"\n',
        encoding="utf-8",
    )
    (repo_dir / "inputs.json").write_text("{}\n", encoding="utf-8")

    docker_test = repo_dir / "results" / "docker_test"
    docker_test.mkdir(parents=True, exist_ok=True)
    (docker_test / "docker_build_retry.log").write_text(
        "#11 naming to docker.io/library/spades done\n",
        encoding="utf-8",
    )
    (docker_test / "docker_image_inspect.log").write_text(
        '{ "RepoTags": ["spades:latest"] }\n',
        encoding="utf-8",
    )
    (docker_test / "docker_run_test.log").write_text(
        "SPAdes test execution\nTEST PASSED CORRECTLY\n",
        encoding="utf-8",
    )
    spades_test = docker_test / "spades_test"
    spades_test.mkdir(parents=True, exist_ok=True)
    (spades_test / "contigs.fasta").write_text(">contig\nACGT\n", encoding="utf-8")

    wdl_file = repo_dir / "results" / "wdl_file"
    wdl_file.mkdir(parents=True, exist_ok=True)
    (wdl_file / spec.wdl_name).write_text(
        'version 1.0\n# runtime docker: "spades"\n',
        encoding="utf-8",
    )
    (wdl_file / "inputs.json").write_text("{}\n", encoding="utf-8")

    wdl_result = repo_dir / "results" / "wdl_result"
    wdl_result.mkdir(parents=True, exist_ok=True)
    (wdl_result / "miniwdl_run_retry.log").write_text(
        "miniwdl run spades.wdl\n"
        "workflow done\n",
        encoding="utf-8",
    )
    (wdl_result / "outputs_retry.json").write_text(
        json.dumps({"outputs": {"spades.contigs": str(wdl_result / "contigs.fasta")}}) + "\n",
        encoding="utf-8",
    )
    (wdl_result / "contigs.fasta").write_text(">contig\nACGT\n", encoding="utf-8")


def write_flye_completed_artifacts_without_root_wdl(repo_dir: Path) -> None:
    spec = build_repo_task_spec("https://github.com/fenderglass/Flye")
    (repo_dir / spec.dockerfile_name).write_text("FROM python:3.12-slim\n", encoding="utf-8")

    docker_test = repo_dir / "results" / "docker_test"
    docker_test.mkdir(parents=True, exist_ok=True)
    (docker_test / "docker_build.log").write_text(
        "#11 naming to docker.io/library/flye done\n",
        encoding="utf-8",
    )
    (docker_test / "docker_image_inspect.log").write_text(
        '{ "RepoTags": ["flye:latest"] }\n',
        encoding="utf-8",
    )
    (docker_test / "docker_run.log").write_text(
        "Flye toy run completed\n",
        encoding="utf-8",
    )
    toy_run = docker_test / "toy_run"
    toy_run.mkdir(parents=True, exist_ok=True)
    (toy_run / "assembly.fasta").write_text(">contig\nACGT\n", encoding="utf-8")

    wdl_file = repo_dir / "results" / "wdl_file"
    wdl_file.mkdir(parents=True, exist_ok=True)
    (wdl_file / spec.wdl_name).write_text(
        'version 1.0\nworkflow FlyeWorkflow {}\ntask RunFlye { runtime { docker: "flye" } }\n',
        encoding="utf-8",
    )
    (wdl_file / "inputs.json").write_text("{}\n", encoding="utf-8")

    wdl_result = repo_dir / "results" / "wdl_result"
    wdl_result.mkdir(parents=True, exist_ok=True)
    (wdl_result / "miniwdl_run.log").write_text(
        "miniwdl run Flye.wdl\n"
        "workflow done\n",
        encoding="utf-8",
    )
    (wdl_result / "outputs.json").write_text(
        json.dumps({"outputs": {"FlyeWorkflow.assembly": str(wdl_result / "assembly.fasta")}}) + "\n",
        encoding="utf-8",
    )
    (wdl_result / "assembly.fasta").write_text(">contig\nACGT\n", encoding="utf-8")


def write_canu_completed_artifacts_with_named_run_log(repo_dir: Path) -> None:
    spec = build_repo_task_spec("https://github.com/marbl/canu")
    (repo_dir / spec.dockerfile_name).write_text("FROM ubuntu:22.04\n", encoding="utf-8")
    (repo_dir / spec.wdl_name).write_text(
        'version 1.0\nworkflow canu_workflow { }\n# runtime docker: "canu"\n',
        encoding="utf-8",
    )
    (repo_dir / "inputs.json").write_text("{}\n", encoding="utf-8")

    docker_test = repo_dir / "results" / "docker_test"
    docker_test.mkdir(parents=True, exist_ok=True)
    (docker_test / "docker_build_retry.log").write_text(
        "#11 naming to docker.io/library/canu done\n",
        encoding="utf-8",
    )
    (docker_test / "docker_canu_meryl.log").write_text(
        "Stop requested after 'meryl'\n",
        encoding="utf-8",
    )
    real_output = docker_test / "ecoli_meryl"
    real_output.mkdir(parents=True, exist_ok=True)
    (real_output / "ecoli.report").write_text("report\n", encoding="utf-8")

    wdl_file = repo_dir / "results" / "wdl_file"
    wdl_file.mkdir(parents=True, exist_ok=True)
    (wdl_file / spec.wdl_name).write_text(
        'version 1.0\nworkflow canu_workflow { }\n# runtime docker: "canu"\n',
        encoding="utf-8",
    )
    (wdl_file / "inputs.json").write_text("{}\n", encoding="utf-8")
    (wdl_file / "options.json").write_text("{}\n", encoding="utf-8")

    wdl_result = repo_dir / "results" / "wdl_result"
    wdl_result.mkdir(parents=True, exist_ok=True)
    (wdl_result / "miniwdl_run.log").write_text(
        "miniwdl run canu.wdl\n"
        "workflow done\n",
        encoding="utf-8",
    )
    (wdl_result / "outputs.json").write_text(
        json.dumps({"outputs": {"canu_workflow.report": str(wdl_result / "ecoli.report")}}) + "\n",
        encoding="utf-8",
    )
    (wdl_result / "ecoli.report").write_text("report\n", encoding="utf-8")


def write_trinity_completed_artifacts_with_numbered_retry_metadata(repo_dir: Path) -> None:
    spec = build_repo_task_spec("https://github.com/trinityrnaseq/trinityrnaseq")
    (repo_dir / spec.dockerfile_name).write_text("FROM ubuntu:22.04\n", encoding="utf-8")
    (repo_dir / spec.wdl_name).write_text(
        'version 1.0\nworkflow trinityrnaseq { }\n# runtime docker: "trinityrnaseq"\n',
        encoding="utf-8",
    )
    (repo_dir / "inputs.json").write_text("{}\n", encoding="utf-8")

    docker_test = repo_dir / "results" / "docker_test"
    docker_test.mkdir(parents=True, exist_ok=True)
    (docker_test / "docker_build_retry.log").write_text(
        "#11 naming to docker.io/library/trinityrnaseq done\n",
        encoding="utf-8",
    )
    (docker_test / "docker_run_retry.log").write_text(
        "Trinity docker run completed\n",
        encoding="utf-8",
    )
    (docker_test / "trinity_out_dir.Trinity.fasta").write_text(">contig\nACGT\n", encoding="utf-8")

    wdl_file = repo_dir / "results" / "wdl_file"
    wdl_file.mkdir(parents=True, exist_ok=True)
    (wdl_file / spec.wdl_name).write_text(
        'version 1.0\nworkflow trinityrnaseq { }\n# runtime docker: "trinityrnaseq"\n',
        encoding="utf-8",
    )
    (wdl_file / "inputs.json").write_text("{}\n", encoding="utf-8")
    (wdl_file / "options.json").write_text("{}\n", encoding="utf-8")

    wdl_result = repo_dir / "results" / "wdl_result"
    wdl_result.mkdir(parents=True, exist_ok=True)
    (wdl_result / "miniwdl_run_retry2.log").write_text(
        "miniwdl run trinityrnaseq.wdl\n"
        "workflow done\n",
        encoding="utf-8",
    )
    (wdl_result / "outputs_retry2.json").write_text(
        json.dumps({"outputs": {"trinityrnaseq.fasta": str(wdl_result / "trinity_out_dir.Trinity.fasta")}}) + "\n",
        encoding="utf-8",
    )
    (wdl_result / "trinity_out_dir.Trinity.fasta").write_text(">contig\nACGT\n", encoding="utf-8")


def test_build_repo_task_spec_normalizes_prefix() -> None:
    spec = build_repo_task_spec("https://github.com/jaleezyy/covid-19-signal")

    assert spec.repo_name == "covid-19-signal"
    assert spec.image_name == "covid-19-signal"
    assert spec.artifact_prefix == "covid_19_signal"


def test_build_repo_task_prompt_contains_required_outputs() -> None:
    prompt = build_repo_task_prompt("https://github.com/ablab/spades")

    assert "spades_Dockerfile" in prompt
    assert "spades.wdl" in prompt
    assert "results/docker_test" in prompt
    assert "COMPLETED" in prompt


def test_build_repo_task_prompt_forces_fast_transition_from_discovery_to_build() -> None:
    prompt = build_repo_task_prompt("https://github.com/ablab/spades")

    assert "不要把仓库里旧的 results、旧的 WDL、旧的 Dockerfile、旧的 miniwdl 执行痕迹当作这次任务已经完成的证据" in prompt
    assert "一旦已经定位到可运行的真实命令和输入数据，接下来的少量动作应当直接用于" in prompt
    assert "写 Dockerfile、执行第一次真实 `docker build`" in prompt


def test_build_repo_task_prompt_warns_about_miniwdl_container_environment() -> None:
    prompt = build_repo_task_prompt("https://github.com/artic-network/fieldbioinformatics")

    assert "运行 miniwdl 时优先加 `--as-me`" in prompt
    assert "不要依赖镜像 ENTRYPOINT、登录 shell 初始化或 Conda/Mamba 自动激活来让主命令出现在 PATH 里" in prompt


def test_load_repo_urls_skips_comments(tmp_path) -> None:
    targets = tmp_path / "targets.txt"
    targets.write_text(
        "# comment\nhttps://github.com/ablab/spades\n\nhttps://github.com/marbl/canu\n",
        encoding="utf-8",
    )

    urls = load_repo_urls(targets)

    assert urls == [
        "https://github.com/ablab/spades",
        "https://github.com/marbl/canu",
    ]


def test_run_repo_task_writes_manifest_and_summary(tmp_path, monkeypatch) -> None:
    workspace_root = tmp_path / "workspace"
    output_root = tmp_path / "output"
    repo_dir = workspace_root / "spades"
    repo_dir.mkdir(parents=True)

    monkeypatch.setattr(
        "experiments.oneshot.run_repo_task.ensure_repo",
        lambda repo_url, workspace_root, **kwargs: repo_dir,
    )
    captured = {}

    def fake_stream_command(cmd, *, cwd, log_path, max_runtime_seconds):
        captured["cmd"] = cmd
        captured["cwd"] = cwd
        captured["max_runtime_seconds"] = max_runtime_seconds
        write_completed_artifacts(cwd, "https://github.com/ablab/spades")
        return 0, "real log\nCOMPLETED\n", False, False

    monkeypatch.setattr("experiments.oneshot.run_repo_task.stream_command", fake_stream_command)

    result = run_repo_task(
        "https://github.com/ablab/spades",
        workspace_root=workspace_root,
        output_root=output_root,
    )

    manifest = json.loads(result["manifest_path"].read_text(encoding="utf-8"))
    summary = json.loads(result["summary_path"].read_text(encoding="utf-8"))
    assert result["completed"] is True
    assert manifest["repo_name"] == "spades"
    assert manifest["prompt_file"].endswith("prompt.txt")
    assert manifest["max_runtime_minutes"] == 30
    assert manifest["completed"] is True
    assert manifest["completion_rubric_file"].endswith("completion_rubric.txt")
    assert summary["completed"] is True
    assert summary["completion_judgment"]["completed"] is True
    assert summary["completion_judgment"]["failed_checks"] == []
    assert summary["returncode"] == 0
    assert summary["status"] == "completed"
    assert summary["max_runtime_minutes"] == 30
    assert captured["cwd"] == repo_dir
    assert captured["cmd"][3].endswith("/libs/cli")
    assert "--session-workdir-mode" in captured["cmd"]
    assert "inherit" in captured["cmd"]
    assert captured["max_runtime_seconds"] == 1800


def test_run_repo_task_does_not_accept_stale_artifacts(tmp_path, monkeypatch) -> None:
    workspace_root = tmp_path / "workspace"
    output_root = tmp_path / "output"
    repo_dir = workspace_root / "spades"
    repo_dir.mkdir(parents=True)
    write_completed_artifacts(repo_dir, "https://github.com/ablab/spades")

    monkeypatch.setattr(
        "experiments.oneshot.run_repo_task.ensure_repo",
        lambda repo_url, workspace_root, **kwargs: repo_dir,
    )
    monkeypatch.setattr(
        "experiments.oneshot.run_repo_task.stream_command",
        lambda cmd, *, cwd, log_path, max_runtime_seconds: (0, "real log\nCOMPLETED\n", False, False),
    )

    result = run_repo_task(
        "https://github.com/ablab/spades",
        workspace_root=workspace_root,
        output_root=output_root,
    )

    summary = json.loads(result["summary_path"].read_text(encoding="utf-8"))
    assert result["completed"] is False
    assert result["status"] == "finished"
    assert summary["completion_judgment"]["completed"] is False
    assert "dockerfile_written" in summary["completion_judgment"]["failed_checks"]
    assert "wdl_outputs_written" in summary["completion_judgment"]["failed_checks"]


def test_run_repo_task_cleans_previous_generated_artifacts_before_streaming(
    tmp_path, monkeypatch
) -> None:
    workspace_root = tmp_path / "workspace"
    output_root = tmp_path / "output"
    repo_dir = workspace_root / "spades"
    repo_dir.mkdir(parents=True)
    write_completed_artifacts(repo_dir, "https://github.com/ablab/spades")
    (repo_dir / "miniwdl_run_state").mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(
        "experiments.oneshot.run_repo_task.ensure_repo",
        lambda repo_url, workspace_root, **kwargs: repo_dir,
    )

    def fake_stream_command(cmd, *, cwd, log_path, max_runtime_seconds):
        del cmd, log_path, max_runtime_seconds
        assert not (cwd / "spades_Dockerfile").exists()
        assert not (cwd / "spades.wdl").exists()
        assert not (cwd / "inputs.json").exists()
        assert not (cwd / "miniwdl_run_state").exists()
        assert not (cwd / "results" / "docker_test").exists()
        assert not (cwd / "results" / "wdl_result").exists()
        assert not (cwd / "results" / "wdl_file").exists()
        write_completed_artifacts(cwd, "https://github.com/ablab/spades")
        return 0, "real log\nCOMPLETED\n", False, False

    monkeypatch.setattr("experiments.oneshot.run_repo_task.stream_command", fake_stream_command)

    result = run_repo_task(
        "https://github.com/ablab/spades",
        workspace_root=workspace_root,
        output_root=output_root,
    )

    summary = json.loads(result["summary_path"].read_text(encoding="utf-8"))
    assert result["completed"] is True
    assert result["status"] == "completed"
    assert summary["completion_judgment"]["completed"] is True


def test_run_repo_task_quarantines_generated_directories_when_delete_fails(
    tmp_path, monkeypatch
) -> None:
    workspace_root = tmp_path / "workspace"
    output_root = tmp_path / "output"
    repo_dir = workspace_root / "spades"
    repo_dir.mkdir(parents=True)
    write_completed_artifacts(repo_dir, "https://github.com/ablab/spades")
    (repo_dir / "miniwdl_run_state").mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(
        "experiments.oneshot.run_repo_task.ensure_repo",
        lambda repo_url, workspace_root, **kwargs: repo_dir,
    )

    original_rmtree = __import__("shutil").rmtree

    def flaky_rmtree(path, *args, **kwargs):
        if Path(path).name in {"docker_test", "wdl_result", "wdl_file", "miniwdl_run_state"}:
            raise PermissionError("root-owned test fixture")
        return original_rmtree(path, *args, **kwargs)

    monkeypatch.setattr("experiments.oneshot.run_repo_task.shutil.rmtree", flaky_rmtree)

    def fake_stream_command(cmd, *, cwd, log_path, max_runtime_seconds):
        del cmd, log_path, max_runtime_seconds
        assert not (cwd / "results" / "docker_test").exists()
        assert not (cwd / "results" / "wdl_result").exists()
        assert not (cwd / "results" / "wdl_file").exists()
        assert not (cwd / "miniwdl_run_state").exists()
        assert list((cwd / "results").glob("docker_test.stale.*"))
        assert list((cwd / "results").glob("wdl_result.stale.*"))
        assert list((cwd / "results").glob("wdl_file.stale.*"))
        assert list(cwd.glob("miniwdl_run_state.stale.*"))
        write_completed_artifacts(cwd, "https://github.com/ablab/spades")
        return 0, "real log\nCOMPLETED\n", False, False

    monkeypatch.setattr("experiments.oneshot.run_repo_task.stream_command", fake_stream_command)

    result = run_repo_task(
        "https://github.com/ablab/spades",
        workspace_root=workspace_root,
        output_root=output_root,
    )

    summary = json.loads(result["summary_path"].read_text(encoding="utf-8"))
    assert result["completed"] is True
    assert result["status"] == "completed"
    assert summary["completion_judgment"]["completed"] is True


def test_run_repo_task_accepts_flye_log_and_copied_wdl_only(
    tmp_path, monkeypatch
) -> None:
    workspace_root = tmp_path / "workspace"
    output_root = tmp_path / "output"
    repo_dir = workspace_root / "Flye"
    repo_dir.mkdir(parents=True)

    monkeypatch.setattr(
        "experiments.oneshot.run_repo_task.ensure_repo",
        lambda repo_url, workspace_root, **kwargs: repo_dir,
    )

    def fake_stream_command(cmd, *, cwd, log_path, max_runtime_seconds):
        del cmd, log_path, max_runtime_seconds
        write_flye_completed_artifacts_without_root_wdl(cwd)
        return 0, "real log\nCOMPLETED\n", False, False

    monkeypatch.setattr("experiments.oneshot.run_repo_task.stream_command", fake_stream_command)

    result = run_repo_task(
        "https://github.com/fenderglass/Flye",
        workspace_root=workspace_root,
        output_root=output_root,
    )

    summary = json.loads(result["summary_path"].read_text(encoding="utf-8"))
    assert result["completed"] is True
    assert result["status"] == "completed"
    assert summary["completion_judgment"]["completed"] is True


def test_run_repo_task_accepts_nonstandard_named_docker_run_log(
    tmp_path, monkeypatch
) -> None:
    workspace_root = tmp_path / "workspace"
    output_root = tmp_path / "output"
    repo_dir = workspace_root / "canu"
    repo_dir.mkdir(parents=True)

    monkeypatch.setattr(
        "experiments.oneshot.run_repo_task.ensure_repo",
        lambda repo_url, workspace_root, **kwargs: repo_dir,
    )

    def fake_stream_command(cmd, *, cwd, log_path, max_runtime_seconds):
        del cmd, log_path, max_runtime_seconds
        write_canu_completed_artifacts_with_named_run_log(cwd)
        return 0, "real log\nCOMPLETED\n", False, False

    monkeypatch.setattr("experiments.oneshot.run_repo_task.stream_command", fake_stream_command)

    result = run_repo_task(
        "https://github.com/marbl/canu",
        workspace_root=workspace_root,
        output_root=output_root,
    )

    summary = json.loads(result["summary_path"].read_text(encoding="utf-8"))
    assert result["completed"] is True
    assert result["status"] == "completed"
    assert summary["completion_judgment"]["completed"] is True


def test_run_repo_task_accepts_numbered_retry_miniwdl_outputs_and_logs(
    tmp_path, monkeypatch
) -> None:
    workspace_root = tmp_path / "workspace"
    output_root = tmp_path / "output"
    repo_dir = workspace_root / "trinityrnaseq"
    repo_dir.mkdir(parents=True)

    monkeypatch.setattr(
        "experiments.oneshot.run_repo_task.ensure_repo",
        lambda repo_url, workspace_root, **kwargs: repo_dir,
    )

    def fake_stream_command(cmd, *, cwd, log_path, max_runtime_seconds):
        del cmd, log_path, max_runtime_seconds
        write_trinity_completed_artifacts_with_numbered_retry_metadata(cwd)
        return 0, "real log\nCOMPLETED\n", False, False

    monkeypatch.setattr("experiments.oneshot.run_repo_task.stream_command", fake_stream_command)

    result = run_repo_task(
        "https://github.com/trinityrnaseq/trinityrnaseq",
        workspace_root=workspace_root,
        output_root=output_root,
    )

    summary = json.loads(result["summary_path"].read_text(encoding="utf-8"))
    assert result["completed"] is True
    assert result["status"] == "completed"
    assert summary["completion_judgment"]["completed"] is True


def test_run_repo_task_records_interrupted_status(tmp_path, monkeypatch) -> None:
    workspace_root = tmp_path / "workspace"
    output_root = tmp_path / "output"
    repo_dir = workspace_root / "spades"
    repo_dir.mkdir(parents=True)

    monkeypatch.setattr(
        "experiments.oneshot.run_repo_task.ensure_repo",
        lambda repo_url, workspace_root, **kwargs: repo_dir,
    )
    monkeypatch.setattr(
        "experiments.oneshot.run_repo_task.stream_command",
        lambda cmd, *, cwd, log_path, max_runtime_seconds: (130, "partial log\n", True, False),
    )

    result = run_repo_task(
        "https://github.com/ablab/spades",
        workspace_root=workspace_root,
        output_root=output_root,
    )

    manifest = json.loads(result["manifest_path"].read_text(encoding="utf-8"))
    summary = json.loads(result["summary_path"].read_text(encoding="utf-8"))
    assert result["completed"] is False
    assert result["status"] == "interrupted"
    assert manifest["status"] == "interrupted"
    assert summary["status"] == "interrupted"


def test_run_repo_task_records_timed_out_status(tmp_path, monkeypatch) -> None:
    workspace_root = tmp_path / "workspace"
    output_root = tmp_path / "output"
    repo_dir = workspace_root / "spades"
    repo_dir.mkdir(parents=True)

    monkeypatch.setattr(
        "experiments.oneshot.run_repo_task.ensure_repo",
        lambda repo_url, workspace_root, **kwargs: repo_dir,
    )
    monkeypatch.setattr(
        "experiments.oneshot.run_repo_task.stream_command",
        lambda cmd, *, cwd, log_path, max_runtime_seconds: (124, "partial log\n", False, True),
    )

    result = run_repo_task(
        "https://github.com/ablab/spades",
        workspace_root=workspace_root,
        output_root=output_root,
        max_runtime_minutes=15,
    )

    manifest = json.loads(result["manifest_path"].read_text(encoding="utf-8"))
    summary = json.loads(result["summary_path"].read_text(encoding="utf-8"))
    assert result["completed"] is False
    assert result["status"] == "timed_out"
    assert manifest["status"] == "timed_out"
    assert manifest["max_runtime_minutes"] == 15
    assert summary["status"] == "timed_out"
    assert summary["max_runtime_minutes"] == 15


def test_run_repo_task_retries_transient_remote_exception_once(
    tmp_path, monkeypatch
) -> None:
    workspace_root = tmp_path / "workspace"
    output_root = tmp_path / "output"
    repo_dir = workspace_root / "spades"
    repo_dir.mkdir(parents=True)

    monkeypatch.setattr(
        "experiments.oneshot.run_repo_task.ensure_repo",
        lambda repo_url, workspace_root, **kwargs: repo_dir,
    )

    attempts = {"count": 0}

    def fake_stream_command(cmd, *, cwd, log_path, max_runtime_seconds):
        del cmd, max_runtime_seconds
        attempts["count"] += 1
        if attempts["count"] == 1:
            log_path.write_text(
                "Unexpected error (RemoteException): {'error': 'RemoteProtocolError', 'message': 'An internal error occurred'}\n",
                encoding="utf-8",
            )
            return (
                1,
                "Unexpected error (RemoteException): {'error': 'RemoteProtocolError', 'message': 'An internal error occurred'}\n",
                False,
                False,
            )
        write_completed_artifacts(cwd, "https://github.com/ablab/spades")
        log_path.write_text("real log\nCOMPLETED\n", encoding="utf-8")
        return 0, "real log\nCOMPLETED\n", False, False

    monkeypatch.setattr("experiments.oneshot.run_repo_task.stream_command", fake_stream_command)

    result = run_repo_task(
        "https://github.com/ablab/spades",
        workspace_root=workspace_root,
        output_root=output_root,
    )

    summary = json.loads(result["summary_path"].read_text(encoding="utf-8"))
    retry_log = result["run_dir"] / "agent.retry1.log"
    assert attempts["count"] == 2
    assert result["completed"] is True
    assert result["status"] == "completed"
    assert summary["returncode"] == 0
    assert retry_log.exists()
    assert "RemoteProtocolError" in retry_log.read_text(encoding="utf-8")


def test_run_repo_task_retries_transient_remote_exception_twice_before_success(
    tmp_path, monkeypatch
) -> None:
    workspace_root = tmp_path / "workspace"
    output_root = tmp_path / "output"
    repo_dir = workspace_root / "spades"
    repo_dir.mkdir(parents=True)

    monkeypatch.setattr(
        "experiments.oneshot.run_repo_task.ensure_repo",
        lambda repo_url, workspace_root, **kwargs: repo_dir,
    )

    attempts = {"count": 0}

    def fake_stream_command(cmd, *, cwd, log_path, max_runtime_seconds):
        del cmd, max_runtime_seconds
        attempts["count"] += 1
        if attempts["count"] < 3:
            log_path.write_text(
                "Unexpected error (RemoteException): {'error': 'APIError', 'message': 'An internal error occurred'}\n",
                encoding="utf-8",
            )
            return (
                1,
                "Unexpected error (RemoteException): {'error': 'APIError', 'message': 'An internal error occurred'}\n",
                False,
                False,
            )
        write_completed_artifacts(cwd, "https://github.com/ablab/spades")
        log_path.write_text("real log\nCOMPLETED\n", encoding="utf-8")
        return 0, "real log\nCOMPLETED\n", False, False

    monkeypatch.setattr("experiments.oneshot.run_repo_task.stream_command", fake_stream_command)

    result = run_repo_task(
        "https://github.com/ablab/spades",
        workspace_root=workspace_root,
        output_root=output_root,
    )

    summary = json.loads(result["summary_path"].read_text(encoding="utf-8"))
    assert attempts["count"] == 3
    assert result["completed"] is True
    assert result["status"] == "completed"
    assert summary["returncode"] == 0
    assert (result["run_dir"] / "agent.retry1.log").exists()
    assert (result["run_dir"] / "agent.retry2.log").exists()


def test_run_repo_task_does_not_retry_generic_nonzero_exit(
    tmp_path, monkeypatch
) -> None:
    workspace_root = tmp_path / "workspace"
    output_root = tmp_path / "output"
    repo_dir = workspace_root / "spades"
    repo_dir.mkdir(parents=True)

    monkeypatch.setattr(
        "experiments.oneshot.run_repo_task.ensure_repo",
        lambda repo_url, workspace_root, **kwargs: repo_dir,
    )

    attempts = {"count": 0}

    def fake_stream_command(cmd, *, cwd, log_path, max_runtime_seconds):
        del cmd, cwd, max_runtime_seconds
        attempts["count"] += 1
        log_path.write_text("docker build failed\n", encoding="utf-8")
        return 1, "docker build failed\n", False, False

    monkeypatch.setattr("experiments.oneshot.run_repo_task.stream_command", fake_stream_command)

    result = run_repo_task(
        "https://github.com/ablab/spades",
        workspace_root=workspace_root,
        output_root=output_root,
    )

    assert attempts["count"] == 1
    assert result["completed"] is False
    assert result["status"] == "finished"
    assert not (result["run_dir"] / "agent.retry1.log").exists()


def test_run_repo_task_records_missing_execution_capability_as_incomplete(
    tmp_path, monkeypatch
) -> None:
    workspace_root = tmp_path / "workspace"
    output_root = tmp_path / "output"
    repo_dir = workspace_root / "spades"
    repo_dir.mkdir(parents=True)

    monkeypatch.setattr(
        "experiments.oneshot.run_repo_task.ensure_repo",
        lambda repo_url, workspace_root, **kwargs: repo_dir,
    )
    monkeypatch.setattr(
        "experiments.oneshot.run_repo_task.stream_command",
        lambda cmd, *, cwd, log_path, max_runtime_seconds: (
            0,
            "I cannot execute shell commands in this environment.\n",
            False,
            False,
        ),
    )

    result = run_repo_task(
        "https://github.com/ablab/spades",
        workspace_root=workspace_root,
        output_root=output_root,
    )

    summary = json.loads(result["summary_path"].read_text(encoding="utf-8"))
    assert result["completed"] is False
    assert result["status"] == "finished"
    failed = set(summary["completion_judgment"]["failed_checks"])
    assert "docker_test_executed" in failed
    assert "miniwdl_ran" in failed
    assert "wdl_outputs_written" in failed


def test_run_repo_batch_respects_limit(tmp_path, monkeypatch) -> None:
    targets = tmp_path / "targets.txt"
    targets.write_text(
        "\n".join(
            [
                "https://github.com/ablab/spades",
                "https://github.com/marbl/canu",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    output_root = tmp_path / "output"
    workspace_root = tmp_path / "workspace"

    calls = []

    def fake_run_repo_task(repo_url, *, workspace_root, output_root, max_runtime_minutes):
        calls.append(repo_url)
        run_dir = output_root / repo_url.rsplit("/", 1)[-1] / "run"
        run_dir.mkdir(parents=True, exist_ok=True)
        summary_path = run_dir / "summary.json"
        manifest_path = run_dir / "manifest.json"
        summary_path.write_text("{}", encoding="utf-8")
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

    monkeypatch.setattr("experiments.oneshot.run_repo_batch.run_repo_task", fake_run_repo_task)

    result = run_repo_batch(
        targets_file=targets,
        workspace_root=workspace_root,
        output_root=output_root,
        limit=1,
        max_runtime_minutes=45,
    )

    assert len(calls) == 1
    assert result["summary"]["run_count"] == 1
    assert result["summary"]["max_runtime_minutes"] == 45
    assert (result["batch_dir"] / "batch_summary.json").exists()


def test_run_repo_task_records_setup_failed_status(tmp_path, monkeypatch) -> None:
    workspace_root = tmp_path / "workspace"
    output_root = tmp_path / "output"
    clone_log_path = output_root / "spades" / "run" / "clone.log"

    def fake_ensure_repo(repo_url, workspace_root, **kwargs):
        log_path = kwargs["clone_log_path"]
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text("git clone failed\n", encoding="utf-8")
        raise RepoPreparationError(
            "git clone failed after 3 attempts for https://github.com/ablab/spades",
            returncode=128,
            log_path=log_path,
        )

    monkeypatch.setattr("experiments.oneshot.run_repo_task.ensure_repo", fake_ensure_repo)

    result = run_repo_task(
        "https://github.com/ablab/spades",
        workspace_root=workspace_root,
        output_root=output_root,
    )

    manifest = json.loads(result["manifest_path"].read_text(encoding="utf-8"))
    summary = json.loads(result["summary_path"].read_text(encoding="utf-8"))
    assert result["completed"] is False
    assert result["status"] == "setup_failed"
    assert summary["status"] == "setup_failed"
    assert summary["returncode"] == 128
    assert "git clone failed after 3 attempts" in summary["error"]
    assert manifest["status"] == "setup_failed"
    assert result["summary_path"].parent.joinpath("agent.log").read_text(encoding="utf-8") == "git clone failed\n"


def test_run_repo_batch_records_batch_error_and_continues(tmp_path, monkeypatch) -> None:
    targets = tmp_path / "targets.txt"
    targets.write_text(
        "\n".join(
            [
                "https://github.com/ablab/spades",
                "https://github.com/marbl/canu",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    output_root = tmp_path / "output"
    workspace_root = tmp_path / "workspace"

    calls = []

    def fake_run_repo_task(repo_url, *, workspace_root, output_root, max_runtime_minutes):
        calls.append(repo_url)
        if repo_url.endswith("/spades"):
            raise RuntimeError("unexpected batch failure")
        run_dir = output_root / "canu" / "run"
        run_dir.mkdir(parents=True, exist_ok=True)
        summary_path = run_dir / "summary.json"
        manifest_path = run_dir / "manifest.json"
        summary_path.write_text("{}", encoding="utf-8")
        manifest_path.write_text("{}", encoding="utf-8")
        return {
            "repo_url": repo_url,
            "repo_name": "canu",
            "run_dir": run_dir,
            "returncode": 0,
            "completed": True,
            "status": "completed",
            "summary_path": summary_path,
            "manifest_path": manifest_path,
        }

    monkeypatch.setattr("experiments.oneshot.run_repo_batch.run_repo_task", fake_run_repo_task)

    result = run_repo_batch(
        targets_file=targets,
        workspace_root=workspace_root,
        output_root=output_root,
        continue_on_error=True,
    )

    assert calls == [
        "https://github.com/ablab/spades",
        "https://github.com/marbl/canu",
    ]
    assert result["summary"]["run_count"] == 2
    assert result["summary"]["results"][0]["status"] == "batch_error"
    assert result["summary"]["results"][1]["status"] == "completed"
    assert (result["batch_dir"] / "batch_summary.json").exists()
