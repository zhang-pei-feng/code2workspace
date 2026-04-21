# Planner Routing Demo

This document shows the current soft-routing behavior for `code2workspace`.

It includes:
- real user inputs
- the planning contract produced by `planning-guide`
- the effective call path inside the codebase
- real non-interactive agent traces with tool calls
- the final user-facing outputs returned by the agent

## Call Path

For all CLI/TUI/Web entrypoints that use `create_cli_agent()`, the current path is:

1. User prompt enters `create_cli_agent()`
   File: [agent.py](/mnt/data1/zhangpf/code2workspace/libs/cli/code2workspace_cli/agent.py)
2. `SkillsMiddleware` loads built-in, user, project, and referenced-project skills
3. `PlannerRoutingMiddleware.before_agent()` reads the latest human task and calls
   [planning_tool.py](/mnt/data1/zhangpf/code2workspace/.code2workspace/skills/planning-guide/scripts/planning_tool.py)
4. `planning_tool.build_plan(task)` returns a soft routing contract
5. `PlannerRoutingMiddleware.wrap_model_call()` injects the recommendation into the system prompt
6. The model still decides what to do; there is no hard dispatch

Relevant implementation files:
- [planning-guide/SKILL.md](/mnt/data1/zhangpf/code2workspace/.code2workspace/skills/planning-guide/SKILL.md)
- [planning_tool.py](/mnt/data1/zhangpf/code2workspace/.code2workspace/skills/planning-guide/scripts/planning_tool.py)
- [planner_routing.py](/mnt/data1/zhangpf/code2workspace/libs/cli/code2workspace_cli/planner_routing.py)
- [agent.py](/mnt/data1/zhangpf/code2workspace/libs/cli/code2workspace_cli/agent.py)
- [project_utils.py](/mnt/data1/zhangpf/code2workspace/libs/cli/code2workspace_cli/project_utils.py)

## Example A: Benchmark Analysis Task

### Raw Input

```text
请分析当前 workspace 里的 benchmark_runs 目录结果，优先按共享数据比较这些工具，不要重跑，只给出简洁结论。
```

### Planning Contract Snapshot

```json
{
  "domain": "benchmark",
  "task_type": "benchmark",
  "recommended_skill": "benchmark-workflow-orchestrator",
  "selected_skill": "benchmark-workflow-orchestrator",
  "fresh_run_required": true,
  "needs_isolated_workspace": true,
  "lanes": [
    {
      "lane_id": "benchmark",
      "title": "Benchmark",
      "purpose": "Run or audit the benchmark path with the benchmark orchestrator skill.",
      "selected_skill": "benchmark-workflow-orchestrator"
    },
    {
      "lane_id": "analysis",
      "title": "Analysis",
      "purpose": "Summarize shared datasets, artifact quality, and blockers for the user.",
      "selected_skill": "benchmark-workflow-orchestrator"
    }
  ]
}
```

### Real Agent Trace

Captured from a real non-interactive run.

```text
Running task non-interactively...
CLI: v0.0.37 | Agent: agent (default) | Model: gpt-5.4 | Thread:
019daf5d-c689-7052-bbd6-a16513ba47ef
Starting LangGraph server...
✓ Server ready
🔧 Calling tool: write_todos
先检查 benchmark skill 指南和当前 workspace 的 benchmark_runs 结构，再按共享输入归并可比结果。
🔧 Calling tool: read_file
🔧 Calling tool: ls
🔧 Calling tool: ls
🔧 Calling tool: glob
🔧 Calling tool: glob
🔧 Calling tool: execute
当前 workspace 看起来是空目录，先确认是否只是 `benchmark_runs` 不在当前目录而是在相邻 workspace。
🔧 Calling tool: ls
🔧 Calling tool: glob
🔧 Calling tool: glob
🔧 Calling tool: write_todos
已定位到同级 workspace 中唯一的 `benchmark_runs`（`20260421113934/benchmark_runs`）；接下来提取每个工具对应输入与成品文件，按共享数据做可比结论。
🔧 Calling tool: ls
🔧 Calling tool: ls
🔧 Calling tool: execute
用现有 summarize 脚本和关键日志/参数文件交叉确认各 run 的输入来源与成品，避免靠目录名猜测。
🔧 Calling tool: execute
🔧 Calling tool: read_file
🔧 Calling tool: read_file
🔧 Calling tool: read_file
🔧 Calling tool: read_file
🔧 Calling tool: read_file
继续核对其余工具的日志，确认哪些确实共用同一批 reads，以及各自是否有可比较的最终产物。
🔧 Calling tool: read_file
🔧 Calling tool: read_file
🔧 Calling tool: read_file
🔧 Calling tool: read_file
汇总各 run 的最终产物与输入来源，并用现有 FASTA/日志直接算出可比指标（不重跑）。
🔧 Calling tool: read_file
🔧 Calling tool: ls
🔧 Calling tool: ls
🔧 Calling tool: execute
再补一轮：读取 Canu 结束段、V-pipe 产物，以及 Trinity 实际输出文件名，完成按共享输入的最终归类。
🔧 Calling tool: read_file
🔧 Calling tool: execute
🔧 Calling tool: read_file
🔧 Calling tool: read_file
🔧 Calling tool: grep
🔧 Calling tool: grep
🔧 Calling tool: grep
🔧 Calling tool: write_todos
```

### Final Output

```text
结论只按“共享输入”比较：

- **短读长、同一批 Illumina PE 数据 `SRR001666_subset_2000000_R1/R2.fastq.gz`**：`SPAdes` 最好，`scaffolds.fasta` 190 条、总长 4.546 Mb、N50 **63.1 kb**、最大 173.9 kb，且仅 **39.8s**；`MEGAHIT` 更快（**18.8s**）但更碎，858 条、N50 **9.9 kb**。`Trinity` 也成功但这是转录组装，不适合和前两者做基因组优先比较，产物 82 条/131 kb。
- **长读、同一批 PacBio 数据**：`Flye` 和 `Canu` 都装成单条 contig；`Flye` 更快（**8:03** vs **41:16**），总长 **4.643 Mb**；`Canu` 总长 **4.665 Mb** 也完整，但耗时明显更高。若只看现有结果，长读场景优先 `Flye`。
- **SARS-CoV-2 共识流程**：`fieldbioinformatics` 成功输出 29,903 bp 共识，**12s**；`v-pipe` 也成功输出 29,903 bp 共识，**22.4s**。但二者**不是同一输入**（前者用 `MT007544.fastq` ONT，后者用 `pos_MN908947_3_1` Illumina），只能说都能出完整共识，不能直接判高下。`covid-19-signal` 与 `v-pipe-srr10903401` 失败，不纳入比较。
```

### Observed Behavior

- The planner clearly recognized this as a benchmark task.
- The agent did not explicitly print “I am now using benchmark-workflow-orchestrator”.
- But the recommendation clearly biased it toward benchmark-style behavior:
  - benchmark scope narrowing
  - shared-input comparison
  - artifact-first evidence collection
  - `execute` used only for metrics extraction, not for re-running work

## Example B: Paper2Workspace-Like Task

### Raw Input

```text
把一个 xxx.github 仓库变成有工作流的工作空间
```

### Planning Contract Snapshot

```json
{
  "domain": "paper2workspace",
  "task_type": "paper2workspace",
  "recommended_skill": "paper2workspace-orchestrator",
  "selected_skill": "paper2workspace-orchestrator",
  "fresh_run_required": true,
  "needs_isolated_workspace": true,
  "lanes": [
    {
      "lane_id": "workspace",
      "title": "Workspace",
      "purpose": "Build a runnable workspace and workflow path for the repository.",
      "selected_skill": "paper2workspace-orchestrator"
    },
    {
      "lane_id": "analysis",
      "title": "Analysis",
      "purpose": "Report workspace status, artifacts, and remaining blockers.",
      "selected_skill": "paper2workspace-orchestrator"
    }
  ]
}
```

### Real Agent Output

This demo prompt intentionally asked the agent to explain the route rather than execute it.

```text
我会按两阶段做，但现在只说明方案、不执行：

1. 先审仓库：确认它是静态站点、脚本项目还是分析/流程仓库，读 `README`、依赖文件、入口脚本、示例数据、现有 CI，整理“怎么安装、怎么运行、怎么验证”。
2. 再建工作空间：补齐可复现环境（通常是 Dockerfile/运行脚本/环境变量约定），把仓库封装成标准 workspace，并明确输入、输出、启动命令、验证命令。
3. 抽取工作流：把仓库里的核心步骤拆成 workflow DAG（如准备输入 → 执行主程序 → 收集结果 → 校验输出）；如果仓库本身没有 workflow，就按其实际执行顺序生成一个可跑的工作流定义。
4. 最后验证交付：本应再做镜像构建、冒烟测试、一次真实运行，确认 workspace 和 workflow 都能复现；你现在要求“不真正执行”，所以我会停在方案设计和待执行清单这一步。
```

### Observed Behavior

- The planner clearly recognized this as a paper2workspace task.
- The answer naturally adopted a two-phase repo-to-workspace framing.
- This is exactly the intended soft-routing effect: not forced dispatch, but a strong push toward the orchestrator’s mental model.

## Example C: Simple Q&A Task

### Raw Input

```text
当前项目的 .code2workspace/skills 目录下有哪些 project skills？请用一句话回答。
```

### Planning Contract Snapshot

```json
{
  "domain": "generic",
  "task_type": "general",
  "recommended_skill": null,
  "selected_skill": null,
  "fresh_run_required": false,
  "needs_isolated_workspace": false
}
```

### Real Agent Trace

```text
Running task non-interactively...
CLI: v0.0.37 | Agent: agent (default) | Model: gpt-5.4 | Thread:
019daf5b-16e3-7900-936b-abff704082a3
Starting LangGraph server...
✓ Server ready
🔧 Calling tool: ls
当前项目 `.code2workspace/skills` 下的 project skills 有：academic-search、benchmark-workflow-orchestrator、data-governance-ops、deep-research-report、epidemic-warning-report、epietl-api、paper2workspace-orchestrator、planning-guide、respiratory-disease-data-fetcher、respiratory-disease-wide-monitor、virus-variation-query。
✓ Task completed
```

### Observed Behavior

- No orchestrator skill recommendation was injected.
- The agent stayed on the general path.
- The tool usage was minimal: one `ls`, one sentence answer.

## Example D: Mixed Task Classification

### Raw Input

```text
先把一个 xxx.github 仓库变成有工作流的工作空间，再对 benchmark 结果做分析汇总
```

### Planning Contract Snapshot

```json
{
  "domain": "multi-lane",
  "task_type": "multi-lane",
  "recommended_skill": null,
  "selected_skill": null,
  "fresh_run_required": true,
  "needs_isolated_workspace": true,
  "lanes": [
    {
      "lane_id": "workspace",
      "title": "Workspace",
      "selected_skill": "paper2workspace-orchestrator",
      "goal": "Turn the repository into a runnable workflow workspace."
    },
    {
      "lane_id": "benchmark",
      "title": "Benchmark",
      "selected_skill": "benchmark-workflow-orchestrator",
      "goal": "Benchmark multiple tools and compare real results."
    }
  ]
}
```

### Observed Behavior

- The planner does not force one orchestrator for the whole task.
- It emits two suggested lanes:
  - workspace lane
  - benchmark lane
- This is the current soft-routing answer to “multiple independent requirements”.

## Example E: Additional Classifier Outputs

### Complex Diagnosis Prompt

Input:

```text
为什么 fresh-run benchmark 会跑出新产物但有时没有自动生成最终总结？请给出根因链和证据文件。
```

Current classification:

```json
{
  "domain": "benchmark",
  "task_type": "benchmark",
  "recommended_skill": "benchmark-workflow-orchestrator",
  "selected_skill": "benchmark-workflow-orchestrator"
}
```

### Report Prompt

Input:

```text
根据 docs/overview/current-status.md 和 docs/research/thesis-log.md 写一份三段式项目进展报告。
```

Current classification:

```json
{
  "domain": "generic",
  "task_type": "general",
  "recommended_skill": null,
  "selected_skill": null
}
```

## What This Demo Shows

- The planner now produces a structured recommendation contract instead of pure generic planning.
- The router is soft:
  - benchmark tasks get benchmark guidance
  - paper2workspace tasks get paper2workspace guidance
  - simple questions stay general
  - mixed tasks become multi-lane
- The agent still makes the final decision.
- Isolated copies can keep project skills visible through `.code2workspace/project-root.txt`, which is why the benchmark analysis demo above can still see project orchestrator skills without copying historical `results/`.
