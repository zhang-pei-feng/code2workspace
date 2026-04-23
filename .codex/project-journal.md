# Project Journal

- Project root: /mnt/data1/zhangpf/code2workspace
- Git repository: yes
- Started: 2026-04-20 21:00 CST

## Entries

### 2026-04-20 21:00 CST
- Session goal: Resume the existing `local-eight-repo-benchmark` run and convert the partially working benchmark skill into a stable local execution path.
- Major changes:
  - Recovered the active benchmark run under `results/skills/benchmark-workflow-orchestrator/local-eight-repo-benchmark` and confirmed `spades` is fully complete while `canu` and `megahit` are WDL-only successes.
  - Root-caused `megahit` repo-native failure to Docker `ENTRYPOINT ["megahit"]` swallowing `/bin/bash -lc ...`, and root-caused `canu` repo-native failure to a symlinked dataset file that becomes dangling inside the container mount.
  - Verified both cases empirically: `megahit` succeeds with `--entrypoint /bin/bash`, and `canu` succeeds when mounting the symlink target directory containing the real FASTQ.
- Validation: Reproduced both failures from current `run/status.json` commands and ran successful control commands in the local Docker images.
- Next step: Patch the benchmark execution layer to canonicalize input paths and support shell execution against ENTRYPOINT images, then re-run `canu` and `megahit` and continue the remaining five repos.

### 2026-04-20 21:24 CST
- Session goal: Clean up obvious top-level historical artifacts on request and review root Markdown files for retention value.
- Major changes:
  - Deleted the root-level historical workflow files `spades_Dockerfile`, `spades.wdl`, `inputs.json`, `conftest.py`, and `cromwell.local.conf`.
  - Left same-named files under `.workspaces/` and `results/` untouched because they are run artifacts rather than stray root files.
- Validation: Confirmed those five filenames no longer exist at repository root.
- Next step: If more cleanup is wanted, review large generated directories like `.workspaces/` and selected `results/` artifacts case by case instead of deleting by filename globally.

### 2026-04-20 21:43 CST
- Session goal: Consolidate scattered root-level documentation into a cleaner `docs/` structure and make current progress easier to scan.
- Major changes:
  - Moved the root-level operational docs into `docs/overview/` and `docs/research/`, and moved the old ACP skills migration plan into `docs/archive/`.
  - Rewrote the root `README.md` as a navigation entrypoint, updated `AGENTS.md` to the new doc paths, and added `docs/README.md` plus `docs/research/README.md` as stable indexes.
  - Compressed the engineering snapshot into `docs/overview/current-status.md` and fixed thesis-facing references in the main harness writing artifacts.
- Validation: Verified the root now contains only the minimal top-level files, and a stale-path search returned no remaining live references outside the implementation plan file.
- Next step: Keep future status updates in `docs/overview/current-status.md` and `docs/research/thesis-log.md` instead of recreating new root-level log files.

### 2026-04-20 21:52 CST
- Session goal: Clarify that the interactive terminal path is still unhealthy and sync the documentation reorganization into git cleanly.
- Major changes:
  - Updated the new root and overview docs to distinguish the working non-interactive CLI path from the still-broken interactive TUI path.
  - Added the TUI repair item to the main blockers, roadmap, handoff notes, and contributor guidance.
- Validation: Verified the updated docs mention the TUI limitation explicitly in the new entrypoint files.
- Next step: When returning to terminal UX work, treat TUI repair as a dedicated task instead of assuming parity with the non-interactive CLI flow.

### 2026-04-20 23:02 CST
- Session goal: Restore basic interactive TUI startup without broad terminal refactoring.
- Major changes:
  - Root-caused the stuck `Connecting to local server...` state to stale Textual message handler names left behind after the app class rename to `Code2WorkspaceApp`.
  - Updated the deferred startup handlers in `libs/cli/code2workspace_cli/app.py` to use the `on_code2workspace_app_server_ready` and `on_code2workspace_app_server_start_failed` names that Textual dispatch actually expects.
  - Added regression coverage in `libs/cli/tests/unit_tests/test_app.py` for both direct handler use and real `post_message(...)` dispatch of `ServerReady` / `ServerStartFailed`.
- Validation: `uv run --project libs/cli pytest libs/cli/tests/unit_tests/test_app.py -k 'server_ready_message_dispatch_clears_connecting or server_failure_message_dispatch_updates_error or initial_skill_runs_after_server_ready or deferred_actions_cleared_on_server_failure or server_failure_stores_error' -q` passed with `5 passed`; a real `uv run --project libs/cli code2workspace --no-mcp` session advanced from `Connecting to local server...` to `Ready to code! What would you like to build?`.
- Next step: Treat this as a startup hotfix only; if TUI still has deeper interaction issues, debug them separately from the deferred server-connect path.

### 2026-04-21 00:08 CST
- Session goal: Update the repository docs so they no longer describe the TUI startup path as broken, and package the hotfix as a clean commit.
- Major changes:
  - Updated the root and overview docs to reflect that interactive TUI startup now reaches the ready prompt again.
  - Removed the old roadmap / handoff wording that described TUI repair as still pending, while keeping the real CLI/TUI state-model split caveat.
  - Added the TUI startup hotfix to `docs/research/thesis-log.md` so the engineering and thesis timelines stay aligned.
- Validation: Reused the already-passing focused TUI regression tests and the prior manual startup check as the evidence baseline for the doc update.
- Next step: If further TUI issues appear, treat them as separate interaction bugs rather than reopening the already-fixed deferred startup message-routing issue.

### 2026-04-21 01:20 CST
- Session goal: Change normal CLI sessions to use per-session timestamped workspaces while preserving fixed-layout experiment runners.
- Major changes:
  - Added a session workspace policy layer in `libs/cli` so ordinary TUI, non-interactive CLI, and web-backed one-shot runs default to `<invocation-cwd>/workspace/<YYYYMMDDHHMMSS>`.
  - Propagated the effective session cwd through stream metadata, server startup, TUI adapter state, shell execution, chat-input file completion, and thread resume so resumed threads can return to the same workspace.
  - Explicitly opted the fixed-layout experiment entrypoints in `experiments/oneshot` and `experiments/skill_tests` back into inherited cwd mode so their existing artifact assumptions remain stable.
- Validation: Focused new-workspace tests passed; a real non-interactive run launched from a temporary directory created `workspace/<timestamp>` under that directory; related unit/integration test files passed with `406 passed` plus the targeted `test_main.py` cwd-forwarding checks.
- Next step: If later UX feedback shows that `@file` completion should prefer the isolated workspace instead of repo-root discovery when running under `workspace/<timestamp>`, adjust that behavior separately from the already-landed cwd routing.

### 2026-04-21 03:30 CST
- Session goal: Add a reproducible experiment batch for 12 COVID/flu/RSV natural-language questions and capture the actual `code2workspace` answers under `experiments/`.
- Major changes:
  - Extended `experiments/skill_tests` so cases can be grouped by a markdown batch file and written to an `experiments/skill_tests/runs/<batch>/<date>/` output root instead of only `results/...`.
  - Added 12 standalone question cases plus a dedicated `run_question_batch.py` entrypoint and a human-readable batch index under `experiments/skill_tests/batches/`.
  - Recorded real run artifacts for the `covid-monitoring-questions` batch under `experiments/skill_tests/runs/covid-monitoring-questions/20260421/` and the pinned snapshot under `experiments/skill_tests/snapshots/covid-monitoring-questions/20260421/`.
- Validation: The new `skill_tests` unit tests passed; a one-case smoke batch proved the new `experiments/...` output root; the full 12-question batch finished with 10 passed and 2 runner errors (one timeout, one non-zero exit due to server-side internal error).
- Next step: If this batch should become a long-term benchmark surface, add explicit expectation matchers for answer quality instead of relying mainly on runner success/failure and captured outputs.

### 2026-04-21 01:34 CST
- Session goal: Create the new benchmark area under `experiments/` and relocate the requested benchmark assets there.
- Major changes:
  - Created `experiments/benchmark/` as a new top-level experiment directory.
  - Moved `experiments/oneshot/datasets/` into `experiments/benchmark/datasets/`.
  - Moved `experiments/oneshot/新冠病毒组装/` into `experiments/benchmark/新冠病毒组装/`.
- Validation: Verified both moved directories exist under `experiments/benchmark/` and no longer exist under `experiments/oneshot/`; checked `git status --short` afterward.
- Next step: Update any scripts or docs only if they still assume these benchmark assets live under `experiments/oneshot/`.

### 2026-04-21 02:49 CST
- Session goal: Rewire the local benchmark helper to the new `experiments/benchmark/` layout and run the seven-case covid-assembly benchmark as far as possible.
- Major changes:
  - Updated the benchmark helper, catalog, and local benchmark inputs so the seven local cases under `experiments/benchmark/新冠病毒组装` are the active benchmark source instead of the removed `experiments/oneshot` paths.
  - Added focused benchmark-helper regression coverage for the new catalog root, explicit case mapping, local WDL/input resolution, and image-tag handling.
  - Started a real benchmark run under `results/skills/benchmark-workflow-orchestrator/20260421-covid-assembly-benchmark` and recorded real status artifacts for successful, failed, and blocked cases.
  - Captured partial positive evidence: WDL success for `spades`, `megahit`, and `trinityrnaseq`; repo-native success for `canu`, `megahit`, and `trinityrnaseq`; explicit blockers for `covid-19-signal` and `fieldbioinformatics`.
- Validation: Targeted benchmark-helper tests passed (`10 passed`); refreshed `summary.json` / `summary.md` for the active benchmark run; recorded concrete failure reasons for the blocked cases.
- Next step: Resume the still-running long cases (`Flye` repo-native and `canu` WDL when last checked), then rerun `summarize` so the benchmark table reflects their final state.

### 2026-04-21 09:12 CST
- Session goal: Prepare a clean benchmark-only copy so future `code2workspace` runs cannot read historical repository results by walking the original repo tree.
- Major changes:
  - Created an isolated directory at `/mnt/data1/zhangpf/code2workspace_benchmark_isolated/20260421-covid-benchmark`.
  - Copied only `experiments/benchmark/新冠病毒组装` and `experiments/benchmark/datasets` into that isolated root.
  - Removed the copied `workspace/` subdirectory so the isolated copy contains no prior benchmark reports or run artifacts.
- Validation: Verified the isolated root contains only the benchmark case folders, dataset catalog, and dataset files; confirmed there is no `results/`, `.workspaces/`, or `workspace/` directory inside it.
- Next step: Launch `code2workspace` from the isolated root rather than from the original repository benchmark directory when a truly fresh benchmark run is required.

### 2026-04-21 09:26 CST
- Session goal: Change the CLI so non-interactive `code2workspace -n ...` runs default to shell-enabled execution instead of requiring an explicit shell allow-list.
- Major changes:
  - Updated the non-interactive execution path to treat an unspecified shell allow-list as the equivalent of unrestricted shell access for that mode only.
  - Adjusted non-interactive decision logic and CLI help text to match the new default.
  - Added/updated unit-test expectations so the default non-interactive branch now verifies `enable_shell=True` and auto-approves shell commands by default.
- Validation: `uv run --project libs/cli pytest libs/cli/tests/unit_tests/test_non_interactive.py -q -k 'shell_without_allow_list_approved_by_default or shell_auto_approve_branches'` passed (`4 passed`); `uv run --project libs/cli pytest libs/cli/tests/unit_tests/test_main_args.py -q -k 'shell_allow_list_not_specified or combined_with_shell_allow_list'` passed (`2 passed`).
- Next step: Retry the isolated benchmark run through `code2workspace -n ...` without `-S all` and confirm the agent now receives the execute tool by default.

### 2026-04-21 02:44 CST
- Session goal: Replace the existing web frontend with an OpenHands-style operator shell and verify the web control plane still works end to end.
- Major changes:
  - Replaced the prior assistant-ui-based frontend with a new static React/Vite shell under `apps/webapp/frontend/` featuring a session rail, conversation surface, and inspector tabs for planner summary, run history, and terminal output.
  - Added frontend smoke coverage in `apps/webapp/frontend/src/App.test.tsx`, recorded OpenHands upstream provenance in `apps/webapp/frontend/UPSTREAM_OPENHANDS.md`, and removed the old unused web frontend components and assistant-ui dependencies.
  - Fixed a web-store concurrency issue in `apps/webapp/store.py` by enabling SQLite `WAL` mode and a busy timeout so quick one-shot runs can complete under the shell's 1.5-second polling cadence.
- Validation: `npm test` in `apps/webapp/frontend` passed (`4 passed`); `npm run build` passed; `PYTHONPATH=. uv run --project libs/cli pytest apps/webapp/tests -q` passed (`10 passed`); live `uvicorn` smoke verified `/`, `/api/health`, `POST /api/sessions`, and a real `Reply with OK only.` one-shot run completing to `OK` while polling.
- Next step: If the web control plane needs richer agent affordances next, wire Browser/App tabs to real runtime surfaces instead of placeholders while keeping the current REST contract stable.

### 2026-04-21 09:11 CST
- Session goal: Remove the checked-in web frontend entirely and leave `apps/webapp` as API-only backend code.
- Major changes:
  - Deleted `apps/webapp/frontend/` and `apps/webapp/static/`, and removed the SPA/static routes from `apps/webapp/api.py` so `/` and `/sessions/*` are no longer served.
  - Kept the API/store/runner pieces in `apps/webapp` and updated their docs/docstrings to reflect API-only status.
  - Updated root, handoff, roadmap, status, thesis, and contributor docs so they no longer describe an in-tree browser frontend.
- Validation: `test ! -d apps/webapp/frontend && test ! -d apps/webapp/static` passed; `PYTHONPATH=. uv run --project libs/cli pytest apps/webapp/tests -q` passed (`10 passed`); live `uvicorn` smoke verified `/` and `/sessions/test` return `404` while `/api/health` returns `{"ok": true}`.
- Next step: If a browser UI is ever reintroduced, treat it as a new deliberate project decision rather than assuming the old web frontend still exists.

### 2026-04-21 09:42 CST
- Session goal: Add a lightweight project skill that improves generic agent planning without hardcoded routing.
- Major changes:
  - Added `.code2workspace/skills/planning-guide/` with a concise `SKILL.md`, two reference files for source selection and reusable planning checklists, and OpenAI UI metadata.
  - Kept the new skill guidance-only so it complements `planning-orchestrator` instead of overlapping with dispatch or artifact generation behavior.
  - Added regression coverage in `libs/cli/tests/unit_tests/skills/test_superagent_project_assets.py` for project skill discovery, asset presence, guidance-only wording, and `SkillsMiddleware` metadata loading.
- Validation: `uv run --project libs/cli pytest libs/cli/tests/unit_tests/skills/test_superagent_project_assets.py -q` passed (`5 passed`).
- Next step: If the skill should influence default agent behavior more strongly, wire its heuristics into prompts or planner UI deliberately instead of turning it into another dispatcher.

### 2026-04-21 10:35 CST
- Session goal: Make initial agent plans visible to the user before execution continues.
- Major changes:
  - Changed CLI todo guidance in `libs/cli/code2workspace_cli/agent.py` so both interactive and non-interactive prompts now tell the agent to summarize the plan and continue instead of waiting for approval.
  - Added non-interactive plan echoing in `libs/cli/code2workspace_cli/non_interactive.py` so `write_todos` tool results are rendered as a compact `Plan:` summary even when the model does not narrate one explicitly.
  - Added focused regression coverage in `libs/cli/tests/unit_tests/test_agent.py` and `libs/cli/tests/unit_tests/test_non_interactive.py` for the new prompt wording and `write_todos` plan-preview rendering.
- Validation: Focused prompt and non-interactive tests passed; real non-interactive case logs showed mixed model behavior before the tool-level echo, with at least one run already emitting a natural-language plan summary immediately after `write_todos`.
- Next step: If plan visibility should also be guaranteed in the interactive TUI/web surfaces, apply the same compact todo-to-plan rendering there instead of relying only on model narration.

### 2026-04-21 11:05 CST
- Session goal: Unify the planning skills and remove keyword-based planning routing.
- Major changes:
  - Moved the reusable planning tool into `.code2workspace/skills/planning-guide/scripts/planning_tool.py` and changed it to emit a generic planning contract with fixed planning principles, generic source options, and helper discovery instead of keyword-derived domains or dispatch targets.
  - Removed `planning-orchestrator` from project skill discovery by deleting its `SKILL.md` and UI metadata, while keeping a compatibility wrapper script at the old path so existing callers still resolve.
  - Updated planning tests to assert generic `domain`, null `recommended_skill` / `dispatch_candidate`, `planning-guide/v2` contract output, and the absence of `planning-orchestrator` in discovered project skills.
- Validation: Focused planning and skill-discovery tests passed; manual `classify` runs for benchmark, workspace, and epidemic-report prompts all produced `domain: generic` and `dispatch_candidate: null`.
- Next step: If you want the planner to become smarter again later, build that on top of explicit helper selection or model reasoning, not on keyword tables or hidden auto-dispatch rules.

### 2026-04-21 12:20 CST
- Session goal: Expand `planning-guide` with reusable case references and remove Bio-OS-specific workflow guidance in favor of local-only execution.
- Major changes:
  - Added a planning-case index plus four short scenario references under `.code2workspace/skills/planning-guide/references/` covering local database lookup, official monitoring windows, latest literature search, and cross-source synthesis.
  - Updated `planning-guide` discovery tests so the new reference entrypoint is required and the case index stays linked from `SKILL.md`.
  - Removed the project `bioos-operator` subagent and shared `bioos_ops.py` helper, then rewrote the remaining benchmark/workspace guidance and OpenClaw bridge docs/prompts to stop assuming Bio-OS/Miracle or other remote workflow execution.
- Validation: `uv run --project libs/cli pytest libs/cli/tests/unit_tests/skills/test_superagent_project_assets.py -q` passed (`6 passed`); `uv run --project libs/cli pytest libs/cli/tests/unit_tests/test_superagent_project_subagents.py -q` passed (`1 passed`); `uv run --project libs/cli pytest experiments/skill_tests/tests/test_planning_tool.py -q` passed (`4 passed`); a repository-wide `rg -i "bio-os|bioos|miracle_access_key|miracle_secret_key"` over non-cache sources only matched the new cleanup assertions in tests.
- Next step: If local workflow support needs stronger helper behavior later, build that explicitly on local result directories and local runners rather than restoring remote workflow submission paths.

### 2026-04-21 12:34 CST
- Session goal: Remove the obsolete `planning-orchestrator` compatibility directory and keep all planning-tool references on the unified `planning-guide` path.
- Major changes:
  - Deleted `.code2workspace/skills/planning-orchestrator/` after confirming it only contained the old wrapper and cache files.
  - Updated the remaining direct test references in `experiments/skill_tests/tests/test_planning_tool.py` and `experiments/harness/tests/test_project_skill_helpers.py` to point at `.code2workspace/skills/planning-guide/scripts/planning_tool.py`.
  - Adjusted two stale harness assertions so they match the current OpenClaw bridge behavior instead of an older benchmark-routing assumption.
- Validation: `test ! -e .code2workspace/skills/planning-orchestrator` passed; `uv run --project libs/cli pytest experiments/skill_tests/tests/test_planning_tool.py -q` passed (`4 passed`); `uv run --project libs/cli pytest experiments/harness/tests/test_project_skill_helpers.py -q` passed (`13 passed`).
- Next step: If any non-test caller still expects the old path externally, update that caller to use `planning-guide` directly rather than restoring a compatibility wrapper.

### 2026-04-21 14:18 CST
- Session goal: Point the repo-tracked OpenAI gateway config at the remote host `8.221.123.105` and remove `/v1`, then verify CLI behavior.
- Major changes:
  - Changed `.code2workspace/config.toml` so `[models.providers.openai].base_url` now points at `http://8.221.123.105:8080`.
  - Updated `docs/overview/current-status.md` to describe the new configured gateway baseline.
  - Added a thesis-log note in `docs/research/thesis-log.md` recording the switch away from the old loopback `/v1` URL.
- Validation: Static checks confirmed the config now uses `http://8.221.123.105:8080`; `uv run --project libs/cli code2workspace --no-mcp` still reached `Ready to code!`; `uv run --project libs/cli code2workspace -n "Reply with OK only." -q --no-mcp` timed out at 90s with no output; direct HTTP probes showed `http://8.221.123.105:8080/` serves HTML while `http://8.221.123.105:8080/v1/models` returns `401 INVALID_API_KEY`.
- Next step: Decide whether the remote gateway should keep the requested root-path config or switch back to `/v1` with a valid remote API key so non-interactive model calls can work again.

### 2026-04-21 14:21 CST
- Session goal: Replace the repo-tracked OpenAI API key with the user-provided remote gateway credential.
- Major changes:
  - Updated `.env` so `OPENAI_API_KEY` now uses `123456789123456789`.
- Validation: `.env` now contains the new key; direct authenticated probe to `http://8.221.123.105:8080/v1/models` returned `200`, while `http://8.221.123.105:8080/` and `/models` still returned the HTML gateway page rather than an API response.
- Next step: If CLI calls should succeed end to end against this gateway, restore `/v1` in `base_url` or use another endpoint shape that matches the gateway's OpenAI-compatible API surface.

### 2026-04-21 14:41 CST
- Session goal: Make the real CLI runtime use the remote gateway successfully after the repo-local config change did not fix execution.
- Major changes:
  - Confirmed by code inspection that runtime `ModelConfig.load()` defaults to `~/.code2workspace/config.toml`, so the repo-tracked `.code2workspace/config.toml` is not the effective CLI model config.
  - Updated `~/.code2workspace/config.toml` so the OpenAI provider now uses `http://8.221.123.105:8080/v1`.
  - Kept the repo-tracked `.code2workspace/config.toml`, `docs/overview/current-status.md`, and `docs/research/thesis-log.md` aligned with the validated `/v1` endpoint shape.
- Validation: direct `uv run python` probe to `http://8.221.123.105:8080/v1/chat/completions` with model `gpt-5.4` returned `200` and `OK`; `uv run --project libs/cli code2workspace -n "Reply with OK only." -q --no-mcp` returned `OK`; `uv run --project libs/cli code2workspace --no-mcp` again reached `Ready to code! What would you like to build?`.
- Next step: If this repo is meant to be self-contained for other machines, decide whether CLI runtime should be taught to read the repo-tracked `.code2workspace/config.toml` instead of relying on the user-level config file.

### 2026-04-21 15:24 CST
- Session goal: Add soft planner-driven skill routing so benchmark and paper2workspace tasks surface the right orchestrator skills without forcing hard dispatch.
- Major changes:
  - Updated the `planning-guide` planning contract so it now emits task type, recommended skill, selected skill, fresh-run/isolation hints, and mixed-task lanes for obvious benchmark and paper2workspace prompts.
  - Added a `PlannerRoutingMiddleware` to the shared CLI agent path so skills-enabled sessions prepend planner recommendations and report-first guidance into the system prompt.
  - Added support for isolated copies to recover the original project `.code2workspace/skills/` and `.code2workspace/agents/` through a `.code2workspace/project-root.txt` marker instead of copying historical results.
  - Updated planning and orchestrator skill docs/tests to match the new soft-routing and report-first behavior.
- Validation: Focused planning, planner middleware, agent wiring, and skill asset tests passed.
- Next step: Create or update the isolated benchmark copy marker file, then verify a fresh `code2workspace` benchmark run actually sees the orchestrator skills without reading historical outputs.

### 2026-04-21 18:15 CST
- Session goal: Reduce the large mixed worktree into coherent commits that can be reviewed and reverted independently.
- Major changes:
  - Split the recent planning/routing work into a dedicated commit: `e89e9d9 feat: add soft planner routing for project skills`.
  - Split the local benchmark assets/helper rewrite into `b486e23 feat: add local benchmark assets and helper`.
  - Split the workflow-skill localization and report-composer cleanup into `107a10b refactor: localize workflow skills and reports`.
  - Split the web backend-only reduction into `badc272 refactor: reduce webapp to api backend`.

### 2026-04-22 00:40 CST
- Session goal: Add a harness-native phase-1 benchmark-autonomy ladder for the local benchmark assets under `experiments/benchmark`.
- Major changes:
  - Added `experiments/harness/code2workspace_harness/benchmark_autonomy.py` plus `experiments/harness/configs/benchmark_autonomy_phase1.toml` to model two phase-1 families (`short-read-assembly`, `long-read-assembly`) across four autonomy levels.
  - Implemented isolated run staging that copies only the required benchmark WDL/input assets and staged dataset files into a fresh workspace-local `experiments/benchmark` tree, while preserving original project skill visibility through `.code2workspace/project-root.txt`.
  - Added report-first prompt generation and fallback run summaries so each benchmark-autonomy run leaves `summary.json` / `summary.md` with selected tools, selected inputs, WDL-change state, cost counters, and normalized failure taxonomy even when the agent only writes a partial report.
  - Extended the harness runner with `validate-benchmark-autonomy` and `run-benchmark-autonomy`, and documented the new commands in `experiments/harness/README.md`.
- Validation: `PYTHONPATH=. uv run --project libs/cli pytest experiments/harness/tests -q` passed (`29 passed`); `PYTHONPATH=. uv run --project libs/cli python experiments/harness/code2workspace_harness/runner.py validate-benchmark-autonomy experiments/harness/configs/benchmark_autonomy_phase1.toml` returned the expected two-family/four-level contract.
- Next step: Run real phase-1 family/level combinations to collect completion/time/cost evidence and see where the agent first fails when tool choice, input choice, and WDL editing are gradually unlocked.

### 2026-04-22 13:15 CST
- Session goal: Stop the autonomy-ladder expansion, record the results reached so far, and switch the harness back to the thesis-critical eight-repository real-task surface.
- Major changes:
  - Stopped the remaining benchmark-autonomy runs after collecting enough evidence to characterize the short-read levels and the first two long-read levels.
  - Recorded the autonomy-ladder pattern reached so far: short-read levels 1-4 all succeeded without any staged WDL edits; long-read levels 1-2 both showed `canu` success while `Flye` failed consistently because the staged Flye image is broken.
  - Extended the harness config loader so it can materialize cases directly from `experiments/harness/configs/repo_splits.toml` with simple per-repo runtime overrides.
  - Added `experiments/harness/configs/benchmark_repo_harness.toml` as the first simple eight-repository real-task harness config, reusing the existing one-shot prompt/completion surfaces and the 5-train / 3-holdout split.
- Validation: Focused config-loader tests passed; the new benchmark repo config loads 8 real repo cases with the expected train/holdout composition and runtime overrides.
- Next step: Run the new `benchmark_repo_harness.toml` baseline on the train split, then start the simplest keep/discard loop on that real-task surface instead of continuing the autonomy ladder.

### 2026-04-22 18:45 CST
- Session goal: Run the first real train baseline for the eight-repository harness and make the measurement path trustworthy enough for later optimization.
- Major changes:
  - Fixed one-shot workspace freshness by clearing prior generated Docker/WDL/Cromwell artifacts before each run and quarantining permission-blocked stale directories as `*.stale.<timestamp>` instead of aborting on old root-owned files.
  - Tightened the completion judge so real successful runs like `Flye` are no longer missed when the agent writes `results/docker_test/docker_run.log` and only the copied WDL under `results/wdl_file/`.
  - Ran the real train baseline under `results/harness/benchmark_repo_harness/benchmark-repo-harness/20260422T090923Z` and collected the first full five-repo result set.
- Validation: `experiments/oneshot/tests/test_tasks.py` passed (`14 passed`); `experiments/harness/tests/test_code2workspace_harness.py` passed (`11 passed`); the persisted train split recorded `1/5` completed, and after the judge fix the existing `Flye` artifacts recompute as a second true completion.
- Next step: Rerun the train split cleanly with the updated judge, then run the first holdout baseline so the harness has a trustworthy real-task baseline before any proposer loop.

### 2026-04-22 19:14 CST
- Session goal: Finish the clean real-task baseline cycle by rerunning train and then collecting the first holdout baseline on the same harness surface.
- Major changes:
  - Completed the clean train rerun under `results/harness/benchmark_repo_harness/benchmark-repo-harness/20260422T105103Z`, which now records `3/5` passes: `spades`, `megahit`, and `trinityrnaseq`.
  - Completed the first holdout baseline under `results/harness/benchmark_repo_harness/benchmark-repo-harness/20260422T105606Z`, which records `2/3` passes: `covid-19-signal` and `fieldbioinformatics`.
  - Established the first full simple real-task harness baseline across all eight repos: `5/8` combined, leaving `canu`, `Flye`, and `v-pipe` as the first concrete optimization targets.
- Validation: The new persisted split results are `train 3/5` and `holdout 2/3`; `experiments/oneshot/tests/test_tasks.py` still passes (`14 passed`) and `experiments/harness/tests/test_code2workspace_harness.py` still passes (`11 passed`).
- Next step: Start the first small optimization loop on the explicit miss set (`canu`, `Flye`, `v-pipe`) instead of collecting more baseline-only runs.
  - Split the repo layout/documentation cleanup into `0796d94 docs: sync repo layout and roadmap`.
  - Split the repo-tracked gateway baseline into `1b5c9e4 chore: point repo config at remote gateway`.

### 2026-04-22 23:46 CST
- Session goal: Tighten the live one-shot prompt surface against the known `canu` / `Flye` / `v-pipe` miss pattern and verify it on a fresh train rerun.
- Major changes:
  - Updated `experiments/harness/surfaces/one_shot_prompt.txt` so the “do not treat old artifacts as completion evidence” instruction matches the new regression test exactly.
  - Added a focused prompt-surface regression and confirmed the refreshed prompt now explicitly pushes the agent from discovery into the first real `docker build`.
  - Started a fresh train baseline under `results/harness/benchmark_repo_harness/benchmark-repo-harness/20260422T153031Z`; early live evidence from `spades` shows the agent now reaches `write_file` plus real `docker build` instead of staying in open-ended repository reading.
- Validation: `experiments/oneshot/tests/test_tasks.py` passed (`15 passed`); `experiments/harness/tests/test_code2workspace_harness.py` passed (`11 passed`); current live artifacts include `.workspaces/oneshot/spades/spades_Dockerfile` and `.workspaces/oneshot/spades/results/docker_test/docker_build.log`.
- Next step: Let the new train rerun finish, then compare whether the miss set improved from “stopped before fresh artifacts” to real build/run attempts or full completions.
  - Split the capability snapshot test/report additions into `012df4c feat: add capability snapshot skill tests`.
- Validation: Ran the focused test commands for the soft-routing, benchmark-helper, webapp backend, workflow-skill, and capability-snapshot groups before committing each batch.
- Next step: Only `.codex/` and `docs/superpowers/plans/` remain untracked locally; keep them uncommitted unless there is a deliberate reason to publish local planning/journal artifacts.

### 2026-04-23 04:19 CST
- Session goal: Convert the remaining train misses from a prompt-only problem into a runner-level stability fix after the latest rerun exposed transient remote internal errors.
- Major changes:
  - Confirmed the latest train rerun stayed at `3/5`, but the failure shape changed materially: `canu` and `megahit` now failed with early `RemoteProtocolError` / `RemoteException` internal errors rather than ordinary repo-task execution failures, while `Flye` flipped to a full pass.
  - Added one-shot retry handling in `experiments/oneshot/run_repo_task.py` that retries exactly once on a narrow transient-remote-error signature, preserves the first failed attempt as `agent.retry1.log`, clears partial generated artifacts, and keeps the same overall runtime budget.
  - Added focused regression coverage proving that transient remote/internal failures are retried once while ordinary non-zero repo failures are not retried.
  - Started independent live reproductions for `megahit` and `canu`; both current runs progressed into real build/download stages, which strengthens the hypothesis that the earlier baseline misses were at least partly transient runtime instability rather than irreducible repo failures.
- Validation: `experiments/oneshot/tests/test_tasks.py` passed (`17 passed`); `experiments/harness/tests/test_code2workspace_harness.py` passed (`11 passed`); live repro artifacts now include fresh `.workspaces/oneshot/megahit/results/docker_test/docker_build.log` and `.workspaces/oneshot/canu/results/docker_test/{download.log,docker_build.log}`.
- Next step: Finish monitoring the live repros, then launch a fresh train baseline with the retry-enabled runner and compare it against `20260422T153031Z`.

### 2026-04-23 11:11 CST
- Session goal: Convert the runner/judge fixes into a cleaner harness baseline and then push the same fixes onto the holdout split.
- Major changes:
  - Completed the next train rerun under `results/harness/benchmark_repo_harness/benchmark-repo-harness/20260422T203210Z`; the persisted result improved from `3/5` to `4/5` by flipping `canu` and `megahit` into full passes.
  - Found a further completion-judge false negative on `trinityrnaseq`: its real run produced `cromwell_run_retry2.log` plus `metadata_retry2.json`, but the old judge only recognized fixed retry filenames; generalized Cromwell success detection to fresh `cromwell_run*.log` and `metadata*.json`, and the same run now recomputes as a full pass under the fixed judge.
  - The train split is therefore effectively `5/5` under current code semantics: `spades`, `canu`, `megahit`, `Flye`, and `trinityrnaseq` all have real Docker + WDL success evidence.
  - Started the next holdout rerun under `results/harness/benchmark_repo_harness/benchmark-repo-harness/20260423T023441Z`; `v-pipe` has already flipped into a real full pass in that run, and the session is continuing with the remaining holdout cases.
- Validation: `experiments/oneshot/tests/test_tasks.py` passed (`19 passed`); `experiments/harness/tests/test_code2workspace_harness.py` passed (`11 passed`); rejudging the persisted `trinityrnaseq` train artifacts with the updated completion logic now returns `completed=True` and no failed checks.
- Next step: Let the holdout rerun finish, then record the updated train/holdout totals and reassess whether any remaining miss is a true repo limitation or another measurement/runtime issue.

### 2026-04-23 11:11 CST
- Session goal: Finish reading out the holdout rerun and reduce the repo-wide harness picture to the smallest remaining miss set.
- Major changes:
  - The holdout rerun under `results/harness/benchmark_repo_harness/benchmark-repo-harness/20260423T023441Z` has settled at `2/3`, with `v-pipe` and `covid-19-signal` completed and `fieldbioinformatics` still failing.
  - `v-pipe` is now a full real Docker + WDL pass in the holdout split, which confirms the recent runner/judge fixes generalize beyond the train repositories.
  - `fieldbioinformatics` remains the only clear repo-level miss in the eight-repository surface; the latest holdout evidence shows it still stops before producing fresh Docker/WDL artifacts.
- Validation: Confirmed `result.json` for the holdout rerun (`2/3`); confirmed `v-pipe` summary is `completed=true`; inspected `fieldbioinformatics` summary and agent log, which still show no fresh Docker/WDL artifacts.
- Next step: Focus the next optimization loop narrowly on `fieldbioinformatics`, using the current `7/8` effective baseline as the new reference point.

### 2026-04-23 15:20 CST
- Session goal: Reduce the last clear miss (`fieldbioinformatics`) from a vague holdout failure into a concrete runner/image integration bug, while integrating the parallel complex-QA work back into `main`.
- Major changes:
  - Merged `feature/complex-qa-benchmark` into `main` and carried over the worktree-only follow-up changes for the complex-QA harness, judge, and runner.
  - Replaced the earlier one-shot single retry with two transient remote/internal retries after isolated `fieldbioinformatics` repros showed the repository could progress materially further on the third attempt.
  - Confirmed the integrated regression set passes after the merge (`142 passed` across the targeted oneshot/harness/skill-tests/CLI suites).
  - Drove `fieldbioinformatics` far enough in isolated repro to identify the current repo-level blocker precisely: Cromwell launches the image under `/bin/bash`, bypassing environment activation so `artic` is not on `PATH`, even though Docker build and the shortest real container validation both succeed.
- Validation: targeted integrated regression suite passed (`142 passed`); isolated `fieldbioinformatics` repro now reaches real Docker build, real `artic guppyplex`, and real Cromwell execution before failing with `artic: command not found` inside the Cromwell task shell.
- Next step: push the integrated `main` branch, then resume from the narrower `fieldbioinformatics` PATH/Cromwell-shell issue instead of broad harness work.

### 2026-04-23 11:33 CST
- Session goal: Consolidate report generation into one generic multi-source report skill and remove the earlier overlapping report surfaces.
- Major changes:
  - Replaced `.code2workspace/skills/deep-research-report` and `.code2workspace/skills/epidemic-warning-report` with one new `.code2workspace/skills/multi-source-report` entrypoint plus a unified `report_tool.py`.
  - Replaced the old report-specific project subagents with `report-researcher`, `report-synthesizer`, and `report-web-researcher`, and updated planner routing plus nested-scope handling to target `multi-source-report`.
  - Reworked report-related unit tests and live skill-test cases so the new report surface is covered by discovery, routing, helper-tool, harness-helper, and live artifact checks.
- Validation: Focused pytest suite passed with `91 passed`; live skill-test runs passed for `multi-source-report` behavior, structure, and end-to-end artifact cases under `results/skill-tests/20260423-msr-{behavior,structure,e2e}/`.
- Next step: If report UX quality matters beyond artifacts, run a dedicated non-interactive prompt evaluation to confirm the final chat reply reliably returns full report bodies instead of only paths.

### 2026-04-23 13:29 CST
- Session goal: Make `multi-source-report` behave more like a formal report writer by default, with long-form output and source-backed tables when reliable numeric evidence exists.
- Major changes:
  - Added table-candidate parsing to the shared report composer path and taught `multi-source-report` to render a `Key Data Tables` section from valid numeric lane rows.
  - Added manifest defaults for long-form/table-preferred formal reports (`min_report_chars=5000`, `prefer_tables=true`, `max_tables=3`) and updated the report-agent instructions to emit `Table Candidate:` blocks when lanes contain stable numeric evidence.
  - Restored missing `experiments/skill_tests/runner.py` metadata and `trace.json` output expected by the current skill-test suite while working in the same area.
- Validation: `experiments/skill_tests/tests/test_multi_source_report_tool.py` passed (`7 passed`); a broader related regression set across `runner`, `parsers`, `harness`, report skill discovery, and nested-scope handling passed (`45 passed`).
- Next step: If you want richer presentation later, the next logical step is optional chart generation built on top of the new table-candidate / diagnostics contract rather than a free-form figure generator.

### 2026-04-21 16:12 CST
- Session goal: Reduce root-directory clutter and document a stable repository layout policy.
- Major changes:
  - Deleted the low-value root artifact directories `cromwell-workflow-logs/`, `.pytest_cache/`, and `.benchmarks/`.
  - Added root ignore rules for `/.benchmarks/`, `/cromwell-workflow-logs/`, and `/workspace/` so regenerated local byproducts stay out of git status noise.
  - Added `docs/overview/repo-layout.md` and linked it from `README.md` to define which root directories are stable source roots, retained generated roots, compatibility paths, and disposable caches.
  - Kept existing retained artifact directory names such as `results/`, `.workspaces/`, `workspace/`, and `tmp/` unchanged to preserve current conventions.
- Validation: Confirmed the three requested root artifact directories were absent after cleanup; skipped further runtime verification in favor of repository-organization work.
- Next step: If additional cleanup is wanted, focus next on whether root-level disposable directories like `__pycache__/` should be pruned periodically rather than on renaming established artifact roots.

### 2026-04-21 16:56 CST
- Session goal: Tweak planning-guide source-priority ordering so code/repo inspection is no longer presented first.
- Major changes:
  - Reordered `.code2workspace/skills/planning-guide/references/source-selection.md` so data/integration and monitoring/research/report sources now appear before the code-and-repository section.
- Validation: Read the updated file back and confirmed the new section order.
- Next step: If source priority should become task-dependent rather than static ordering, revise the reference to explain precedence by task type instead of relying on section order alone.
