# Supervisor Agent 功能流程图说明

本文面向毕业设计说明，解释 `code2workspace` 目录下当前智能体的主要功能、执行流程、技术分工、产物设计、算子库与 benchmark 比对历史库设计，以及不同任务的评估指标。除功能关键词和代码名保持英文外，其余尽量用中文说明。

## 目录

1. [总体架构](#总体架构)
2. [Agent 与 Worker 设计](#agent-与-worker-设计)
3. [任务分类与路由](#任务分类与路由)
4. [通用任务 generic](#通用任务-generic)
5. [仓库转工作空间 github2workspace](#仓库转工作空间-github2workspace)
6. [基准测试 benchmark](#基准测试-benchmark)
7. [报告生成 report](#报告生成-report)
8. [节点执行机制](#节点执行机制)
9. [能力束与 Skill guidance](#能力束与-skill-guidance)
10. [产物与 Benchmark 比对历史库](#产物与-benchmark-比对历史库)
11. [算子库 operator_store](#算子库-operator_store)
12. [Benchmark 比对历史库 benchmark_comparison_history_store](#benchmark-比对历史库-benchmark_comparison_history_store)
13. [评估指标与完成度判断](#评估指标与完成度判断)
14. [入口文件速查](#入口文件速查)

## 总体架构

当前默认 CLI 智能体不是直接把用户问题交给单个 chat agent，而是先进入 `Supervisor Graph Runtime`。它先判断任务类型，再生成一轮或多轮 `TaskGraph`，每个节点由确定性代码、helper 脚本、worker agent 或最终 LLM 汇总器执行。

```mermaid
flowchart TD
    U[用户请求] --> E[CLI / TUI / non-interactive]
    E --> C[create_cli_agent]
    C --> B[base_agent<br/>普通工作空间 agent]
    C --> W[worker_agent<br/>节点执行 agent]
    C --> S[Supervisor wrapper graph]

    S --> R{route}
    R -->|有用户任务| CL[classify_task_with_model]
    R -->|fallback mode 或空任务| FB[fallback_agent]

    CL --> P[HeuristicSupervisorPlanner<br/>代码规划图]
    P --> G[TaskGraph<br/>nodes + edges]
    G --> X[execute_graph_round<br/>依赖感知调度]

    X --> A{节点类型}
    A -->|deterministic adapter| H[helper / 本地代码]
    A -->|普通节点| WA[worker agent + tools]
    A -->|final_response| FR[LLM 最终回答编辑]

    H --> O[WorkerResult]
    WA --> O
    FR --> O
    O --> D[decision_check + SupervisorDecision]
    D -->|replan| P
    D -->|stop| F[final_summary.md<br/>final_response.md<br/>evaluation.json]
```

核心分工：

| 层次 | 由谁执行 | 主要作用 |
| --- | --- | --- |
| `route` | LangGraph 代码节点 | 决定进入 `supervise` 还是 `fallback` |
| `classify_task_with_model` | LLM + 规则兜底 | 识别 `generic`、`github2workspace`、`benchmark`、`report` |
| `HeuristicSupervisorPlanner` | Python 代码 | 生成每轮 `TaskGraph` |
| `execute_graph_round` | Python 代码 | 按 `edges` 做依赖调度，可并行执行 ready 节点 |
| `SupervisorWorkerRunner` | Python 代码 | 先尝试确定性 adapter，再调用 worker agent |
| worker 节点 | agent + tools | 执行仓库检查、构建、写文件、搜索、总结等 |
| helper | Python 脚本 | 对 `benchmark` 的注册、准备、执行做可复现处理 |
| `final_response` | LLM | 从已有证据中写最终给用户看的回答，不新增事实 |

## Agent 与 Worker 设计

当前系统里有几类容易混淆的 agent。它们都由 `create_cli_agent()` 组装，但职责不同。

```mermaid
flowchart TD
    C[create_cli_agent] --> M[解析 model / project_context / cwd]
    M --> MW[组装 CLI middleware stack]
    MW --> BA[base_agent<br/>正常 workspace agent]
    MW --> WK[supervisor_worker_agent<br/>Supervisor 节点默认 worker]
    MW --> FB[fallback_agent<br/>普通聊天/ fallback]
    MW --> RW[report_worker_agents<br/>按 report 节点模型覆盖]

    C --> CM[classifier_model<br/>resolve_model(model)]
    BA --> SG[build_supervisor_enabled_agent]
    WK --> SG
    FB --> SG
    RW --> SG
    CM --> SG

    SG --> OUT[最终 CLI agent graph]
```

### agent 类型

| 名称 | 由谁创建 | 作用 | 是否直接面向用户 |
| --- | --- | --- | --- |
| `base_agent` | `_build_workspace_agent()` | 原始工作空间 agent，也是某些兜底执行路径的基础能力 | 否，包在 supervisor 后面 |
| `supervisor_worker_agent` | `_build_workspace_agent()` 的第二个实例 | supervisor 普通节点默认执行器，即文档里的 `worker_agent` | 否，只执行节点 |
| `fallback_agent` | 去掉 orchestration skill 后的 `_build_workspace_agent()` | 当 route 进入 fallback 时做普通聊天 | 是，fallback 时直接输出 |
| `report_worker_agents` | `_build_workspace_agent(model_override=...)` | 给 report 的特定节点换模型，例如 `monitoring_lane`、`compose_report` | 否，只执行 report 节点 |
| `classifier_model` | `resolve_model(model)` | 只做任务族分类，输出 JSON | 否 |

这里的 `worker_agent` 不是单独手写的一套 agent，而是“同样工具能力 + 同样系统提示 + 同样 middleware”的 workspace agent 副本。这样设计的原因是：supervisor 外层负责拆图和调度，worker 内层仍然可以使用文件、shell、skills、subagents、summary 等完整工具能力。

### workspace agent 的 middleware 栈

`create_cli_agent()` 先准备 CLI 层 middleware，然后调用 `create_workspace_agent()`。最终 worker 可见的核心能力来自下面两层。

```mermaid
flowchart TD
    CLI[CLI middleware] --> CWM[create_workspace_agent]
    CWM --> Base[基础 middleware]
    Base --> Tool[工具面]
    Tool --> Agent[LangChain create_agent]

    subgraph CLI 层
        CM[ConfigurableModelMiddleware]
        TS[TokenStateMiddleware]
        AU[AskUserMiddleware 可选]
        MM[MemoryMiddleware 可选]
        SK[SkillsMiddleware 可选]
        LC[LocalContextMiddleware]
        SA[ShellAllowListMiddleware 可选]
        SM[Summarization tool middleware]
    end

    subgraph Workspace Agent 基础层
        TODO[TodoListMiddleware]
        FSW[FilesystemMiddleware]
        SUB[SubAgentMiddleware]
        SUM[SummarizationMiddleware]
        PATCH[PatchToolCallsMiddleware]
        ASYNC[AsyncSubAgentMiddleware 可选]
        HITL[HumanInTheLoopMiddleware 可选]
        PERM[_PermissionMiddleware 可选且最后]
    end
```

关键能力：

| middleware | 作用 |
| --- | --- |
| `ConfigurableModelMiddleware` | 支持运行时模型配置 |
| `TokenStateMiddleware` | 记录 token 状态，便于 checkpoint |
| `AskUserMiddleware` | 交互模式下可向用户提问 |
| `MemoryMiddleware` | 读取用户/项目 `AGENTS.md` 记忆 |
| `SkillsMiddleware` | 加载 built-in、用户、项目 skill |
| `LocalContextMiddleware` | 注入本地 git、目录、MCP 等上下文 |
| `FilesystemMiddleware` | 提供 `ls`、`read_file`、`write_file`、`edit_file`、`glob`、`grep`、`execute` |
| `SubAgentMiddleware` | 提供 `task` 工具，允许 worker 再委托短生命周期 subagent |
| `SummarizationMiddleware` | 处理长上下文和总结 |
| `PatchToolCallsMiddleware` | 修正工具调用形态 |
| `HumanInTheLoopMiddleware` | 根据配置暂停危险工具调用 |
| `_PermissionMiddleware` | 最后检查文件权限 |

### worker_agent 节点执行选择

`SupervisorWorkerRunner` 不会所有节点都交给 LLM。它按顺序尝试多种执行器。

```mermaid
flowchart TD
    N[TaskNode] --> P[maybe_prepare_worker_inputs<br/>代码预处理]
    P -->|命中| WR1[WorkerResult]
    P -->|未命中| AR[maybe_run_agentic_benchmark_register<br/>LLM 选择算子]
    AR -->|命中| WR2[WorkerResult]
    AR -->|未命中| REP[maybe_run_agentic_benchmark_case_repair<br/>LLM 修复 case]
    REP --> DET[maybe_run_deterministic_worker<br/>helper / Python]
    DET -->|命中| WR3[WorkerResult]
    DET -->|未命中| SEL[select_runnable]
    SEL -->|report 专用节点| RWA[report_worker_agent]
    SEL -->|普通节点| SWA[supervisor_worker_agent]
    RWA --> INV[invoke_worker_runnable]
    SWA --> INV
    INV --> WR4[WorkerResult]
```

执行优先级：

1. `github2workspace inspect` 的仓库 materialization 由代码先做。
2. `github2workspace wdl` 可复用已有 smoke 证据，但只能返回 `partial`，不能假装主 workflow 完成。
3. `benchmark register` 可以先让 LLM 在候选算子中选工具，再交给确定性 helper 落地。
4. `benchmark case` 和 `summarize` 优先走确定性 helper。
5. 其他节点才进入 `worker_agent`。

### report 专用 worker 模型

`report` 任务可以给不同节点配不同模型。默认模型是 `openai_paid:gpt-5.4`，不可用时尝试兼容 fallback `openai:gpt-5.4`。

| report 节点 | 环境变量 |
| --- | --- |
| 全局 report worker | `CODE2WORKSPACE_SUPERVISOR_REPORT_MODEL` |
| `init_report` | `CODE2WORKSPACE_SUPERVISOR_REPORT_INIT_MODEL` |
| `monitoring_lane` | `CODE2WORKSPACE_SUPERVISOR_REPORT_MONITORING_MODEL` |
| `local_data_lane` | `CODE2WORKSPACE_SUPERVISOR_REPORT_LOCAL_DATA_MODEL` |
| `literature_lane` | `CODE2WORKSPACE_SUPERVISOR_REPORT_LITERATURE_MODEL` |
| `compose_report` | `CODE2WORKSPACE_SUPERVISOR_REPORT_COMPOSE_MODEL` |
| `summarize` | `CODE2WORKSPACE_SUPERVISOR_REPORT_SUMMARIZE_MODEL` |
| `final_response` | `CODE2WORKSPACE_SUPERVISOR_REPORT_FINAL_RESPONSE_MODEL` |

`SupervisorWorkerSubagent` 只是一个轻量映射：

- `name`：例如 `report:compose_report`。
- `runnable`：对应模型构建出的 workspace agent。
- `node_ids`：这个 runnable 负责的节点集合，例如 `compose_report` 和 `retry_compose_report`。

`SupervisorWorkerRunner._select_runnable()` 会先看节点是否匹配 report 专用 worker；匹配则用专用 runnable，否则用默认 `supervisor_worker_agent`。

### worker prompt 设计

每个 `TaskNode` 进入 `worker_agent` 前，会被 `_build_worker_prompt()` 包装成严格的节点执行提示。这个 prompt 的核心目标是让 worker 只完成当前节点，而不是重新规划整个任务。

```mermaid
flowchart TD
    N[TaskNode] --> C[capability_bundles]
    N --> M[metadata<br/>task/run_dir/prior outputs]
    N --> G[node_guidance + family_guidance]
    N --> T[时间锚点<br/>UTC/local time]
    C --> P[worker prompt]
    M --> P
    G --> P
    T --> P
    P --> A[worker_agent.astream]
    A --> JSON[返回 WorkerResult JSON]
```

prompt 中会注入：

- `Workspace root`
- 当前 UTC 时间和本地时间，用于 latest/recent 任务。
- `Node ID`、`Objective`、原始用户任务。
- `Run directory`。
- 之前节点的 `worker_outputs`、`node_traces` 和简化 payload。
- `capability_bundles` 的说明、实现类型和偏好工具。
- 节点级 guidance，例如 `register`、`wdl`、`compose_report`。
- family guidance，例如 `benchmark_family`、`github2workspace_pipeline`。
- 对 `final_response` 节点，额外注入 final summary 和决策信息。
- 对 `report local_data_lane`，额外注入 `benchmark_comparison_history_store` 候选比对历史记录。

worker 必须返回 JSON：

```json
{
  "status": "completed",
  "summary": "节点完成内容",
  "artifacts": ["文件路径"],
  "evidence": ["证据说明或路径"],
  "next_action_hint": null,
  "failure_reason": null,
  "spawned_subgraph": null
}
```

如果 worker 没有返回 JSON，解析器会把文本包装成 `completed`，但这类结果在关键节点会被 `decision_check` 拦住。例如 `init_generic` 没有 `spawned_subgraph.nodes`，就不能进入下一轮执行。

### subagent 机制

worker agent 自己还可以通过 `task` 工具调用 subagent。subagent 定义来自：

```txt
.code2workspace/agents/<agent_name>/AGENTS.md
~/.code2workspace/<assistant_id>/agents/<agent_name>/AGENTS.md
```

每个 subagent 文件使用 YAML frontmatter：

```md
---
name: researcher
description: Research topics on the web before writing content
model: openai:gpt-5.4
allow_nested_task: true
nested_task_budget: 1
max_delegation_depth: 3
---

这里写 subagent 的 system_prompt。
```

`SubAgentMiddleware` 会把它们暴露成一个 `task(description, subagent_type)` 工具。调用时：

1. 父 agent 给出详细 `description` 和 `subagent_type`。
2. middleware 创建只包含这次任务的新 state，避免把父 agent 全部上下文泄漏给子 agent。
3. 子 agent 独立运行，最后只把最后一条消息作为 `ToolMessage` 返回。
4. 对 report lane，可以允许有限 nested subagent，但受 `nested_task_budget`、`max_delegation_depth`、`nested_scope_guard` 限制。

这意味着系统里有两种“worker”：

- supervisor 层的 `worker_agent`：执行 `TaskGraph` 节点。
- workspace agent 内部的 subagent：由 worker 通过 `task` 工具临时调用，用于隔离复杂子任务。

## 任务分类与路由

任务分类有两层：先用规则识别明显信号，再尝试用 LLM 分类；当 LLM 输出无效、低置信度或不可用时回退到规则结果。

```mermaid
flowchart TD
    T[用户任务文本] --> Rule[classify_task<br/>规则匹配]
    Rule --> LLM{classifier_model 可用?}
    LLM -->|否| RF[使用 rules_fallback]
    LLM -->|是| Ask[LLM 返回 JSON<br/>task_type/confidence/reason]
    Ask --> V{输出有效且 confidence >= 0.55?}
    V -->|否| RF
    V -->|是| LR[使用 llm_classifier]
    RF --> Out[TaskClassification]
    LR --> Out
    Out --> P[选择 graph family]
```

分类结果：

| `task_type` | 触发场景 | 后续图 |
| --- | --- | --- |
| `generic` | 普通问答、代码修复、数据分析、判断类问题 | 动态规划或通用执行图 |
| `github2workspace` | 把 GitHub 仓库转成可运行 workspace、Docker、WDL 验证 | `inspect -> build -> wdl -> summarize` |
| `benchmark` | 多工具或多 workflow 在共享数据集上比较指标 | `register -> parallel tool cases -> summarize` |
| `report` | 正式报告、风险评估、监测简报、证据综述 | `init_report -> evidence lanes -> compose_report -> summarize` |

特别规则：如果用户说“先给我口头判断”“不要正式写作”“直接回答”，即使内容像报告，也优先走 `generic`，避免误生成正式报告。

## 通用任务 generic

`generic` 是默认能力，用来处理普通问答、代码修复、仓库分析、方案比较、判断类任务。它的第一轮通常由 `init_generic` 让 worker agent 设计下一轮子图。

```mermaid
flowchart TD
    G0[generic 请求] --> G1[init_generic<br/>agent 规划下一轮图]
    G1 --> C{spawned_subgraph 可用?}
    C -->|是| DG[动态 TaskGraph<br/>agent 给出 nodes/edges]
    C -->|否| FG[fallback 图<br/>compose_generic -> summarize]
    DG --> R[execute_graph_round]
    FG --> R
    R --> D{SupervisorDecision}
    D -->|未解决且未达 max_rounds| Retry[retry_失败节点 -> compose_generic -> summarize]
    D -->|完成或停止| F[final_response]
```

`init_generic` 的关键技术点：

- 由 worker agent 执行，不直接给最终答案。
- 要返回 JSON，其中 `spawned_subgraph.nodes` 是下一轮节点列表。
- 每个节点需要 `node_id`、`title`、`objective`、`capability_bundles`。
- 代码会清洗节点名、能力束和边，防止非法节点进入调度。
- 如果没有可用子图，会退化为 `compose_generic -> summarize`。

典型节点设计：

| 节点 | 谁执行 | 作用 |
| --- | --- | --- |
| `init_generic` | worker agent | 分析任务并规划下一轮子图 |
| `worker_context` | worker agent | 查约束、证据、仓库事实或上下文 |
| `worker_solution` | worker agent | 做实现、修复、方案或结论 |
| `compose_generic` | worker agent / LLM | 合并 worker 输出为正常用户答案 |
| `summarize` | worker agent / LLM | 记录结果、阻塞点、下一步建议 |
| `final_response` | LLM | 编辑成最终聊天回答 |

## 仓库转工作空间 github2workspace

`github2workspace` 面向“把 GitHub 仓库变成可运行工作空间”的任务，重点验证 Docker 与 WDL，而不是只写说明。

```mermaid
flowchart TD
    H0[github2workspace 请求] --> M[repo materialization preflight<br/>代码预处理]
    M --> H1[inspect<br/>agent 检查仓库]
    H1 --> H2[build<br/>agent/工具构建 Docker]
    H2 --> H3[wdl<br/>agent 写/修 WDL 并运行 miniwdl]
    H3 --> H4[summarize]
    H4 --> D{decision}
    D -->|inspect 失败| R1[retry_inspect -> build -> wdl -> summarize]
    D -->|build 失败| R2[retry_build -> wdl -> summarize]
    D -->|wdl 失败或 partial| R3[retry_wdl -> summarize]
    D -->|停止| F[final_response + evaluation.json]
```

`repo materialization preflight` 由代码执行，顺序为：

1. 如果 workspace 已有目标 git 仓库，直接复用。
2. 查找本地 `code_repository` 缓存并复制。
3. 执行普通 `git clone`。
4. 执行 `git clone --depth 1`。
5. 查找本地同名仓库并 `git clone --local`。
6. 都失败则返回 `repo_materialization_failed`，这会作为实验结果记录，而不是让批处理崩溃。

节点完成标准更严格：

| 阶段 | 关键证据 | 说明 |
| --- | --- | --- |
| `inspect` | 仓库结构、入口脚本、依赖、数据需求 | 给 `build` 和 `wdl` 提供下游前提 |
| `build` | Dockerfile、镜像构建日志、最小容器验证 | 优先官方镜像，其次薄包装镜像，最后从零构建 |
| `wdl` | 主功能 WDL、`outputs.json`、`workflow.log` | 只通过 `miniwdl check` 不算完成 |
| `summarize` | 已验证状态和阻塞点 | 不能把 smoke 成功夸大成主 workflow 成功 |

`decision_check` 会阻止虚假完成：如果 `wdl` 声称 `completed`，但没有主功能 `miniwdl` 成功运行证据，代码会生成 `check_wdl` 并要求停止或重试。

## 基准测试 benchmark

`benchmark` 用于多个算子或工具在共享输入上比较指标。这里的关键不是让 LLM 自由发挥，而是把注册、准备、执行、汇总拆成可追溯阶段。

```mermaid
flowchart TD
    B0[benchmark 请求] --> B1[register<br/>选择工具/数据集/准备 case]
    B1 --> Sel{selected_tools?}
    Sel -->|无| Stop[记录 missing_benchmark_assets 或 missing_selected_tools]
    Sel -->|有| B2[fan-out 并行执行]
    B2 --> T1[tool A case<br/>deterministic helper / agent repair]
    B2 --> T2[tool B case<br/>deterministic helper / agent repair]
    B2 --> TN[tool N case<br/>deterministic helper / agent repair]
    T1 --> B3[summarize<br/>聚合指标和阻塞]
    T2 --> B3
    TN --> B3
    B3 --> D{decision}
    D -->|失败工具| R[retry_tool -> summarize]
    D -->|完成或达上限| F[final_response + evaluation.json]
```

`register` 的实现分三层：

| 层 | 谁执行 | 作用 |
| --- | --- | --- |
| `operator_store` 检索 | 代码 + SQLite | 根据任务、输入输出类型、tag、全文或 embedding 召回候选算子 |
| LLM 选择 | worker agent | 在候选集中选择最合适的工具子集，输出 JSON |
| deterministic helper | Python 脚本 | 初始化 benchmark 目录、解析数据集、准备 case、生成执行契约 |

`register` 最少要产出：

- `operator_selection.json`：选择策略、候选和最终工具。
- `benchmark_plan.json/md`：本次基准测试计划。
- `dataset_resolution.json/md`：共享数据集和输入解析结果。
- `metric_plan.json/md`：要计算的指标。
- `cases/<tool>/manifest.json`：每个工具的 case 描述。
- `cases/<tool>/execution_ready.json`：是否具备 runtime image、WDL、inputs。
- `spawned_subgraph.selected_tools`：下一轮并行节点的机器可读工具列表。

执行节点会优先使用 `.code2workspace/skills/orchestration/benchmark-workflow-orchestrator/scripts/benchmark_workflow.py`，例如 `run-repo-native` 或 WDL 运行路径。只有在需要修复 case 时，才让 agent 做受限修复。

## 报告生成 report

`report` 面向正式报告、风险评估、监测简报等证据型交付。它把证据分成多条 lane，最后由 `compose_report` 合成。

```mermaid
flowchart TD
    R0[report 请求] --> R1[init_report<br/>agent 建立报告契约]
    R1 --> R2[monitoring_lane<br/>官方监测/运行态势]
    R1 --> R3[local_data_lane<br/>本地数据/计算历史]
    R1 --> R4[literature_lane<br/>文献/技术网页]
    R2 --> R5[compose_report<br/>合成正式报告]
    R3 --> R5
    R4 --> R5
    R5 --> R6[summarize]
    R6 --> D{decision}
    D -->|lane 超时/partial| Retry[retry lane -> compose_report]
    D -->|完成或停止| F[final_response<br/>保留报告结构]
```

报告链路的技术约束：

- `init_report` 只做报告契约和目录脚手架，不做大规模研究。
- 三条 evidence lane 可并行执行。
- report 节点有默认超时 `20min`，超时记录为 `partial + worker_timeout`，后续仍可基于已有证据合成。
- `local_data_lane` 会注入 `benchmark_comparison_history_store` 候选历史记录，把本地 benchmark 比对计算历史当作结构化证据。
- `compose_report` 必须区分直接证据、推断证据和不确定性。
- `final_response` 对 report 不压缩成短摘要，而是尽量保留正式 Markdown 报告结构。

默认报告结构包括：标题、执行摘要、范围与时间窗口、关键发现、证据分析、不确定性与局限、建议或下一步、来源与证据附录。

## 节点执行机制

每轮图执行由 `execute_graph_round` 完成，它按边关系找 ready 节点，并用 `asyncio.gather` 并行执行。

```mermaid
flowchart TD
    G[TaskGraph] --> P[pending nodes]
    P --> R{找 ready nodes}
    R -->|依赖 completed/partial| Run[并行运行 ready nodes]
    R -->|依赖 failed/blocked| Block[标记 blocked_by_failed_dependency]
    R -->|依赖链无法解析| U[blocked_by_unresolved_dependency]
    Run --> WR[WorkerResult]
    WR --> Check{decision_check?}
    Check -->|通过| Next[更新 final_status]
    Check -->|要求 finalize| Skip[跳过剩余节点]
    Next --> P
    Skip --> End[TaskExecutionRound]
```

`WorkerResult` 是所有节点统一返回格式：

```json
{
  "status": "completed | blocked | failed | partial",
  "summary": "节点摘要",
  "artifacts": ["产物路径"],
  "evidence": ["证据路径或证据说明"],
  "next_action_hint": "下一步提示",
  "failure_reason": "失败原因",
  "spawned_subgraph": {}
}
```

节点执行包装 `_run_worker_and_capture` 会额外做：

- 写 `node_started`、`node_heartbeat`、`node_finished` 到 `tool_activity.jsonl`。
- 把 worker 真实工具调用暴露为 `worker_tool_call` / `worker_tool_result`。
- 对 report 节点设置超时。
- 把结果写入 `worker_outputs/<node>.json` 和 `node_traces/<node>.json`。
- 向 TUI / stream 发送 supervisor event，便于界面显示长任务进度。

## 能力束与 Skill guidance

每个 `TaskNode` 不是只写自然语言目标，还带 `capability_bundles`。能力束告诉 worker 这一节点允许或偏好的工具面。

| `capability_bundle` | 实现类型 | 典型工具 | 用途 |
| --- | --- | --- | --- |
| `repo_fetch` | hybrid | `execute`, `read_file`, `ls`, `glob` | 拉取和检查仓库 |
| `docker_build_run` | hybrid | `execute`, `write_file`, `edit_file` | Docker 构建与运行 |
| `wdl_run` | hybrid | `execute`, `write_file`, `edit_file` | WDL/Cromwell/miniwdl |
| `operator_filter` | guidance | `read_file`, `execute` | 算子筛选 |
| `metric_compute` | hybrid | `execute`, `read_file`, `write_file` | 指标计算 |
| `summarize` | guidance | `read_file`, `write_file` | 汇总和最终表达 |
| `web_search` | tool | `web_search` | 搜索证据 |
| `web_fetch` | tool | `fetch_url` | 抓取网页 |
| `db_access` | hybrid | `execute`, `read_file` | 访问本地数据库 |
| `api_call` | hybrid | `fetch_url`, `execute` | 调 API |

`Skill guidance` 存放在 `.code2workspace/skills/orchestration/supervisor-guidance/`。代码会按 family 和 node 加载提示片段，例如：

- `families/github2workspace_pipeline.md`
- `families/benchmark_family.md`
- `families/report_synthesis.md`
- `nodes/register.md`
- `nodes/benchmark_case.md`
- `nodes/wdl.md`
- `nodes/compose_report.md`

这样做的好处是：稳定的调度逻辑留在 Python，经验型执行策略放到 Skill 文档，便于迭代和论文追踪。

## 产物与 Benchmark 比对历史库

每次 supervisor 运行都会写入：

```txt
<workspace>/orchestration_runs/<run_id>/
├── request.json
├── task_classification.json
├── retrieved_cases.json
├── graph_round_1.json
├── graph_round_2.json
├── node_traces/
├── worker_outputs/
├── tool_activity.jsonl
├── final_summary.md
├── final_response.md
├── final_decision.json
└── evaluation.json
```

这些文件是 canonical evidence，也就是最可靠的可追溯来源。SQLite 索引只是可重建缓存。

```mermaid
flowchart TD
    Run[orchestration run] --> Art[run artifacts]
    Art --> CaseIdx[SQLiteCaseIndex<br/>从历史 run 重建]
    CaseIdx --> Retrieve[retrieved_cases.json]
    Retrieve --> Planner[planner 参考历史经验]

    Art --> Eval[evaluation.json]
    Art --> Op[operator_store<br/>可复用算子]
    Art --> Hist[benchmark_comparison_history_store<br/>benchmark 比对历史记录]
```

`SQLiteCaseIndex` 会从历史 `orchestration_runs` 中读取 `request.json`、`final_decision.json`、`final_summary.md`，把类似任务摘要索引起来。新任务规划前会检索最多 3 条相似历史案例。

## 算子库 operator_store

`operator_store` 用于管理可复用算子。当前设计是 manifest-first：文件是主记录，SQLite 是查询层。

```mermaid
flowchart TD
    P[benchmark/github2workspace 产物] --> M[operator_product.json<br/>run-level manifest]
    M --> N[normalize manifest]
    N --> O[operators/&lt;operator_id&gt;/operator.json<br/>稳定算子记录]
    N --> V[versions/&lt;version&gt;.json<br/>版本记录]
    N --> R[validations/&lt;run_id&gt;.json<br/>验证记录]
    O --> I[index.sqlite]
    V --> I
    R --> I
    O --> Emb[embedding.json<br/>可选向量]
    Emb --> I
    I --> Search[search_operators]
```

目录结构：

```txt
operator_store/
├── objects/
│   └── <family>/<name>/<version>/operator_product.json
├── operators/
│   └── <operator_id>/
│       ├── operator.json
│       ├── embedding.json
│       ├── versions/<version>.json
│       └── validations/<run_id>.json
└── index.sqlite
```

`operator.json` 记录“这个算子是什么”，包括：

- `operator_id`
- `family`
- `name`
- `version`
- `summary`
- `description`
- `source_repo`
- `inputs`
- `outputs`
- `runtime`
- `metrics`
- `tags`
- `canonical_text`

`validations/<run_id>.json` 记录“这次跑得怎么样”，包括：

- `validation_id`
- `operator_id`
- `run_id`
- `status`
- `dataset_id`
- `run_dir`
- `summary`
- `product_manifest_path`

检索接口 `search_operators` 支持：

- 结构化过滤：`family`、`input_media_type`、`output_media_type`、`metric_name`、`status`、`tags`。
- SQLite `FTS5` 全文检索。
- 可选 embedding 检索，支持 `sqlite_vec` 时走向量表，否则用 Python cosine similarity。
- 混合排序：语义结果和文本结果合并，按相关性与限制数量返回。

在 `benchmark register` 中，算子库的作用是把历史可运行产物变成候选工具，而不是让 LLM 从零猜测可运行命令。

## Benchmark 比对历史库 benchmark_comparison_history_store

`benchmark_comparison_history_store` 保存历史 benchmark 比对计算记录，主要服务两个场景：复用已有成功结果，以及给 `report local_data_lane` 提供本地比对计算证据。

```mermaid
flowchart TD
    CaseRun[benchmark case 执行] --> Rec[benchmark_result_record.json]
    Rec --> Norm[normalize record]
    Norm --> DB[index.sqlite<br/>benchmark_records]
    Norm --> Emb[embedding.json<br/>可选]
    Emb --> DB
    DB --> Search[search_records]
    Search --> Register[benchmark 复用历史结果]
    Search --> Report[report local_data_lane 引用历史证据]
```

目录结构：

```txt
benchmark_comparison_history_store/
├── records/
│   └── <repo>/<run_id>/
│       ├── benchmark_result_record.json
│       └── embedding.json
└── index.sqlite
```

核心字段：

| 字段 | 作用 |
| --- | --- |
| `record_id` | 历史记录唯一标识 |
| `repo` | 工具或仓库名 |
| `operator_id` | 对应算子 |
| `dataset_key` | 数据集标识 |
| `workflow_signature` | workflow 摘要 |
| `input_signature` | 输入摘要 |
| `success` / `returncode` | 执行结果 |
| `workflow_path` / `inputs_json_path` | 可复现输入 |
| `result_manifest_path` | 输出检查结果 |
| `analysis_path` | 指标分析文件 |
| `canonical_text` | 用于检索的文本 |

检索 `search_records` 先做结构化过滤，再用 query token 和可选 embedding 对候选重排。默认 `success_only=True`，需要报告失败经验时可设为 `False`。

## 评估指标与完成度判断

评估器是 artifact post-processor，不是 agent。它读取 run 目录产物，写 `evaluation.json`。目前主要支持 `github2workspace` 和 `benchmark`。

### github2workspace 评估等级

| 等级 | 名称 | 判断依据 |
| --- | --- | --- |
| `G0` | `repo_not_materialized` | 仓库未成功落地 |
| `G1` | `repo_materialized` | 有成功 materialization 记录 |
| `G2` | `repo_inspected` | `inspect` 至少 partial/completed |
| `G3` | `environment_created` | 找到 Dockerfile 等环境产物 |
| `G4` | `environment_built` | 有 Docker build 成功证据 |
| `G5` | `workflow_created` | 有 WDL 产物 |
| `G6` | `workflow_validated` | `wdl` 节点至少 partial/completed |
| `G7` | `smoke_run_succeeded` | `outputs.json` + 成功 `workflow.log` |
| `G8` | `workspace_reproducible` | 关键请求、决策和成功输出都存在 |

同时检查 false positive：

- 没有 build 证据却声称 Docker 成功。
- 没有 smoke 成功证据却声称端到端跑通。
- 没有可复现证据却声称完全可复现。

### benchmark 评估等级

| 等级 | 名称 | 判断依据 |
| --- | --- | --- |
| `B0` | `benchmark_not_registered` | 未注册 |
| `B1` | `task_registered` | 有 `operator_selection.json` 或 register 输出 |
| `B2` | `operators_selected` | 选出了工具 |
| `B3` | `inputs_resolved` | 输入或数据集已解析 |
| `B4` | `cases_materialized` | case manifest 和 WDL/input 已落地 |
| `B5` | `execution_started` | run/status 或 wdl/status 出现 |
| `B6` | `single_operator_completed` | 至少一个工具成功 |
| `B7` | `multi_operator_completed` | 至少两个工具成功 |
| `B8` | `metrics_extracted` | 有指标 |
| `B9` | `comparison_valid` | 可比较数据集上形成有效比较 |
| `B10` | `result_reusable` | 有可复用历史记录或复用证据 |

额外指标：

- `selected_operators`
- `completed_operators`
- `failed_operators`
- `dataset_consistency`
- `comparison_valid`
- `history_reuse`
- `required_evidence_missing`
- `unsupported_claims`

这套评估避免只看最终回答文字，而是把“真实完成到哪一步”落到文件证据上。

## 入口文件速查

| 文件 | 作用 |
| --- | --- |
| `libs/code2workspace/code2workspace/orchestration_runtime.py` | `TaskGraph` 数据结构、分类、规划、依赖调度、决策检查 |
| `libs/cli/code2workspace_cli/supervisor_runtime.py` | CLI supervisor wrapper、运行目录、worker 执行、产物落盘、helper adapter |
| `libs/cli/code2workspace_cli/supervisor_capabilities.py` | `capability_bundles` 到工具和 guidance 的映射 |
| `libs/cli/code2workspace_cli/supervisor_evaluation.py` | `evaluation.json` 阶段化评估 |
| `libs/cli/code2workspace_cli/operator_store.py` | 算子库、结构化/全文/向量检索 |
| `libs/cli/code2workspace_cli/benchmark_result_store.py` | benchmark 比对历史库实现；模块名保留旧称以兼容代码 |
| `.code2workspace/skills/orchestration/supervisor-guidance/` | family 和 node 执行经验 |
| `.code2workspace/skills/orchestration/benchmark-workflow-orchestrator/scripts/benchmark_workflow.py` | benchmark 确定性 helper |
