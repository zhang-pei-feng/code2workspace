# ACPX / Benchmark / Code2Workspace Skills 说明

本文档说明当前 `skills` 目录下与 `acpx` 外部智能体桥接相关的 3 个 skill：

- `acpx-skill`
- `benchmark-agent-acpx`
- `code2workspace_agent`

目标是明确它们分别做什么、什么时候触发，以及在“工作流只在本地跑”的前提下应如何使用。

## 一览

### 1. `acpx-skill`

- 总桥接入口，不是单一业务 skill
- 通过本地 `.acpxrc.json` 路由到外部 agent
- 适合明确要求使用 `acpx`、继续外部 agent 会话，或显式点名外部 agent 的任务

默认路由：

- benchmark / compare / workflow reuse -> `benchmark_agent`
- source / 数据源 / snapshot / MySQL / lineage / mutation -> `data_governance_agent`
- 联网研究 / 带来源链接总结 -> `deep_research_agent`
- paper2workspace / code2workspace / WDL / workspace 产物 -> `code2workspace_agent`
- 正式报告 / 风险评估报告 -> `report_agent`

### 2. `benchmark-agent-acpx`

- benchmark 专用桥接入口
- 统一把 benchmark / workflow reuse 类任务交给外部 `benchmark_agent`
- 只负责桥接，不负责伪造结果

适合的任务：

- `benchmark`
- `compare`
- `workflow reuse`
- `复用工作流`
- `复用已有 workflow`
- `已有 workflow 复跑`
- 需要多个本地 workflow 的真实结果做对比

### 3. `code2workspace_agent`

- code2workspace / paper2workspace 专用桥接入口
- 统一桥接到外部 `code2workspace_agent`
- 产物以本地 workspace、Docker 相关产物、WDL 和本地验证结果为主

适合的任务：

- `paper2workspace`
- `code2workspace`
- `仓库转 workspace`
- `代码转 workspace`
- `生成 workspace 产物`
- `生成/编写 WDL`

## 使用边界

- 报告生成不要走 `benchmark-agent-acpx`
- 本地 skill 能直接完成的任务，不要先走 `acpx-skill`
- `code2workspace_agent` 失败时，应该报告失败，不要在主会话里伪造一套完成结果
