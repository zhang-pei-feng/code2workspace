# Project Journal

- Project root: /mnt/data1/zhangpf/code2workspace
- Git repository: yes
- Started: 2026-04-20 21:00 CST

## Entries

### 2026-05-12 08:32 CST
- Session goal: Configure the supervisor-runtime worktree to use ClawdRouter Claude by default.
- Major changes:
  - Updated this worktree's ignored `.env` Anthropic/ClawdRouter variables to use the ClawdRouter endpoint and key.
  - Updated the branch-local model config at `backend/config/agent_models.json` so `default` and `recent` are `anthropic:claude-sonnet-4-6`.
- Validation:
  - Direct `create_model()` resolved `backend/config/agent_models.json`, created `langchain_anthropic.ChatAnthropic`, and returned `OK`.
  - `uv run --project libs/cli code2workspace --default-model` reports `anthropic:claude-sonnet-4-6`.
  - `uv run --project libs/cli code2workspace -n "Reply with OK only." -q --no-mcp` completed through the supervisor generic path and returned `OK only.`
- Next step: If this branch should preserve the model config in Git, add `backend/config/agent_models.json`; `.env` remains intentionally ignored.

### 2026-05-11 19:15 CST
- Session goal: Make supervisor runtime return natural user-facing answers instead of the structured Supervisor Summary in chat.
- Major changes:
  - Added `user_response` to the supervisor run result and write it to `final_response.md`, while preserving the full diagnostic `final_summary.md` artifact.
  - Changed the supervisor wrapper to return `user_response` as the chat `AIMessage`, using deterministic extraction from completed delivery nodes such as `final_summarize` / `compose_generic` instead of a second LLM call.
  - Added worker prompt guidance so final delivery nodes put the actual user-facing answer in `summary` and keep process details in evidence/hints.
- Validation: `test_supervisor_runtime.py` passed (`26 passed`); live `code2workspace -n "你好" -q` returned only the natural greeting while the full Supervisor Summary remained in the run artifact.
- Next step: consider extending the final-response selector with task-family-specific formatting for benchmark/report outputs if those should also hide operational details by default.

### 2026-05-11 19:07 CST
- Session goal: Fix Paseo not listing `gpt-5.5` for the Codex provider.
- Major changes:
  - Upgraded the user-level global `@openai/codex` npm package from `0.124.0` to `0.130.0`.
  - Restarted the local Paseo daemon so it launched the updated Codex app server.
- Validation: `paseo daemon status --json` reports Codex `codex-cli 0.130.0`; `paseo provider models codex --json` now lists `gpt-5.5`.
- Next step: use `codex/gpt-5.5` from Paseo normally; no repository code changes were needed.
### 2026-05-11 19:05 CST
- Session goal: Diagnose why a successful TUI startup failed on the simple prompt `你好`.
- Major changes:
  - Traced the supervisor failure to model invocation, not graph scheduling: the run artifact showed `ValueError: No generations found in stream` before node outputs were written.
  - Reproduced a direct model call failure with `.env` `OPENAI_BASE_URL=http://8.221.123.105:8080/`; the OpenAI-compatible client received an invalid string response.
  - Fixed local `.env` to use the working OpenAI-compatible endpoint `http://8.221.123.105:8080/v1`.
- Validation: direct `create_model('openai:gpt-5.4').ainvoke('你好')` returned a normal Chinese greeting; `code2workspace -n "你好" -q` completed all supervisor nodes.
- Next step: consider making model config validation warn when an OpenAI-compatible base URL lacks `/v1`.

### 2026-05-11 18:59 CST
- Session goal: Diagnose and fix local CLI/TUI startup failure in the supervisor-runtime worktree.
- Major changes:
  - Identified `.env` `LANGSMITH_TRACING=` as the trigger for LangGraph API startup failure because Starlette cannot cast an empty string to bool.
  - Updated `libs/cli/code2workspace_cli/server.py` so the LangGraph server subprocess drops empty LangSmith tracing bool flags while preserving explicit `true` / `false` values.
  - Added focused tests in `libs/cli/tests/unit_tests/test_server_helpers.py`.
- Validation: `test_server_helpers.py` passed (`13 passed`); non-interactive startup no longer crashes the server; interactive TUI reached `Ready to code!`.
- Next step: investigate the separate generic worker failure seen after non-interactive startup if exact prompt execution quality matters.


### 2026-05-11 14:27 CST
- Session goal: Remove the retired `multi-source-report` surface and keep the active supervisor report path only.
- Major changes:
  - Deleted the project `multi-source-report` skill files plus its dedicated skill-test cases and tool tests.
  - Updated harness/test/catalog references to stop recommending or loading `multi-source-report`, replacing those hints with still-live evidence skills.
  - Switched the nested report subagent scope guard default from `multi-source-report` to the neutral `report`, and rewrote current-status notes to describe the active supervisor report runtime instead of the old skill entrypoint.
- Validation: focused cleanup regression set passed (`35 passed`) across nested report delegation, project-skill discovery, skill-test runner/judge coverage, and the affected harness tests. One broader harness config test still fails because the current worktree is already missing `experiments/harness/surfaces/one_shot_prompt.txt`, which predates this cleanup.
- Next step: commit the cleanup checkpoint, then continue tuning generic/report runtime behavior without carrying the old report skill surface.

### 2026-05-11 14:01 CST
- Session goal: Increase the length of generated report outputs and make report composition favor fuller final bodies.
- Major changes:
  - Strengthened the supervisor report composition objective in `libs/code2workspace/code2workspace/orchestration_runtime.py` so `compose_report` explicitly prefers a full-length report over a short brief.
  - Expanded report guidance in `.code2workspace/skills/supervisor-guidance/references/nodes/compose_report.md` and `references/families/report_synthesis.md` to push for more substantial section bodies with evidence, interpretation, and caveats.
  - Raised the default `multi-source-report` minimum report length from `5000` to `7000` characters in `.code2workspace/skills/multi-source-report/scripts/report_tool.py`.
- Validation: `py_compile` passed; focused report/runtime tests passed (`47 passed`); a fresh default `report_tool.py init` run now writes `manifest.json` with `min_report_chars = 7000`.
- Next step: run one live report case or bounded replay to see whether the longer-body preference materially changes the final report size and completion latency.

### 2026-05-11 11:03 CST
- Session goal: Make generic Supervisor Graph planning less rigid and adapt graph shape to the user's question.
- Major changes:
  - Reworked generic planning into a prompt-driven two-round flow: first `init_generic` asks the worker to design a flexible `spawned_subgraph`, then the runtime validates and executes that graph.
  - Kept task examples in the planner prompt rather than hardcoding generic task profiles in Python; research/evidence-judgment questions are called out as the main scenario and may choose sequential or parallel evidence lanes based on complexity.
  - Added graph sanitization so generated nodes/edges use known capability bundles and terminal nodes are connected to `summarize`.
- Validation: `py_compile` passed for orchestration/supervisor runtime; focused supervisor/orchestration tests passed (`40 passed`); a live CSV-log prompt produced a planner-generated second-round graph with parallel trend/attribution branches before the 180-second smoke timed out.
- Next step: tune worker execution latency and rerun the live generic prompt to completion.

### 2026-05-11 10:15 CST
- Session goal: Diagnose why `gpt-5.5` did not show the same 1000k context as `gpt-5.4`.
- Major changes:
  - Added `gpt-5.5` to the global `~/.code2workspace/config.toml` `openai_paid` provider so it inherits the existing `max_input_tokens = 1000000` profile.
  - Added `gpt-5.5` plus a 1000k profile override to the worktree `.code2workspace/config.toml` provider list.
- Validation: TOML parsing passed; mocked/local `create_model` checks reported `context_limit=1,000,000` for both `openai_paid:gpt-5.5` and `openai:gpt-5.5`.
- Next step: Restart any already-running CLI/TUI/Web server process so cached model selectors reload the updated config.

### 2026-05-11 10:07 CST
- Session goal: Recover the `supervisor-graph-runtime` worktree back to the supervisor-first runtime state before the QA-only packaging pass.
- Major changes:
  - Restored `libs` supervisor graph runtime files and guidance assets from the surviving local worktree copy, then removed the old soft planner routing module again.
  - Reverted QA-only runtime behavior: no forced generic QA mode, no project-local `backend/config/agent_models.json`, normal `.env` / `~/.code2workspace/config.toml` model config, and isolated project-root session workspaces by default.
  - Updated overview handoff/status notes so the active branch is again `feature/supervisor-graph-runtime`.
- Validation: supervisor/orchestration/agent focused tests passed (`26 passed`); config/main/non-interactive/session tests passed with a clean temporary HOME (`454 passed`); direct run with the user's real HOME has one environment-dependent config leak from `~/.code2workspace/config.toml`.
- Next step: run the broader CLI test suite or a real `code2workspace -n "Reply with OK only." -q` smoke once the local model environment is intentionally set.

### 2026-05-11 01:46 CST
- Session goal: Test whether more detailed capability descriptions improve generic supervisor orchestration quality.
- Major changes:
  - Expanded `libs/cli/code2workspace_cli/supervisor_capabilities.py` from one-line summaries into structured capability contracts with execution focus, preferred inputs, expected outputs, stop conditions, and anti-drift guidance.
  - Added `generic_qa` family guidance plus generic node guidance assets for `init_generic`, `worker_context`, `worker_solution`, and `compose_generic`, and changed generic classification to attach `generic_qa` by default.
  - Added `experiments/harness/evaluate_generic_capability_prompts.py` and generated a five-case evaluation artifact set under `experiments/harness/runs/generic-capability-prompt-eval/20260510T174323Z/`.
- Validation: targeted generic runtime tests passed (`44 passed`); broader CLI/config/agent/supervisor suite passed (`632 passed`); all 5 business cases in the new eval kept the generic graph and hit the expected guidance/contract checks.
- Next step: once a live model key is filled into `backend/config/agent_models.json`, run a real interactive or non-interactive QA batch to see whether the richer worker contracts improve actual answer quality and not only prompt structure.

### 2026-05-08 19:20 CST
- Session goal: Make the thesis draft treat benchmark as a first-class system scenario alongside github2workspace.
- Major changes:
  - Updated `experiments/harness/THESIS_FULL_DRAFT_ZH.md` so chapters 2-4 now define two core task families, add the benchmark main chain to the system architecture, and describe Supervisor Graph as the shared mechanism for sequential repository graphs and shared-input parallel benchmark graphs.
  - Updated `experiments/harness/THESIS_OUTLINE_ZH.md`, `docs/research/thesis-log.md`, and `docs/overview/current-status.md` to match the new thesis framing.
  - Regenerated `experiments/harness/code2workspace_毕业论文_新版结构.docx` from the updated markdown using `uv run --with python-docx`.
- Validation: focused thesis/harness tests passed (`14 passed`); DOCX generation completed.
- Next step: when polishing chapter 5, keep the benchmark results tied back to the chapter 2-4 system task-family framing rather than describing them as an external script-only experiment.

### 2026-05-08 14:53 CST
- Session goal: Switch the deployed web UI to the version with a right-side workspace directory panel.
- Major changes:
  - Replaced the first migrated chat-only frontend/backend with the newer web workbench from the main worktree, including `WorkspacePanel`, workspace tree hooks, file preview helpers, upload/download/delete workspace APIs, and matching tests.
  - Rebuilt the Next static export and restarted the 8084 service; current Uvicorn PID is `2659110` with child LangGraph server PID `2659127`.
- Validation: backend webapp tests passed (`45 passed`); frontend Vitest suite passed (`43 passed`); `npm run build` completed; Playwright loaded `http://127.0.0.1:8084/` and confirmed the `Workspace` panel is visible. Screenshot: `.works/webapp-8084-workspace-panel.png`.
- Next step: open `http://127.0.0.1:8084/`, create or select a conversation, and use the right-side Workspace panel to inspect that thread's working directory.

### 2026-05-08 14:43 CST
- Session goal: Migrate the available web workbench frontend into the supervisor graph runtime worktree and deploy it on port 8084.
- Major changes:
  - Migrated the web-workbench `apps/webapp` implementation, including the Next static export under `apps/webapp/frontend/out`, the Starlette frontend serving route, `/langgraph/*` proxy, thread/workspace APIs, model settings APIs, and web runtime bridge.
  - Added `libs/cli/code2workspace_cli/thread_history.py` and updated `server_manager.py` project-context capture so web-launched LangGraph server processes can recover the reference project root from isolated workspaces.
  - Restarted the 8084 service with the migrated frontend/backend; Uvicorn is running as PID `2645183` with a child LangGraph server PID `2645192`.
- Validation: `py_compile` passed for migrated Python modules; `apps/webapp/tests` passed (`27 passed`); `GET /`, frontend CSS/JS assets, `/api/models`, `/langgraph/info`, and a Playwright page load all succeeded. Screenshot: `.works/webapp-8084-smoke.png`.
- Next step: use `http://127.0.0.1:8084/` for the chat UI; stop it with `kill 2645180` when done so the child server shuts down cleanly.

### 2026-05-08 14:37 CST
- Session goal: Check whether the supervisor graph runtime worktree still has a web frontend and expose the available web surface on port 8084.
- Major changes:
  - Confirmed `apps/webapp` is API-backend only; the checked-in browser frontend/static SPA assets are intentionally absent.
  - Started the Starlette/Uvicorn API backend on `0.0.0.0:8084` with logs at `.works/webapp-8084.log`.
- Validation: `GET /api/health` returned `{"ok":true}`; `GET /api/sessions` and a create/delete session smoke flow succeeded.
- Next step: if a browser UI is needed, intentionally reintroduce or build a frontend that calls the existing `/api/*` backend routes.

### 2026-05-07 22:47 CST
- Session goal: Align the supervisor-runtime generic graph with the newer mainline generic orchestration idea of one bounded parallel layer plus normal long-form answer synthesis.
- Major changes:
  - Updated `.worktrees/supervisor-graph-runtime/libs/code2workspace/code2workspace/orchestration_runtime.py` so first-round generic graphs now use `init_generic -> worker_context -> worker_solution -> compose_generic -> summarize` instead of the older `analyze_task` placeholder shape.
  - Tightened report-vs-generic disambiguation in both the rule fallback and the LLM classifier instructions so prompts like `先给我一个口头判断` / `不要正式写作` / `区分证据和猜测` stay on the generic path.
  - Updated the focused worktree tests and reran a generic-only supervisor routing replay; the new run under `experiments/harness/runs/supervisor-routing-trigger-eval/20260507T143455346391Z/` shows `5/5` correct generic classifications and the expected new graph skeleton, though that replay used rules fallback because `openai_paid` credentials were missing in the shell.
- Validation: `PYTHONPATH=. uv run --project libs/cli --group test pytest libs/code2workspace/tests/unit_tests/test_orchestration_runtime.py libs/cli/tests/unit_tests/test_supervisor_runtime.py -q` passed (`37 passed`); `PYTHONPATH=. uv run --project libs/cli python experiments/harness/evaluate_supervisor_routing.py --model openai_paid:gpt-5.4 --family generic` completed and wrote a new routing report with `model_available = False`.
- Next step: rerun the same generic routing evaluation with real `openai_paid` credentials, then decide whether the generic graph should expose worker roles as stable semantic names or eventually derive them more dynamically from the batch plan itself.

### 2026-05-07 00:20 CST
- Session goal: Add a lightweight routing-trigger evaluation for the three special supervisor task families and record real prompt-to-graph outcomes without running full long tasks.
- Major changes:
  - Added `experiments/harness/evaluate_supervisor_routing.py`, which builds prompt variants from real historical `github2workspace`, `benchmark`, and `report` cases, runs task-family classification plus first-round `plan_round()`, and writes `routing_eval.json` / `routing_eval.md`.
  - Added a rules-only fallback mode so routing checks can still run when the current worktree lacks model credentials; the report explicitly records whether classification used a model or forced rule fallback.
  - Generated the first routing-trigger artifact set under `experiments/harness/runs/supervisor-routing-trigger-eval/20260506T161917Z/` and added a run-folder README for quick navigation.
- Validation: `uv run --project libs/cli python -m py_compile experiments/harness/evaluate_supervisor_routing.py` passed; `uv run --project libs/cli python experiments/harness/evaluate_supervisor_routing.py --rules-only --output-root experiments/harness/runs/supervisor-routing-trigger-eval` completed and produced a `9/9` correct routing snapshot.
- Next step: rerun the same evaluation without `--rules-only` once a working model credential is available, so the new shared LLM classifier path can be measured against the same prompt set.

### 2026-05-07 00:13 CST
- Session goal: Remove the last split between CLI-side and shared supervisor task-family classification, and make the special-task router live in the main orchestration runtime.
- Major changes:
  - Moved the LLM-backed hybrid task-family classifier into `libs/code2workspace/code2workspace/orchestration_runtime.py`, including the constrained JSON prompt and the low-confidence fallback to the existing rule markers.
  - Simplified `libs/cli/code2workspace_cli/supervisor_runtime.py` so the CLI wrapper now calls the shared classifier instead of carrying its own duplicate prompt/constants/classification function.
  - Added shared runtime classifier coverage in `libs/code2workspace/tests/unit_tests/test_orchestration_runtime.py`, updated CLI tests to call the shared helper, and corrected `docs/overview/current-status.md` so `planning-guide` is no longer described as an active routing helper.
- Validation: `uv run --project .worktrees/supervisor-graph-runtime/libs/cli python -m py_compile ...` passed for the touched files; `uv run --project .worktrees/supervisor-graph-runtime/libs/cli --group test pytest .worktrees/supervisor-graph-runtime/libs/code2workspace/tests/unit_tests/test_orchestration_runtime.py .worktrees/supervisor-graph-runtime/libs/cli/tests/unit_tests/test_supervisor_runtime.py -q` passed (`37 passed`).
- Next step: if desired, sweep remaining thesis/history docs that still mention `planning-guide` as an active router, and consider tightening when the shared classifier should skip LLM calls for obviously single-family prompts.

### 2026-05-06 16:29 CST
- Session goal: Integrate the user's off-machine early experiment history and bioinformatics-task framing into the thesis materials while keeping the current in-repo evidence boundary clear.
- Major changes:
  - Expanded `experiments/harness/code2workspace_开题报告.md` with a stronger bioinformatics-task background plus the early cross-agent comparison story (`cline` / `deepagents` / `opencode`), the later model-comparison / experience-trace stage (`Xiaomi MiMo` / `Claude` / `GPT-5.1`), and the planned final three-way ablation.
  - Updated `experiments/harness/THESIS_EXPERIMENT_DESIGN_ZH.md` to add new research questions, comparison groups, existing-experiment notes, schedule rows, and reserved tables/figures for the off-machine baseline/model comparisons and the final ablation.
  - Added matching context in `experiments/harness/THESIS_FULL_DRAFT_ZH.md` so chapter 1 now better motivates bioinformatics repos as hard execution targets and chapter 5 now treats the off-machine agent/model comparisons as system-evolution background rather than directly reproducible main-table evidence.
- Validation: `PYTHONPATH=. uv run --project libs/cli --group test pytest experiments/harness/tests/test_thesis_asset_notes.py experiments/harness/tests/test_code2workspace_harness.py -q` passed (`14 passed`).
- Next step: when the raw logs from the other machine are available, materialize them into `表 5-1a` / `表 5-1b`, then decide the final ablation's reporting format for `表 5-13` and `图 5-6`.

### 2026-05-06 16:16 CST
- Session goal: Fold the user's off-machine early experiment history into the thesis/proposal structure without overstating currently reproducible evidence.
- Major changes:
  - Updated `experiments/harness/code2workspace_开题报告.md` to add the early-agent comparison story (`cline` / `deepagents` / `opencode` on 8 bioinformatics repos), the later model-comparison / experience-trace stage (`Xiaomi MiMo` / `Claude` / `GPT-5.1` on nearly 24 repos), and the final three-way ablation plan.
  - Expanded `experiments/harness/THESIS_EXPERIMENT_DESIGN_ZH.md` with new research questions, comparison groups, existing-experiment notes, schedule rows, and reserved tables/figures for the off-machine baseline/model comparisons plus the final ablation.
  - Added matching context in `experiments/harness/THESIS_FULL_DRAFT_ZH.md` so chapter 5 now explains that the early cross-agent/model work is background for baseline selection and system evolution, not yet a directly reproducible main-table result.
- Validation: `PYTHONPATH=. uv run --project libs/cli --group test pytest experiments/harness/tests/test_thesis_asset_notes.py experiments/harness/tests/test_code2workspace_harness.py -q` passed (`14 passed`).
- Next step: when the raw records from the other machine are available, materialize them into `表 5-1a` / `表 5-1b` and then decide whether the final ablation should be shown as counts, rates, or a compact scorecard.

### 2026-05-06 15:32 CST
- Session goal: Locate any existing opening-report material and align the proposal with the current thesis direction.
- Major changes:
  - Searched the worktree, parent repository, and local reference-material folder for `开题报告` / proposal / task-book files; no project-specific opening report existed in the repo, only unrelated local samples under `/home/zhangpf/参考模版（注意内容无关）`.
  - Added `experiments/harness/code2workspace_开题报告.md` as the current opening-report draft aligned with the updated repository-to-workspace thesis title, Supervisor Graph runtime, evidence-backed evaluation, experiment counts, schedule, feasibility analysis, and references.
  - Updated `experiments/harness/README.md` so the new opening-report draft is listed with the other thesis artifacts.
- Validation: thesis/harness focused tests passed (`14 passed`).
- Next step: if a school-format `.doc/.docx` opening-report template is required, transfer this Markdown content into that template or add a small generator.

### 2026-05-06 15:18 CST
- Session goal: Improve thesis wording so the draft reads less like a development log and uses more concrete experiment counts.
- Major changes:
  - Revised `experiments/harness/THESIS_FULL_DRAFT_ZH.md` to use a more formal thesis tone in the abstract, system architecture, harness analysis, two-hour reduced evaluation, Supervisor Graph demo, chapter 5 summary, and conclusion.
  - Replaced broad qualitative claims with concrete counts/ratios where supported: one-shot `3/8`, project-skill `4/4`, two-hour reduced evaluation `2 completed / 2 blocked / 1 service error`, SWE-bench Lite `3 resolved / 5`, benchmark snapshot `4 success / 1 partial / 3 blocked`, and Supervisor Graph `2/2`.
  - Reframed incomplete experiments as extension designs rather than current conclusions, and reduced branch-sensitive frontend wording by centering the API/CLI/LangGraph execution chain.
- Validation: `PYTHONPATH=. uv run --project libs/cli --group test pytest experiments/harness/tests/test_thesis_asset_notes.py experiments/harness/tests/test_code2workspace_harness.py libs/cli/tests/unit_tests/test_supervisor_runtime.py -q` passed (`36 passed`, warnings only).
- Next step: generate or add the figure 5-4 N50/contig-count chart and then regenerate the thesis DOCX.

### 2026-05-07 21:34 CST
- Session goal: Replay four report-generation prompts on the `supervisor-graph-runtime` worktree and record both routing behavior and real execution bottlenecks.
- Major changes:
  - Added a focused four-prompt routing replay under `experiments/harness/runs/supervisor-routing-trigger-eval/20260507T130559636349Z/`; all four user report prompts were classified into the `report` family with the expected `init_report -> monitoring_lane -> local_data_lane -> literature_lane -> compose_report -> summarize` graph skeleton.
  - Ran bounded five-minute live non-interactive report replays under `experiments/harness/runs/supervisor-report-cases-bounded/20260507T131756580675Z/` plus an earlier first-case probe tied to `orchestration_runs/20260507T131222693578Z`; none produced a final report body within the budget, but the traces separated three failure depths: `case-04` stalled inside `init_report`, `case-01` / `case-03` reached lane fan-out only, and `case-02` completed `monitoring_lane` and wrote real WHO/CDC surveillance evidence before timing out.
  - Preserved the strongest mid-run artifacts for follow-up debugging: `orchestration_runs/20260507T131810216924Z/worker_outputs/monitoring_lane/*.md` now shows the report lane can produce dated official evidence once started, so the dominant issue is end-to-end latency / lane completion rather than pure misrouting.
- Validation: live routing replay completed with `4/4` expected `report` classifications; bounded report replays all hit the five-minute wall without final answers, but produced reproducible supervisor traces and partial worker outputs.
- Next step: prioritize report runtime optimization around `init_report` latency and parallel lane completion, then rerun the same four-case bounded batch to see whether `case-02` can advance past `monitoring_lane` and whether the XFG-focused prompts still stall before any lane finishes.

### 2026-05-06 15:07 CST
- Session goal: Align thesis materials in `experiments/harness` with the current supervisor graph runtime code and benchmark evidence.
- Major changes:
  - Expanded `THESIS_FULL_DRAFT_ZH.md` so the system and experiment chapters describe the current supervisor-first runtime: generic task flow, task graph planning, case-index retrieval, node-level artifacts, retry/replan behavior, and the `short-read-ecoli-srr001666` benchmark demo.
  - Updated `THESIS_EXPERIMENT_DESIGN_ZH.md` with a new Supervisor Graph research question, experiment-object row, existing-experiment section, schedule row, and thesis-mainline guidance.
  - Updated `THESIS_ASSET_MATRIX_ZH.md` so Supervisor Graph figures/tables point at the worktree code and `workspace/20260505165456/orchestration_runs/20260505T085500Z/benchmark_supervisor_summary.md`.
- Validation: `experiments/harness/tests/test_thesis_asset_notes.py` and `test_code2workspace_harness.py` passed (`14 passed`); supervisor/configurable-model focused tests passed (`57 passed`, warnings only).
- Next step: convert the ready Supervisor Graph benchmark table into a final chart/screenshot asset and then do a consistency pass over chapter 3/5 wording before generating the DOCX.

### 2026-04-30 16:40 CST
- Session goal: Replace the default long-task soft routing with the new supervisor graph runtime from the approved refactor plan.
- Major changes:
  - Added `libs/code2workspace/code2workspace/orchestration_runtime.py` with typed task graphs, graph-round execution, supervisor decisions, and heuristic v1 planners for `github2workspace` and `benchmark`.
  - Added `libs/cli/code2workspace_cli/supervisor_runtime.py` with thread-workspace artifact writing, rebuildable SQLite case indexing, a supervisor loop, and a wrapper graph that sits above the base CLI agent.
  - Changed `create_cli_agent()` so the base workspace agent is now wrapped by the supervisor runtime by default instead of relying on `PlannerRoutingMiddleware` for long-task orchestration.
- Validation: new runtime tests passed (`7 passed` across the new orchestration/unit suites); targeted CLI/runtime regressions passed (`175 passed`); focused TUI startup unit checks passed (`3 passed`); repeated real non-interactive smokes on `-M openai:gpt-5.4` were mixed (one earlier exit `0`, latest 30-second rerun timed out); scripted real TUI startup still timed out under capture.
- Next step: harden the interactive TUI real-startup smoke, then expand the supervisor runtime beyond `github2workspace` / `benchmark` to complex QA and report flows.

### 2026-04-30 16:47 CST
- Session goal: Remove the remaining hard coupling in supervisor routing and make the paid relay the default runtime path.
- Major changes:
  - Refactored the planner so every task now enters supervisor first; unknown tasks get a generic `analyze -> execute -> summarize` graph while known families use guidance/template overlays.
  - Extended the known-family guidance set to include `report`, and added a minimal custom alias provider `openai_paid` pointing at the paid OpenAI-compatible relay without deleting the older relay config.
  - Switched user-level `[models].default` and `[models].recent` to `openai_paid:gpt-5.4`, while retaining `openai` as a labeled fallback provider.
- Validation: focused orchestration + CLI regression suite passed again (`186 passed`); default no-`-M` smoke still exits `0`; manual direct-invoke experiments now show `benchmark`, `github2workspace`, `report`, and a generic task all entering supervisor and writing round artifacts, though live runs still tend to stall at the first or second node.
- Next step: attack the live worker stall problem itself, especially first-node report initialization and the long-running build/benchmark execution nodes.

### 2026-04-30 17:40 CST
- Session goal: Move task experience further out of Python branches and into Skill assets, then rerun the three representative task families.
- Major changes:
  - Added `.code2workspace/skills/supervisor-guidance/` and changed `supervisor_capabilities.py` to load node guidance from those files instead of relying on embedded node-strategy strings.
  - Kept capability-to-tool mappings in code while making worker prompt assembly combine capability summaries, preferred tool surfaces, and skill-backed node guidance.
  - Added `docs/overview/supervisor-system-architecture.md` with the current end-to-end architecture diagram and layer split.
- Validation: targeted supervisor-runtime tests passed after the Skill-layer shift; full focused regression suite passed again (`348 passed`).
- Next step: continue reducing hardcoded family graph skeletons and investigate why `benchmark.register` / `report.init_report` still return too slowly in live runs.

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

### 2026-05-05 15:09 CST
- Session goal: Stabilize the supervisor-driven benchmark helper-first chain in the `supervisor-graph-runtime` worktree using the user's latest real-case evidence.
- Major changes:
  - Root-caused the first non-interactive benchmark failure to the local `langgraph dev` server being started without `--allow-blocking` while the supervisor runtime performs synchronous file/SQLite/helper subprocess work; fixed `_build_server_cmd()` so the CLI server now opts into blocking explicitly.
  - Added deterministic benchmark fast paths in `libs/cli/code2workspace_cli/supervisor_runtime.py` for `register`, `spades`, `megahit`, and `summarize`, so those nodes can call the checked-in benchmark helper directly, write canonical artifacts, and return `WorkerResult` without depending on the model to decide when to stop.
  - Extended supervisor-runtime regression coverage to enforce the new server flag and the deterministic benchmark worker behavior, including helper-driven register scaffolding, repo-node result manifests, and benchmark summary artifacts.
- Validation: `uv run --project libs/cli --group test pytest libs/cli/tests/unit_tests/test_server_helpers.py libs/cli/tests/unit_tests/test_supervisor_runtime.py -q` passed (`23 passed`); a fresh live benchmark smoke under `workspace/20260505145718/orchestration_runs/20260505T065722Z` now reaches `register finished` immediately and enters real helper-driven SPAdes execution instead of stalling on the first node.
- Next step: Let the fresh SPAdes-heavy smoke finish, confirm the chain advances through `megahit` and `summarize`, then decide whether any remaining instability is pure workload cost or still a supervisor-control issue.

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

### 2026-05-05 15:35 CST
- Session goal: Remove retired orchestration wrappers from the supervisor-runtime branch so the branch reflects the current `supervisor -> generic worker` architecture more honestly.
- Major changes:
  - Deleted the unused CLI soft-routing module `libs/cli/code2workspace_cli/planner_routing.py` and its dedicated unit tests.
  - Removed the thin `github2workspace-orchestrator` project Skill wrapper and the empty `paper2workspace-orchestrator` legacy shell, then updated skill-discovery tests accordingly.
  - Kept `planning-guide` in place as an optional helper, but changed it so `github2workspace` tasks no longer recommend the deleted wrapper skill; updated harness / skill-test fixtures to match.
- Validation: focused tests passed for supervisor-surface cleanup (`libs/cli/tests/unit_tests/skills/test_superagent_project_assets.py`, selected `experiments/harness/tests/test_project_skill_helpers.py`, `experiments/skill_tests/tests/test_planning_tool.py`, and `libs/cli/tests/unit_tests/test_agent.py -k planner_routing_middleware_removed_when_skills_enabled`); one broader harness file still has a pre-existing unrelated failure in `test_benchmark_orchestrator_execution_ready_resolves_existing_paths`.
- Next step: if you want the branch simplified further, the next high-value cut is the report-specific project subagent stack (`report-researcher` / `report-synthesizer` / `report-web-researcher`) and any remaining default worker injection of project subagents.

### 2026-05-05 16:03 CST
- Session goal: Exercise the supervisor-runtime branch with one real `github2workspace` Flye task and one real WHO-style XFG.1.1 report task, then inspect success state and orchestration traces.
- Major changes:
  - Ran a full non-interactive `github2workspace` task under `workspace/20260505150750/`: the supervisor graph completed `inspect -> build -> wdl -> summarize`, materialized `Flye`, authored `Flye_Dockerfile` and `Flye.wdl`, built image `flye`, passed a real container toy-data assembly, and reached Cromwell `Succeeded` after repairing an initial `AF_UNIX path too long` failure by exporting `TMPDIR=/tmp`.
  - Ran a full non-interactive `report` task under `workspace/20260505153357/`: the report graph completed `init_report -> monitoring/local_data/literature lanes -> compose_report -> summarize`, produced lane evidence plus a final WHO-style XFG.1.1 risk assessment and diagnostics under `compose/`.
  - Confirmed the current `tool_activity.jsonl` contract is node-level only (`node_started` / `node_finished`), while the richer reasoning/evidence trail currently lives in `worker_outputs/*.json`, `node_traces/*.json`, lane files, and task-specific artifacts rather than a per-tool call log.
- Validation: `github2workspace` finished successfully with real outputs in `workspace/20260505150750/results/{docker_test,wdl_file,wdl_result}`; `report` finished successfully with `compose/final_report.md` and `compose/report_diagnostics.json` under `workspace/20260505153357/orchestration_runs/20260505T073400Z/`; a trivial smoke task also confirmed the supervisor wrapper writes orchestration artifacts end to end.
- Next step: if observability is the next priority, extend `libs/cli/code2workspace_cli/supervisor_runtime.py` so `tool_activity.jsonl` records actual tool invocations/results in addition to node lifecycle events, and consider promoting report `compose/*` artifacts to a flatter top-level contract for easier discovery.

### 2026-05-05 16:07 CST
- Session goal: Re-run the same supervisor-runtime validation on the current worktree and record the exact artifact roots actually produced in this session.
- Major changes:
  - Confirmed a real `github2workspace` success under `workspace/20260505150750/`, including `Flye_Dockerfile`, `results/docker_test/docker_run.log`, `results/wdl_file/Flye.wdl`, and `results/wdl_result/metadata_retry.json` with Cromwell `Succeeded`.
  - Confirmed a real `report` success under `workspace/20260505154257/orchestration_runs/20260505T074301Z/`, with the final report at `composition/final_report.md` plus lane artifacts in `evidence_lanes/{monitoring_lane,local_data_lane,literature_lane}/`.
  - Reconfirmed that `tool_activity.jsonl` still captures only node lifecycle, not individual tool calls; the actionable evidence trail remains split across `worker_outputs/*.json`, `node_traces/*.json`, and task-specific lane/result artifacts.
- Validation: both non-interactive runs exited `0`; `github2workspace` resolved an initial Cromwell/Flye path-length failure via retry and still ended in `Succeeded`; `report` covered the requested three dimensions and stated the XFG-vs-XFG.1.1 extrapolation boundary explicitly.
- Next step: tighten observability first, especially per-tool activity logging inside supervisor workers, before relying on `tool_activity.jsonl` as a detailed tool-trace artifact.

### 2026-05-05 16:41 CST
- Session goal: Make benchmark per-tool workers truly run concurrently after `register`, then verify the full helper-first two-tool path.
- Major changes:
  - Offloaded deterministic benchmark helper execution from `_invoke_worker_agent()` to a worker thread so blocking helper subprocesses no longer serialize ready `spades` / `megahit` branches inside the async graph scheduler.
  - Added a regression test with blocking fake deterministic workers that asserts both ready benchmark branches are active at the same time.
  - Ran a fresh full benchmark supervisor task under `workspace/202605051600_parallel/orchestration_runs/20260505T081847Z`; `tool_activity.jsonl` shows `spades` and `megahit` both start after `register` before either finishes, then the run completes through `summarize`.
- Validation: focused supervisor/orchestration tests passed (`19 passed`); direct supervisor and outer `code2workspace -n ... -q` two-tool benchmark runs both exited with `decision=stop`, `failed_nodes=[]`, and `reason=All nodes completed.`, with the outer CLI run under `workspace/20260505165456/orchestration_runs/20260505T085500Z`.
- Next step: the benchmark supervisor path has the intended fan-out evidence now; the remaining nearby cleanup is improving CLI/client behavior when interrupting long helper runs.

### 2026-05-05 19:23 CST
- Session goal: Test a less prescriptive benchmark prompt where the user gives only the benchmark path, dataset, and metrics while leaving tool choice to the agent.
- Major changes:
  - Ran the natural prompt through the outer `code2workspace -n ... -q` path under `workspace/20260505185712/orchestration_runs/20260505T105716Z`; the planner classified it as `benchmark`, selected `spades` and `megahit`, and preserved the `register -> parallel spades/megahit -> summarize` event order.
  - Found a product-level gap: execution and metric aggregation were correct, but the final benchmark summary did not directly answer which tool looked better.
  - Added benchmark comparison synthesis to the deterministic summary path, writing `comparison` into `benchmark_supervisor_summary.json`, adding a Markdown comparison section, and appending the overall judgment to the summarize worker result.
- Validation: `libs/cli/tests/unit_tests/test_supervisor_runtime.py` passed (`14 passed`); replaying only the summary node on the completed natural-prompt run now reports `Overall favors spades by N50/assembly-size strength, while megahit has the lower contig_count.`
- Next step: the next full natural-prompt benchmark run should verify that the final user-facing `final_summary.md` also carries the comparison sentence from the updated summarize worker result.

### 2026-05-05 17:04 CST
- Session goal: Make normal CLI sessions use the supervisor-runtime branch workspace root consistently.
- Major changes:
  - Changed `prepare_session_cwd()` so isolated sessions launched inside a Git project create `workspace/<timestamp>` under the project root, with the old invocation-cwd behavior kept as the fallback outside projects.
  - Updated focused session-workspace coverage plus README/status/handoff/thesis notes to describe the project-root workspace policy.
- Validation: `uv run --project libs/cli pytest libs/cli/tests/unit_tests/test_session_workspace.py -q` passed (`4 passed`); a direct probe from `libs/cli` resolved to `workspace/20990101000000` relative to the worktree root.
- Next step: decide whether trivial conversational prompts like `你好` should bypass supervisor entirely and fall through to the base chat agent.

### 2026-05-05 17:15 CST
- Session goal: Remove stale report-only subagents and the retired harness-side `OpenClaw` / `ACPX` bridge so the checked-in branch surface matches the validated supervisor runtime.
- Major changes:
  - Deleted `.code2workspace/agents/report-researcher/`, `report-synthesizer/`, and `report-web-researcher/`.
  - Deleted `experiments/harness/skills/openclaw/`, `experiments/harness/import_openclaw_skills.py`, and the matching import/bridge tests and README references.
  - Updated `multi-source-report` plus the live respiratory / EpiETL helper skills so they now describe supervisor/generic-worker lane execution instead of `report_agent` or report-only subagent names.
- Validation: targeted cleanup regression set passed with `83 passed` when excluding one known pre-existing benchmark-helper failure in `experiments/harness/tests/test_project_skill_helpers.py::test_benchmark_orchestrator_execution_ready_resolves_existing_paths`; the full same command still reproduces that single unrelated failure.
- Next step: if more cleanup is wanted later, evaluate separately whether the generic filesystem subagent loader itself should remain as a platform feature; this pass intentionally removed stale checked-in assets without deleting the loader mechanism.

### 2026-05-05 17:42 CST
- Session goal: Prune the most obviously branch-irrelevant docs and experiment writeups that still described retired `paper2workspace`, report-subagent, or ACPX/OpenClaw paths.
- Major changes:
  - Deleted `docs/archive/acp-agent-skills-plan.md` and `docs/superpowers/specs/2026-04-23-multi-source-report-subagent-budget-design.md`.
  - Deleted `experiments/harness/THESIS_EXPERIMENT_DESIGN_ZH.md` and `experiments/harness/THESIS_FULL_DRAFT_ZH.md`, both of which still treated `paper2workspace` routing and old orchestrator surfaces as current.
  - Kept `docs/research/thesis-log.md` and the active overview docs as historical/context material, but not as sources of current branch behavior.
- Validation: post-cleanup search over `docs/` and `experiments/` no longer finds active design/spec/draft files under those trees that still define old report-only subagent names or the removed OpenClaw/ACPX bridge surfaces; no runnable code paths were changed in this pass.
- Next step: if you want the branch even leaner, the next likely cleanup is purely naming-level work inside still-live helper skills that retain harmless `OpenClaw` metadata or user-agent strings even though the old bridge itself is gone.

### 2026-05-06 10:05 CST
- Session goal: Reorganize `experiments/benchmark/` so the shared dataset layer no longer looks virus-assembly-only, and add realistic shared-dataset candidates for `cirrna` and `免疫逃逸`.
- Major changes:
  - Restored a checked-in `experiments/benchmark/datasets/benchmark_catalog.json` in this worktree and kept the current virus-assembly entries intact.
  - Added `experiments/benchmark/README.md` plus family-level README guides for `cirrna/` and `免疫逃逸/`.
  - Added shared-dataset candidate entries and staged download directories for:
    - `circrna-hela-rnaser-paired`
    - `circrna-blood-prjna722046`
    - `immune-escape-rbd-functional-dms`
    - `immune-escape-rbd-antibody-escape`
    - `immune-escape-covabdab-structural-bundle`
- Validation: `python3 .code2workspace/skills/benchmark-workflow-orchestrator/scripts/benchmark_workflow.py catalog-datasets` now prints the restored catalog with `dataset_count = 10`; focused catalog/prepare-case tests passed for the benchmark helper (`3 passed`).
- Next step: the next concrete benchmark extension should update a small representative subset of `cirrna` and `免疫逃逸` tool `input.json` files to point at the new shared dataset directories instead of historical absolute paths.

### 2026-05-05 21:02 CST
- Session goal: Add a user choice gate to the generic supervisor task flow without changing the three special task families.
- Major changes:
  - Changed the generic graph from one-shot `analyze -> execute -> summarize` to staged `analyze`, then user-selected `execute -> summarize`.
  - Added simple / medium / difficult generic approach options, persisted option/selection artifacts, and wired the CLI supervisor wrapper to ask the user through the existing `ask_user` interrupt path.
  - Left `github2workspace`, `benchmark`, and `report` graph skeletons untouched.
- Validation: focused supervisor/orchestration tests passed (`21 passed`); CLI non-interactive/agent regression tests passed (`133 passed`); `uv run --project libs/cli python -m py_compile` passed for the changed runtime files.
- Next step: run a real interactive TUI generic prompt to verify the option picker UX, since the focused tests cover the runtime contract but not the visual interaction.

### 2026-05-05 22:20 CST
- Session goal: Diagnose and fix a failed interactive generic task after the new simple/medium/difficult choice gate.
- Major changes:
  - Root-caused the failure shape in `workspace/20260505214253/orchestration_runs/20260505T135424Z`: `execute_task` started, then no worker output or `node_finished` event was written, matching an interrupt/control-flow exception swallowed by the generic worker exception guard.
  - Changed `execute_graph_round()` so LangGraph `GraphBubbleUp` / `GraphInterrupt` exceptions are re-raised instead of converted into ordinary failed worker results.
  - Added `node_interrupted` logging in `_run_worker_and_capture()` before re-raising, so future tool approval / ask-user pauses do not look like silent node stalls.
- Validation: focused supervisor/orchestration tests passed (`24 passed`); `uv run --project libs/cli python -m py_compile` passed for the changed runtime files.
- Next step: rerun the same TUI query; if it reaches web-search approval or tool execution instead of `unexpected exception`, the control-flow fix is confirmed live.

### 2026-05-05 22:56 CST
- Session goal: Preserve the generic difficulty-selection interaction in the TUI transcript after the user answers.
- Major changes:
  - Added a read-only `AskUserTranscript` widget that renders the original ask-user question plus the selected answer.
  - Changed TUI ask-user answered/cancelled handlers to replace the interactive menu with that transcript instead of removing it outright.
  - Kept the supervisor/runtime choice mechanics unchanged; this is only a CLI display-layer persistence change.
- Validation: ask-user/app focused tests passed (`33 passed`); supervisor/orchestration focused tests passed (`24 passed`); `uv run --project libs/cli python -m py_compile` passed for changed TUI files.
- Next step: do a quick manual TUI run to confirm the transcript placement looks good after selecting simple/medium/difficult.

### 2026-05-05 23:12 CST
- Session goal: Fix the TUI copy-to-clipboard path that showed a success toast even when nothing reached the real clipboard.
- Major changes:
  - Reordered clipboard backends so explicit system/terminal methods are preferred before Textual's `app.copy_to_clipboard()` path.
  - Added regression coverage for the new order, including the mouse-up case where OSC 52 should run before the Textual clipboard path.
- Validation: clipboard-focused exception/behavior tests passed (`7 passed`); `uv run --project libs/cli python -m py_compile` passed for the changed clipboard files.
- Next step: verify once manually in the TUI that selecting text now copies into the actual host clipboard instead of only showing the toast.

### 2026-05-05 23:43 CST
- Session goal: Surface more supervisor/runtime trace detail directly in the TUI instead of leaving most orchestration state only in artifacts.
- Major changes:
  - Added supervisor custom-stream events for run start/finish, round start, generic choice request/selection, node start, node finish, and node interrupt in `libs/cli/code2workspace_cli/supervisor_runtime.py`.
  - Updated `execute_task_textual()` to subscribe to `custom` stream mode and render those supervisor events as inline `AppMessage` records in the TUI.
  - Added a pure formatting regression test for supervisor-event rendering; kept the change display-layer only, without altering worker execution semantics.
- Validation: `py_compile` passed for the changed runtime/adapter files; targeted tests passed for supervisor generic orchestration (`1 passed`), graph interrupt propagation (`1 passed`), and supervisor-event formatting (`1 passed`). A broader batched `textual_adapter` suite still hit the existing pytest-asyncio teardown timeout under this environment, so confidence comes from the focused checks rather than the full file sweep.
- Next step: do one manual TUI run and confirm the chat now shows round/node lifecycle lines alongside the existing tool-call cards.

### 2026-05-06 00:03 CST
- Session goal: Stop new interactive sessions from falling back to `~/workspace/...` when the launch cwd unexpectedly resolves to the home directory.
- Major changes:
  - Added `resolve_default_session_invocation_cwd()` in `session_workspace.py` so startup keeps the process cwd in normal cases but falls back to the current repo/worktree root when the default cwd is exactly the user's home directory.
  - Updated both interactive and non-interactive startup paths in `main.py` and `non_interactive.py` to use that resolver before creating `workspace/<timestamp>`.
  - Kept `prepare_session_cwd()` itself conservative so explicitly supplied invocation directories still behave exactly as before.
- Validation: session-workspace focused tests passed (`6 passed`); `py_compile` passed for the changed startup/workspace files.
- Next step: manually launch a fresh TUI session from the current worktree and verify the status bar/workspace path lands under `<project>/workspace/<timestamp>` again.

### 2026-05-06 09:02 CST
- Session goal: Make TUI copy-on-selection update both the remote host clipboard and the local terminal clipboard during SSH sessions when possible.
- Major changes:
  - Added SSH-session detection in `clipboard.py`.
  - Changed clipboard writes so SSH sessions attempt both `pyperclip` (host clipboard) and OSC 52 (local terminal clipboard), while keeping Textual's clipboard path as fallback only when neither explicit method succeeded.
  - Updated clipboard tests to cover SSH detection, dual-write behavior, and the fallback suppression after successful host/local copies.
- Validation: clipboard-focused tests passed (`9 passed`); `py_compile` passed for the changed clipboard files.
- Next step: manually verify over SSH that a TUI text selection now pastes both on the remote host and on the local machine clipboard, depending on where paste is attempted.

### 2026-05-06 11:32 CST
- Session goal: Determine whether the latest generic-task failures come from current code or from a stale long-running TUI/server process.
- Major changes:
  - Verified both old relay endpoints directly with `curl`: `http://8.221.123.105:8080/v1/chat/completions` and `/v1/responses` both return `OK` for the minimal prompt.
  - Ran fresh in-process comparisons with the current code against the old relay: direct `init_chat_model`, `create_workspace_agent`, `create_cli_agent(...).nodes['fallback']`, and `_invoke_worker_agent()` all succeeded on `Reply with OK only.` in a new Python process.
  - Confirmed the user's live failing TUI/server pair was an older process started at `2026-05-05 23:05 CST`, with `PWD=/home/zhangpf` and `CODE2WORKSPACE_CLI_SERVER_CWD=/home/zhangpf/workspace/20260505230552`, which strongly suggests the observed failures were coming from a stale long-lived runtime rather than the newly patched code path.
- Validation: fresh reproducibility probes succeeded across all four layers (direct model, workspace agent, CLI base agent, supervisor worker) against the old relay; no new code change was needed in this diagnostic step.
- Next step: fully stop the old TUI/server process and start a new session from the current worktree before judging whether any further generic-runtime fixes are still needed.

### 2026-05-05 21:43 CST
- Session goal: Remove benchmark coupling to concrete `spades` / `megahit` runtime and guidance entries, then rerun the natural benchmark task.
- Major changes:
  - Replaced benchmark planner default-tool coupling with catalog-based selection from `experiments/benchmark/datasets/benchmark_catalog.json`; the natural `short-read-ecoli-srr001666` prompt still selects the catalog's shared compatible tool pair.
  - Removed runtime-local per-tool expected-output mapping and now derive expected outputs from each case manifest; replaced tool-specific node guidance files with generic `benchmark_case.md`.
  - Re-ran the less prescriptive benchmark prompt through outer `code2workspace -n ... -q` under `workspace/20260505212743/orchestration_runs/20260505T132747Z`; it completed with `register -> parallel per-case workers -> summarize` and the final comparison sentence.
- Validation: focused supervisor/orchestration tests passed (`22 passed`); grep over `libs/cli/code2workspace_cli/supervisor_runtime.py` and `.code2workspace/skills/supervisor-guidance/references/nodes` no longer finds `spades` / `megahit`; real benchmark run exited with `decision=stop`, `failed_nodes=[]`.
- Next step: if benchmark generality matters further, test another catalog dataset such as long-read E. coli so the catalog selector is exercised beyond the short-read pair.

### 2026-05-06 09:30 CST
- Session goal: Rerun the long-read benchmark after the user deleted benchmark catalog/readme files to see whether the agent can choose tools without structured catalog guidance.
- Major changes:
  - Removed the planner fallback that was still reading a parent-project benchmark catalog when the worktree catalog was missing, so deletion in this worktree is now meaningful.
  - Re-ran the long-read prompt under `workspace/20260506092525/orchestration_runs/20260506T012529193142Z`; the graph classified it as `benchmark` but had no `selected_tools`, so deterministic `register` failed with `missing_selected_tools` and summary remained empty/partial.
  - Updated the catalog-selection unit test to use a temporary fixture catalog instead of the now-deleted checked-in catalog.
- Validation: `libs/code2workspace/tests/unit_tests/test_orchestration_runtime.py` passed (`9 passed`); real catalog-free benchmark run reached `decision=stop` with unresolved nodes, confirming catalog-free autonomous benchmark planning is not implemented yet.
- Next step: replace deterministic catalog-first register with a model/asset-inspection register path that can inspect WDL/input directories, choose compatible tools, and then create the fan-out graph.

### 2026-05-05 22:01 CST
- Session goal: Fix false CLI copy toast when mouse selection leaves stale widget selections behind.
- Major changes:
  - Scoped mouse-up copy harvesting to the event widget, its ancestors, and descendants instead of scanning every widget in the app.
  - Passed the `MouseUp` source widget from `app.py` into `copy_selection_to_clipboard()` so stale selections in unrelated widgets no longer produce misleading previews like `". " copied`.
  - Added clipboard regression tests for ignoring unrelated stale selections while preserving related-widget copying.
- Validation: `uv run --project libs/cli pytest libs/cli/tests/unit_tests/test_exception_handling.py -q` passed (`17 passed`); `uv run --project libs/cli python -m py_compile libs/cli/code2workspace_cli/clipboard.py libs/cli/code2workspace_cli/app.py` passed.
- Next step: manually verify in the TUI that dragging over message text either copies the intended text or stays silent if the terminal-native selection is not visible to Textual.

### 2026-05-05 22:53 CST
- Session goal: Remove the oversized TUI startup ASCII art banner.
- Major changes:
  - Changed `WelcomeBanner` to render a compact `code2workspace v...` header instead of the large `DEEP AGENTS` text-art banner.
  - Preserved the existing version/local-install display plus LangSmith/thread/MCP/footer lines.
- Validation: `uv run --project libs/cli pytest libs/cli/tests/unit_tests/test_welcome.py -q` passed (`40 passed`); `uv run --project libs/cli python -m py_compile libs/cli/code2workspace_cli/widgets/welcome.py` passed.
- Next step: start the TUI once to visually confirm the compact welcome header.

### 2026-05-08 12:22 CST
- Session goal: Reorganize the thesis materials to follow a more standard undergraduate engineering-thesis structure modeled on the provided reference paper.
- Major changes:
  - Restructured `experiments/harness/THESIS_FULL_DRAFT_ZH.md` from the older “related work / system / harness method” flow into “绪论 -> 系统需求分析 -> 系统总体设计 -> 详细设计与实现 -> 实验结果与分析 -> 结论”, and rewrote the chapter-overview, TOC, chapter-2 content, and section titles to match that framing.
  - Updated `experiments/harness/THESIS_OUTLINE_ZH.md` so the recommended directory, per-chapter writing advice, minimum-deliverable checklist, and final suggested structure now align with the new需求/设计/实现/实验 layout.
  - Synchronized `experiments/harness/THESIS_ASSET_MATRIX_ZH.md` with the new chapter arrangement by renaming the second-chapter figure/table assets and keeping the thesis-facing chart/table mapping consistent.
- Validation: Performed a heading/reference sweep with `rg` plus a section-list check to confirm the draft and outline no longer retain the old top-level chapter names; no code tests were needed because this change is documentation-only.
- Next step: continue tightening chapter 5 so future-planned experiments occupy less space than already completed evidence, and then polish the prose inside chapters 3 and 4 to better match final school-paper style.

### 2026-05-08 12:26 CST
- Session goal: Export the newly restructured thesis draft to a separate DOCX without overwriting the existing thesis document.
- Major changes:
  - Updated `experiments/harness/generate_thesis_docx.py` to accept an optional `--output` argument instead of always writing only `code2workspace_毕业论文.docx`.
  - Generated a new file at `experiments/harness/code2workspace_毕业论文_新版结构.docx` from the current `THESIS_FULL_DRAFT_ZH.md`.
- Validation: `uv run python -m py_compile experiments/harness/generate_thesis_docx.py` passed; `uv run --with python-docx python experiments/harness/generate_thesis_docx.py --output experiments/harness/code2workspace_毕业论文_新版结构.docx` completed successfully and produced a readable OOXML file.
- Next step: spot-check the new DOCX visually in Word/WPS for heading spacing, table pagination, and Mermaid-placeholder layout before using it as the main submission draft.

### 2026-05-08 20:23 CST
- Session goal: Decide whether the thesis needs a technical-principles section and apply the needed thesis edits.
- Major changes:
  - Renamed chapter 2 in `experiments/harness/THESIS_FULL_DRAFT_ZH.md` to `相关技术基础与系统需求分析` and added a compact `2.1` technical foundation section covering LLM agents/tool use, LangGraph/LangChain, Docker/WDL/Cromwell, and harness/benchmark evidence-based evaluation.
  - Synchronized `experiments/harness/THESIS_OUTLINE_ZH.md`, `docs/research/thesis-log.md`, and `docs/overview/current-status.md`; regenerated `experiments/harness/code2workspace_毕业论文_新版结构.docx`.
- Validation: heading/reference sweep passed with `rg`; `generate_thesis_docx.py` compiled; DOCX regeneration completed and the OOXML contained the new chapter title and section headings.
- Next step: visually spot-check the regenerated DOCX in Word/WPS, then continue polishing chapter 3/4 prose and chapter 5 evidence balance.

### 2026-05-08 20:36 CST
- Session goal: Sync the thesis-related harness documents from the user's preferred `test-agent-8081` version into this worktree.
- Major changes:
  - Copied the source worktree's `THESIS*.md`, `generate_thesis_docx.py`, `code2workspace_毕业论文.docx`, and `code2workspace_毕业论文_新版结构.docx` into `experiments/harness/`.
  - Restored the paragraph-style `1.4 研究问题与挑战` and the chapter-2 `系统需求分析` structure from that version; updated `docs/overview/current-status.md` and `docs/research/thesis-log.md` to note the active thesis baseline.
- Validation: byte-compare confirmed the synced thesis files match `test-agent-8081`; `generate_thesis_docx.py` compiled and produced `/tmp/code2workspace_sync_smoke.docx` with the expected headings.
- Next step: continue editing from this synchronized thesis baseline unless the user explicitly asks to reintroduce the technical-principles chapter.

### 2026-05-08 20:43 CST
- Session goal: Add the related-technical-principles section back on top of the synchronized thesis baseline.
- Major changes:
  - Updated `experiments/harness/THESIS_FULL_DRAFT_ZH.md` so chapter 2 is `相关技术基础与系统需求分析`, adding `2.1 相关技术基础` while preserving the paragraph-style `1.4`.
  - Synchronized the chapter-2 structure in `THESIS_OUTLINE_ZH.md`, updated `generate_thesis_docx.py` chapter maps, and regenerated both thesis DOCX outputs.
- Validation: `generate_thesis_docx.py` compiled; DOCX XML contains the new chapter title, `2.1 相关技术基础`, and `2.1.1 大语言模型智能体与工具调用`.
- Next step: visually spot-check the regenerated DOCX in Word/WPS for table of contents, heading spacing, and page breaks.

### 2026-05-08 20:56 CST
- Session goal: Correct thesis Web-layer descriptions to match the current full Web Workbench implementation.
- Major changes:
  - Rewrote thesis references that described `apps/webapp` as only a small backend service so they now describe the Starlette backend, vendored Next.js chat frontend, `/langgraph/*` proxy, `/api/*` management routes, and shared local LangGraph server.
  - Updated `THESIS_OUTLINE_ZH.md`, `THESIS_ASSET_MATRIX_ZH.md`, and overview docs (`current-status`, `session-handoff`, `roadmap`) to remove stale frontend-removal assumptions.
  - Regenerated both thesis DOCX outputs from the updated markdown.
- Validation: searched thesis/overview docs for obsolete web-layer phrasing; `generate_thesis_docx.py` compiled; DOCX XML contains `Web Workbench`, `Next.js chat-first`, `Starlette 后端`, and `/langgraph/*`.
- Next step: visually inspect the Web Workbench diagrams in the generated DOCX and update screenshots in appendix E when convenient.

### 2026-05-08 21:29 CST
- Session goal: Align the thesis materials with the current supervisor-runtime branch and remove report-family exposure from the thesis narrative.
- Major changes:
  - Reworked `experiments/harness/THESIS_FULL_DRAFT_ZH.md` so the thesis now presents Supervisor Graph as the final execution path, keeps one-shot only as the historical baseline / batch launcher, and excludes the `report` family from chapter-3/4 diagrams and chapter-5 evidence.
  - Updated the supporting thesis docs (`THESIS_OUTLINE_ZH.md`, `THESIS_ASSET_MATRIX_ZH.md`, `THESIS_EXPERIMENT_DESIGN_ZH.md`, `THESIS_METHOD.md`, `THESIS_CHAPTER_ZH.md`, `README.md`) plus `docs/overview/supervisor-system-architecture.md`, `docs/overview/current-status.md`, and `docs/research/thesis-log.md` to the same framing.
  - Reworked `experiments/harness/generate_thesis_asset_notes.py` and `test_thesis_asset_notes.py` so the asset-note table numbering now matches the revised chapter-5 Supervisor Graph tables.
- Validation: `PYTHONPATH=. uv run --project libs/cli --group test pytest experiments/harness/tests/test_thesis_asset_notes.py -q` passed (`3 passed`); `PYTHONPATH=. uv run --project libs/cli --group test pytest experiments/harness/tests/test_code2workspace_harness.py -q` passed (`11 passed`); `uv run --with python-docx python experiments/harness/generate_thesis_docx.py` regenerated `code2workspace_毕业论文.docx`; `uv run --project libs/cli python experiments/harness/generate_thesis_asset_notes.py` completed.
- Next step: visually spot-check the regenerated thesis DOCX and decide whether the appendix asset-note bundle should also gain an explicit table-5-9 note for the Supervisor Graph benchmark demo.

### 2026-05-08 22:04 CST
- Session goal: Fix inconsistent thesis DOCX indentation caused by hard-wrapped Markdown body lines.
- Major changes:
  - Updated `experiments/harness/generate_thesis_docx.py` so adjacent body lines without a blank-line/block boundary are joined into one Word paragraph, preserving spaces around ASCII terms when needed.
  - Regenerated `experiments/harness/code2workspace_毕业论文.docx` and `experiments/harness/code2workspace_毕业论文_新版结构.docx` from the current thesis markdown.
- Validation: `generate_thesis_docx.py` compiled; targeted hard-wrap join probe merged the reported paragraph into one text block; both regenerated thesis DOCX files contain no stale `技能感知规划层` / `hard router` paragraph.
- Next step: visually spot-check the regenerated DOCX in Word/WPS for page breaks and table layout.

### 2026-05-08 22:11 CST
- Session goal: Make the thesis abstract less overloaded with experiment counts.
- Major changes:
  - Rewrote the Chinese abstract's experiment paragraph in `experiments/harness/THESIS_FULL_DRAFT_ZH.md` to summarize layered validation, main bottlenecks, and method value without listing every run count.
  - Applied the same simplification to the English Abstract and regenerated both thesis DOCX outputs.
- Validation: `generate_thesis_docx.py` compiled; regenerated DOCX text no longer contains the old abstract phrases `已整理结果包括` or `The current evidence has already`.
- Next step: visually review the abstract in Word/WPS for final wording and page flow.

### 2026-05-08 22:30 CST
- Session goal: Remove thesis-facing harness narrative and polish the documents around the current Supervisor Graph framing.
- Major changes:
  - Reworked the active thesis draft and supporting thesis notes so the formal paper now centers on Supervisor Graph orchestration, node-level artifacts, and evidence-backed completion judgment instead of local harness-loop methods.
  - Removed surface/variant/keep-discard/proposer wording from the thesis markdown, task book, proposal, outline, asset matrix, experiment-design note, appendix template, generated asset-note wording, and regenerated thesis DOCX outputs.
  - Updated `docs/overview/current-status.md` and `docs/research/thesis-log.md` to record that harness remains an engineering area but is no longer part of the thesis method narrative.
- Validation: `py_compile` for thesis generators passed; `test_thesis_asset_notes.py` passed (`3 passed`); regenerated both thesis DOCX outputs; DOCX XML search found no `harness`, `surface`, `variant`, `proposer`, or `外环` terms.
- Next step: visually spot-check both regenerated DOCX files in Word/WPS for table numbering and page flow.

### 2026-05-10 16:29 CST
- Session goal: Move thesis-related templates and document files out of the current worktree into the user's external backup folder.
- Major changes:
  - Moved 31 thesis-facing document/template files from `experiments/harness/` into `/home/zhangpf/参考模版（注意内容无关）/毕业论文资料备份/experiments/harness/`, preserving the original subdirectory layout.
  - Included thesis markdown drafts/outlines, generated DOCX/DOC files, reference templates, translation docs, and harness surface/template text files; left code generators/tests in place.
- Validation: listed the backup tree and confirmed the moved files now exist under the target backup path.
- Next step: if desired, flatten the backup layout from `毕业论文资料备份/experiments/harness/` to a shallower folder structure, or restore selected files back into the worktree.

### 2026-05-12 10:15 CST
- Session goal: Try a pure LLM finalizer for supervisor chat-facing answers.
- Major changes:
  - Replaced the primary final-answer path in `libs/cli/code2workspace_cli/supervisor_runtime.py` with a `final_response` worker node that rewrites existing supervisor/worker results into the user-visible answer.
  - Added finalizer prompt guidance to emphasize successfully obtained information, keep failures brief, preserve strict output constraints, and avoid inventing new facts or success states.
  - Kept the previous candidate-scoring logic as a fallback if the finalizer fails.
- Validation: `uv run --project libs/cli --group test pytest libs/cli/tests/unit_tests/test_supervisor_runtime.py -q` passed (`26 passed`); live CLI smokes returned exact `OK` for `Reply with OK only.` and a natural Chinese greeting for `你好`.
- Next step: rerun medium generic cases to see whether finalizer improves answer completeness without hiding important partial/blocked state.

### 2026-05-12 10:59 CST
- Session goal: Make `/chat` bypass supervisor orchestration without dropping domain skills.
- Major changes:
  - Added `exclude_skill_names` support to `SkillsMiddleware`, then used it in `libs/cli/code2workspace_cli/agent.py` so the plain-chat fallback agent keeps normal skills but filters out orchestration-owned skills.
  - Classified the current project skills and marked `benchmark-workflow-orchestrator` plus `supervisor-guidance` as plain-chat exclusions; repository/domain skills such as `academic-search`, `epietl-api`, `respiratory-disease-*`, `virus-variation-query`, and `data-governance-ops` remain available in `/chat`.
  - Updated agent and middleware unit tests to cover the new two-middleware setup (full skills for supervisor path, filtered skills for plain chat path).
- Validation: `uv run --project libs/cli --group test pytest libs/cli/tests/unit_tests/test_agent.py -q` passed (`89 passed`); `uv run --project libs/cli --group test pytest libs/code2workspace/tests/unit_tests/middleware/test_skills_middleware.py -q` passed (`61 passed`); `uv run --project libs/cli --group test pytest libs/cli/tests/unit_tests/test_supervisor_runtime.py -q` passed (`26 passed`).
- Next step: if needed, promote the exclusion list into skill metadata (for example `supervisor-only`) so future orchestrator skills do not require manual code updates.

### 2026-05-12 11:00 CST
- Session goal: Replace the temporary `/chat` skill exclusion list with a directory-based skills split.
- Major changes:
  - Reorganized project skills under `.code2workspace/skills/capabilities/` and `.code2workspace/skills/orchestration/`, moving domain skills into `capabilities` and supervisor/benchmark assets into `orchestration`.
  - Updated `libs/cli/code2workspace_cli/agent.py` and `libs/cli/code2workspace_cli/skills/load.py` so categorized skill roots expand into different source lists: supervisor sees both folders, while plain chat sees only `capabilities` from categorized roots and still supports legacy flat roots.
  - Repaired migration fallout by updating benchmark helper paths, supervisor guidance asset paths, skill script command paths, harness configs, and project skill tests; fixed relocated helper imports in `benchmark_workflow.py` and `governance_ops.py`.
- Validation: `uv run --project libs/cli --group test pytest libs/cli/tests/unit_tests/test_agent.py libs/cli/tests/unit_tests/skills/test_superagent_project_assets.py libs/code2workspace/tests/unit_tests/middleware/test_skills_middleware.py -q` passed (`154 passed`); `uv run --project libs/cli --group test pytest libs/cli/tests/unit_tests/test_supervisor_runtime.py experiments/harness/tests/test_project_skill_helpers.py -q` passed (`36 passed`).
- Next step: if we want cleaner long-term ergonomics, teach project skill creation commands about the `capabilities` / `orchestration` categories so new skills land in the right subtree by default.
