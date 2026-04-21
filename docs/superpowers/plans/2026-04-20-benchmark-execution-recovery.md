# Benchmark Execution Recovery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stabilize the local benchmark execution layer so `canu` and `megahit` repo-native runs succeed inside the existing `local-eight-repo-benchmark` run, then use that fixed path to continue the remaining repository cases.

**Architecture:** Keep the current benchmark run structure and case manifests intact. Fix the execution boundary where container commands are assembled and launched so mounted inputs resolve to real files and shell-wrapped commands work for images that define an entrypoint. Then refresh the affected case outputs and continue the remaining repos using the same run root.

**Tech Stack:** Python 3, Docker CLI, Cromwell/WDL artifacts already on disk, pytest

---

### Task 1: Harden repo-native container execution

**Files:**
- Modify: `.code2workspace/skills/benchmark-workflow-orchestrator/scripts/benchmark_workflow.py`
- Test: `experiments/harness/tests/test_project_skill_helpers.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_repo_native_mounts_real_input_for_symlinked_dataset(tmp_path: Path) -> None:
    ...


def test_repo_native_shell_command_overrides_image_entrypoint(tmp_path: Path) -> None:
    ...
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest experiments/harness/tests/test_project_skill_helpers.py -k "repo_native_mounts_real_input_for_symlinked_dataset or repo_native_shell_command_overrides_image_entrypoint" -v`
Expected: FAIL because the current benchmark helper does not yet expose the execution helper behavior.

- [ ] **Step 3: Implement minimal execution-layer fix**

```python
def _canonical_input_mounts(input_files: dict[str, str]) -> tuple[list[str], dict[str, str]]:
    ...


def _docker_shell_command(image: str, shell_command: str, mount_args: list[str], *, force_shell_entrypoint: bool) -> list[str]:
    ...
```

- [ ] **Step 4: Run targeted tests to verify they pass**

Run: `pytest experiments/harness/tests/test_project_skill_helpers.py -k "repo_native_mounts_real_input_for_symlinked_dataset or repo_native_shell_command_overrides_image_entrypoint" -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add .code2workspace/skills/benchmark-workflow-orchestrator/scripts/benchmark_workflow.py experiments/harness/tests/test_project_skill_helpers.py
git commit -m "fix: harden benchmark repo-native container execution"
```

### Task 2: Refresh the two partially successful cases in the existing benchmark run

**Files:**
- Modify: `results/skills/benchmark-workflow-orchestrator/local-eight-repo-benchmark/cases/canu/run/status.json`
- Modify: `results/skills/benchmark-workflow-orchestrator/local-eight-repo-benchmark/cases/megahit/run/status.json`
- Modify: `results/skills/benchmark-workflow-orchestrator/local-eight-repo-benchmark/cases/canu/analysis.json`
- Modify: `results/skills/benchmark-workflow-orchestrator/local-eight-repo-benchmark/cases/megahit/analysis.json`
- Modify: `results/skills/benchmark-workflow-orchestrator/local-eight-repo-benchmark/summary.json`

- [ ] **Step 1: Re-run `canu` repo-native with the fixed execution path**

```bash
python3 .code2workspace/skills/benchmark-workflow-orchestrator/scripts/benchmark_workflow.py ...
```

- [ ] **Step 2: Re-run `megahit` repo-native with the fixed execution path**

```bash
python3 .code2workspace/skills/benchmark-workflow-orchestrator/scripts/benchmark_workflow.py ...
```

- [ ] **Step 3: Refresh per-case analysis and run summary**

```bash
python3 .code2workspace/skills/benchmark-workflow-orchestrator/scripts/benchmark_workflow.py analyze-case --repo canu --run-dir results/skills/benchmark-workflow-orchestrator/local-eight-repo-benchmark
python3 .code2workspace/skills/benchmark-workflow-orchestrator/scripts/benchmark_workflow.py analyze-case --repo megahit --run-dir results/skills/benchmark-workflow-orchestrator/local-eight-repo-benchmark
python3 .code2workspace/skills/benchmark-workflow-orchestrator/scripts/benchmark_workflow.py summarize --run-dir results/skills/benchmark-workflow-orchestrator/local-eight-repo-benchmark
```

- [ ] **Step 4: Verify updated artifacts**

Run: `python3 - <<'PY' ... PY`
Expected: both repos report `run.success == True`, `wdl.success == True`, and non-empty artifact paths in their summaries.

- [ ] **Step 5: Commit**

```bash
git add results/skills/benchmark-workflow-orchestrator/local-eight-repo-benchmark
git commit -m "chore: refresh canu and megahit benchmark artifacts"
```

### Task 3: Prepare the remaining five repos and traceback capture path

**Files:**
- Modify: `results/skills/benchmark-workflow-orchestrator/local-eight-repo-benchmark/cases/Flye/*`
- Modify: `results/skills/benchmark-workflow-orchestrator/local-eight-repo-benchmark/cases/trinityrnaseq/*`
- Modify: `results/skills/benchmark-workflow-orchestrator/local-eight-repo-benchmark/cases/v-pipe/*`
- Modify: `results/skills/benchmark-workflow-orchestrator/local-eight-repo-benchmark/cases/covid-19-signal/*`
- Modify: `results/skills/benchmark-workflow-orchestrator/local-eight-repo-benchmark/cases/fieldbioinformatics/*`

- [ ] **Step 1: Inspect each case manifest, Docker image, local result candidates, and reusable artifacts**

```bash
python3 - <<'PY'
...
PY
```

- [ ] **Step 2: Record the shortest honest repo-native and WDL next action per repo**

```json
{
  "repo": "Flye",
  "next_repo_native_action": "...",
  "next_wdl_action": "...",
  "reusable_artifacts": ["..."]
}
```

- [ ] **Step 3: Identify where to capture server traceback if `InternalServerError` recurs**

```bash
rg -n "InternalServerError|traceback|exception" libs experiments
```

- [ ] **Step 4: Save the findings for controller integration**

```text
Return a concise summary with file paths, commands, and blockers only.
```

- [ ] **Step 5: Commit**

```bash
git add results/skills/benchmark-workflow-orchestrator/local-eight-repo-benchmark
git commit -m "docs: capture next benchmark actions for remaining repos"
```
