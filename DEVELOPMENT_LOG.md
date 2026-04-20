# Development Log

This file is the fastest handoff for a new session. Read this before making changes.

## Snapshot

- Last updated: 2026-04-17
- Repository scope: trimmed down to `libs/code2workspace` and `libs/cli`
- Current verified baseline: CLI, simplified web control plane, and the `spades` end-to-end Docker+WDL path are runnable
- Latest local model setup: OpenAI-compatible gateway on `http://127.0.0.1:8080/v1`
- Current batch status: the queue has been resumed from `Flye` after hardening repository-preparation failure handling

## Current repository shape

- `libs/code2workspace`: runtime, middleware, backends, agent graph
- `libs/cli`: terminal UI, non-interactive runner, model/config handling, LangGraph server bridge
- `apps/webapp`: minimal web workspace MVP
- `experiments/oneshot`: generic repo-task runner
- `experiments/harness`: harness-practice scaffolding
- Root files worth reading first:
  - `README.md`
  - `AGENTS.md`
  - `DEVELOPMENT_LOG.md`
  - `PROJECT_ROADMAP.md`
  - `SESSION_BRIEF.md`

## Latest verified setup

- Repo-tracked config file: `.code2workspace/config.toml`
- Repo-tracked env file: `.env`
- User-level runtime config currently symlinked to those repo files:
  - `~/.code2workspace/config.toml -> .code2workspace/config.toml`
  - `~/.code2workspace/.env -> .env`

### Verified command

```bash
uv run --project libs/cli code2workspace -n "Reply with OK only." -q --no-mcp
```

Expected result:

```text
OK
```

## Local OpenAI-compatible gateway notes

The current working local model config is:

```toml
[models]
default = "openai:gpt-5.4"
recent = "openai:gpt-5.4"

[models.providers.openai]
models = ["gpt-5.4"]
api_key_env = "OPENAI_API_KEY"
base_url = "http://127.0.0.1:8080/v1"

[models.providers.openai.params]
reasoning_effort = "xhigh"
use_responses_api = false
```

Important compatibility note:

- `code2workspace` defaults OpenAI models toward the Responses API path
- The local gateway did respond correctly to direct `POST /v1/responses`
- But the full `code2workspace` agent flow failed against that gateway when using Responses API mode
- The working workaround is `use_responses_api = false`, which routes through chat completions compatibility
- `base_url` must include `/v1`

## Known intentional repo state

- `.env` is intentionally tracked in git for now by request during local development
- `.gitignore` was adjusted to allow the root `.env` file to be committed
- This should be cleaned up before public release if secrets or local-only settings should not remain in history

## Recent log

### 2026-04-16

- Verified that the repo root is a normal git repository and currently clean aside from local config additions
- Added repo-tracked local config at `.code2workspace/config.toml`
- Added repo-tracked local key file at `.env`
- Switched user-level runtime config to symlink to repo-tracked files
- Debugged local OpenAI gateway compatibility:
  - initial `base_url = "http://127.0.0.1:8080"` was wrong for `code2workspace`
  - corrected to `http://127.0.0.1:8080/v1`
  - Responses API mode still failed inside the full agent path
  - Chat-completions-compatible mode worked
- Re-verified non-interactive execution end to end with `OK`
- Added planning and handoff docs:
  - `PROJECT_ROADMAP.md`
  - `THESIS_LOG.md`
  - `SESSION_BRIEF.md`
- Added a minimal web workspace MVP under `apps/webapp`:
  - session list
  - create session
  - one-shot task submission
  - run-status polling
  - terminal output panel
- Added a generic one-shot experiment scaffold under `experiments/oneshot`:
  - standardized repo-task prompt generation
  - repo cloning entrypoint
  - run logging
  - run summary output
- Added initial harness-practice directory structure under `experiments/harness`
- Expanded the roadmap so the next round is explicit:
  - web workspace session/run management
  - one-shot batch execution and manifests
  - first real harness surfaces and repo splits
  - one expensive baseline before scaling to all target repos
- Implemented the second-round web workspace iteration:
  - session deletion
  - manual refresh
  - run history in the UI
  - selected-run log inspection instead of latest-run-only inspection
- Turned the one-shot runner into a more stable experiment entrypoint:
  - prompt template now loaded from `experiments/harness/surfaces/one_shot_prompt.txt`
  - per-run `manifest.json` added
  - sequential batch runner added at `experiments/oneshot/run_repo_batch.py`
- Populated the first real harness files:
  - `surfaces/one_shot_prompt.txt`
  - `surfaces/completion_rubric.txt`
  - `configs/repo_splits.toml`
  - `configs/baseline_layout.toml`
- Added and re-ran focused tests for web store/API and oneshot runner helpers:
  - current focused status: `11 passed`
- Started the first real baseline on `spades` and hit real execution-path issues:
  - the initial oneshot runner used `--project libs/cli` relative to the target repo, which would fail on real runs; fixed to use the absolute CLI project path
  - the first `spades` run spent a long time in repository reading / grep / glob steps and never reached Dockerfile, WDL, or `results/` artifact creation before manual interruption
  - the run emitted a noisy Tavily warning even in this no-MCP workflow; local config now suppresses it
  - `agent.log` existed but did not flush incrementally during execution; the runner now flushes each line
  - interrupted runs previously left no `summary.json`; the runner now records `status = "interrupted"` in both summary and manifest
- Updated the one-shot prompt surface after the first `spades` baseline so the agent is pushed toward earlier real execution instead of extended repository-only reading
- Ran a second and third `spades` baseline to isolate the next blockers:
  - second run proved the deeper cause of task impossibility: non-interactive `code2workspace` had no shell/execute tool because shell access is not enabled by default
  - experiment entrypoints now pass `--shell-allow-list all`, and the web runner does the same
  - third run confirmed the fix worked because the agent obtained `execute` and checked Docker/Java/compiler prerequisites on the host
  - after shell access was restored, the next bottleneck became clearer: the agent still spends too long on pre-build convergence before writing `spades_Dockerfile` or starting `docker build`
  - comparative notes for the three `spades` runs were saved to `results/oneshot/spades/BASELINE_NOTES.md`
- Updated the oneshot runner to tolerate longer exploration by default:
  - default per-repo timeout is now 30 minutes
  - both single-run and batch entrypoints accept `--max-runtime-minutes`
  - runs that exceed the limit now end with `status = "timed_out"` in summary and manifest
- Longer `spades` reruns confirmed two more concrete points:
  - simply increasing timeout is not enough if the agent stops early after discovery-only work
  - after tightening the prompt again, the next `spades` run finally wrote `spades_Dockerfile` and launched a real `docker build`
  - the first observed real build failure mode is environmental and external: Ubuntu apt mirror sync inconsistency during package installation inside the Docker build
- Continued the `spades` case all the way through task two by manual workspace continuation after the empty follow-up run:
  - `spades.wdl`, `inputs.json`, and `cromwell.local.conf` were added under `.workspaces/oneshot/spades`
  - first real Cromwell execution proved the workflow was genuinely running in Docker and exposed a task-level mistake: `spades.py` does not allow `--test` together with `-o`
  - after switching the WDL command to explicit repository test FASTQs inside the image, Cromwell completed successfully with workflow status `Succeeded`
  - `results/wdl_file` now contains the actual WDL/input/config used for the successful run, and `results/wdl_result` contains copied workflow outputs plus Cromwell logs/metadata

### 2026-04-17

- Simplified the web control plane toward a more stable baseline:
  - removed the more decorative dashboard-style emphasis from the previous iteration
  - kept the core control-plane functions only: session list, search, run history, log inspection, prompt submission, and basic refresh/status feedback
  - the current frontend direction is intentionally simple and static rather than animated or visually aggressive
- Re-verified the current web UI tests after that simplification:
  - `apps/webapp/tests`: `6 passed`
- Started the first multi-repo batch after the successful `spades` case:
  - `canu` reached a real Docker build and then timed out at 30 minutes
  - `megahit` also reached a real Docker build and then timed out at 30 minutes
  - these are useful baselines because they confirm the runner is now producing real long-running build behavior beyond `spades`
- The batch did not finish normally:
  - `Flye` failed during `git clone` with a transient Git/TLS transport error (`curl 56`, `early EOF`)
  - because clone/setup failure was not isolated as a per-repo outcome, `run_repo_batch.py` aborted before writing `_batch/.../batch_summary.json`
  - this is now the clearest harness-entry reliability gap after the earlier shell-tooling issue was solved
- Current local worktree note:
  - repository-preparation hardening is now wired into the oneshot runners:
    - `run_repo_task.py` retries clone and records `setup_failed` instead of crashing out
    - `run_repo_batch.py` now serializes unexpected per-repo exceptions as `batch_error` results and still writes `batch_summary.json`
  - the tests were updated to the new `ensure_repo(...)` call shape and now cover the new failure paths
  - latest focused test status:
    - `experiments/oneshot/tests`: `9 passed`
    - `apps/webapp/tests`: `6 passed`
  - a new batch has already been restarted from the remaining repositories, beginning with `Flye`
- Shifted the implementation priority away from collecting more raw baseline runs and toward the harness itself:
  - imported reusable OpenClaw skill content into `experiments/harness/skills/openclaw`
  - added `experiments/harness/import_openclaw_skills.py` so the import is reproducible instead of manual
  - started a local harness package at `experiments/harness/code2workspace_harness`
  - the current harness skeleton is explicitly modeled after `/mnt/data1/zhangpf/deepagents/examples/better-harness`
  - current supported commands are:
    - `validate` for harness config loading and surface/case parsing
    - `run-baseline` for driving the existing oneshot runner through a harness variant
  - current focused status for this new area:
    - `experiments/harness/tests`: `4 passed`

## Current difficulties

- Local model gateway compatibility is still partial:
  - direct `/v1/responses` works in isolation
  - the current full agent path still needs chat-completions compatibility
- Web sessions are currently stored in a lightweight SQLite app store, not in the existing CLI/TUI thread model
- The eight target repositories are too expensive to brute-force early
- The repo intentionally tracks a local `.env` file for now, which is useful for development but unsuitable for publication
- The current baseline agent can over-invest in repository understanding before attempting the first real command on heavy scientific repositories such as `spades`
- Non-interactive experiments are impossible for Docker/WDL tasks unless shell tools are explicitly enabled
- Batch experiments can still hit external clone/network errors, but the runner now records them instead of killing the queue immediately

## Current implementation focus

### 1. Web control plane

- keep it static and simple
- preserve deletion, refresh, visible run history, and log inspection
- avoid overbuilding chat UX before one-shot experiments are stable

### 2. One-shot experiment runner

- standardize prompt and manifest layout first
- support batch scheduling from `targets.txt`
- harden batch scheduling so clone/setup failures become explicit per-repo outcomes instead of killing the queue
- only then start expensive real runs

### 3. Harness groundwork

- define concrete editable surfaces before writing any optimization loop
- reuse imported OpenClaw skills as reference material where useful
- keep the harness wired to the existing one-shot runner and artifact layout

## Next useful work

- Keep implementing the actual `code2workspace` pipeline beyond the inherited agent runtime
- Decide whether repo-tracked `.env` should be replaced with `.env.example` before publishing
- If the local gateway later gains full Responses API compatibility for agent/tool flows, re-test `use_responses_api = true`
- Iterate the web workspace from one-shot MVP to richer session management
- Run the generic oneshot runner on the target repositories and collect baseline logs
- Finish hardening the oneshot batch path after the observed `Flye` clone failure
- Turn the stabilized prompt / policy surfaces into explicit harness experiments

## Maintenance rule

- Add a new dated entry when behavior, architecture, or local setup meaningfully changes
- Keep the `Snapshot` section current so a new session can orient in under a minute
