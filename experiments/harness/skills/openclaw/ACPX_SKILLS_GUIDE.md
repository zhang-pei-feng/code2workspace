# ACPX / Benchmark / Paper2Workspace Skills 说明

本文档说明当前 `skills` 目录下与 `acpx` 外部智能体桥接相关的 3 个 skill：

- `acpx-skill`
- `benchmark-agent-acpx`
- `code2workspace_agent`

目标是明确它们分别做什么、什么时候触发、什么时候不该触发，以及三者之间的关系。

## 一览

### 1. `acpx-skill`

路径：

`skills/acpx-skill/`

作用：

- 这是总桥接入口，不是单一业务 skill。
- 它通过本地 `.acpxrc.json` 把请求路由到外部 agent。
- 当前注册了 5 个外部 agent：
  - `benchmark_agent`
  - `data_governance_agent`
  - `deep_research_agent`
  - `code2workspace_agent`
  - `report_agent`

当前注册配置见：

- `skills/acpx-skill/.acpxrc.json`

本地 wrapper 的作用是把 agent 名解析成真实的 ACP 启动命令。默认会从下面两种路径之一找外部 agent：

- 环境变量 `*_ACP_COMMAND`
- `skills/acpx-skill/external-agents/<agent>/run-acp.sh`

适合的任务：

- 明确要求“调用外部 agent / 用 acpx / 继续某个外部 agent 会话”
- 需要桥接到 `data_governance_agent`
- 需要桥接到 `deep_research_agent`
- 需要桥接到 `report_agent`
- 需要桥接到 `code2workspace_agent`
- 需要桥接到 `benchmark_agent`

默认路由语义：

- benchmark / compare / workflow reuse -> `benchmark_agent`
- source / 数据源 / snapshot / MySQL / lineage / mutation -> `data_governance_agent`
- 联网研究 / 带来源链接总结 -> `deep_research_agent`
- paper2workspace / code2workspace / WDL / workspace 产物 -> `code2workspace_agent`
- 正式报告 / 风险评估报告 -> `report_agent`

注意事项：

- 它是桥接层，不应默认抢走本地专用 skill 的任务。
- 如果用户明确要求“用 acpx-skill / 用某个外部 agent 回答”，就必须真的走外部 agent。
- 报告类任务只走 `report_agent`，不要并行改走 `benchmark_agent`。
- 对 `code2workspace_agent` 和 `benchmark_agent` 都明确禁止 `sessions_spawn`，要求通过 `acpx ... exec`。

### 2. `benchmark-agent-acpx`

路径：

`skills/benchmark-agent-acpx/`

作用：

- 这是 benchmark 专用入口。
- 它本身不实现 benchmark 逻辑，而是统一把 benchmark 任务桥接到外部 `benchmark_agent`。
- 实际命令路径固定为：

```bash
acpx --cwd skills/acpx-skill --timeout 3600 benchmark_agent exec "<任务文本>"
```

适合的任务：

- `benchmark`
- `compare`
- `workflow reuse`
- `复用工作流`
- `复用已有 workflow`
- `已有 workflow 复跑`
- `Bio-OS workflow reuse`
- 需要拿多个 workflow 的真实结果做对比
- 需要返回 `submission_id`、状态、结果文件路径

硬规则：

- 不要用 `sessions_spawn(runtime="acp", agentId="benchmark_agent")`
- 不要切到外部 `benchmark_agent` 仓库目录直接跑
- 必须通过 `skills/acpx-skill/.acpxrc.json` 去解析真实入口
- Bio-OS / Miracle 任务要把 `MIRACLE_ACCESS_KEY` / `MIRACLE_SECRET_KEY` 注入子进程环境
- 如果没有真实 `submission_id`、状态、结果文件路径，就不能宣称任务完成

执行特征：

- 对长任务需要长超时
- 第一次返回 `Command still running` 时必须继续轮询
- 对短探活消息可以 one-shot
- 对含环境变量导出的任务强制 fresh one-shot，避免复用旧会话污染

### 3. `code2workspace_agent`

路径：

`skills/code2workspace_agent/`

作用：

- 这是 paper2workspace / code2workspace 专用入口。
- 它统一桥接到外部 `code2workspace_agent`，把仓库、代码、paper 需求转成 workspace 产物。
- 典型产物包括：
  - workspace
  - Docker 相关产物
  - WDL
  - Bio-OS workspace 结果

适合的任务：

- `paper2workspace`
- `code2workspace_agent`
- `code2workspace`
- `仓库转 workspace`
- `代码转 workspace`
- `生成 workspace 产物`
- `生成/编写 WDL`
- `Bio-OS workspace`

硬规则：

- 禁止 `sessions_spawn(runtime="acp", agentId="code2workspace_agent")`
- 禁止主会话自己拆分成 Docker 阶段和 WDL 阶段分别做
- 禁止主会话自己 `git clone`、手写 Dockerfile/WDL、`docker build`、`docker push` 或 Bio-OS 投递来替代外部 agent
- 必须把用户原始任务文本整体转发给 `code2workspace_agent`

推荐执行方式：

```bash
python3 skills/acpx-skill/scripts/acpx_session.py route \
  --agent code2workspace_agent \
  --prompt "<用户原始任务文本>"
```

或者：

```bash
acpx --cwd skills/acpx-skill \
  --format text \
  --timeout 7200 \
  code2workspace_agent exec "<用户原始任务文本>"
```

执行特征：

- 往往是长任务
- 需要长超时和长轮询
- 如果失败，应直接报告失败原因，不要本地补做一套假替代流程

## 三者之间的关系

### `acpx-skill` 和另外两个的关系

- `acpx-skill` 是总桥接层
- `benchmark-agent-acpx` 是 benchmark 场景的专用入口
- `code2workspace_agent` 是 paper2workspace 场景的专用入口

可以理解成：

- `acpx-skill` = 总路由器
- `benchmark-agent-acpx` = benchmark 的专线
- `code2workspace_agent` = paper2workspace 的专线

### 为什么 `benchmark-agent-acpx` 和 `code2workspace_agent` 还要单独保留

因为它们不是泛路由描述，而是对高风险长任务加了明确约束：

- 固定命令形态
- 固定超时建议
- 禁止 `sessions_spawn`
- 必须继续 poll
- 失败时不能本地冒充完成

这些约束对 benchmark 和 paper2workspace 都很关键，所以保留单独 skill 是合理的。

## 什么时候触发哪个

### 优先触发 `benchmark-agent-acpx`

当用户意图是：

- 跑 benchmark
- 对比多个 workflow / tool
- 复用已有 workflow
- 在 Bio-OS 里拿真实运行结果做比较

这时应直接走 `benchmark-agent-acpx`，而不是泛泛地说“先用 acpx-skill 看看”。

### 优先触发 `code2workspace_agent`

当用户意图是：

- 把 repo / code / paper 转成 workspace
- 生成 WDL
- 生成 workspace 产物
- 建立 Bio-OS workspace 运行资产

这时应直接走 `code2workspace_agent`。

### 优先触发 `acpx-skill`

当用户意图是：

- 明确说要调用某个 acpx 外部 agent
- 需要 `data_governance_agent`
- 需要 `deep_research_agent`
- 需要 `report_agent`
- 需要继续某个外部 agent 的会话
- 需要查看 acpx 会话状态 / 历史

这时 `acpx-skill` 才是正确入口。

## 不该怎么用

### 不要让 `acpx-skill` 抢本地专用 skill

以下任务不应优先走 `acpx-skill`：

- 查论文 / 文献 -> 应优先 `academic-search`
- 查本地 virus_variation / covid_data 数据库 -> 应优先 `virus-variation-query`
- 查 EpiETL source catalog / source type / source URL / 结构化 XLS CSV JSON -> 应优先 `epietl-api`
- 查广域呼吸道病原官方网页 / 周报 / PDF / 多地区监测 -> 应优先 `respiratory-disease-wide-monitor`

### 不要把报告类交给 benchmark

只要用户在生成正式报告、撰写报告、风险评估报告，统一应该走：

- `acpx-skill` -> `report_agent`

不要走：

- `benchmark-agent-acpx`

### 不要把 paper2workspace 任务本地硬做

`code2workspace_agent` 的核心约束就是：

- 不要在主会话手写 Dockerfile/WDL 充当 paper2workspace 的替代品

## 建议的最终理解

如果只记一条：

- “用户需要外部 agent” 时看 `acpx-skill`
- “用户要跑 benchmark/workflow reuse” 时直接用 `benchmark-agent-acpx`
- “用户要做 paper2workspace/code2workspace/WDL/workspace 产物” 时直接用 `code2workspace_agent`

如果只记第二条：

- `acpx-skill` 是总桥接层
- `benchmark-agent-acpx` 和 `code2workspace_agent` 是场景专用桥接层
- 专用层优先于总桥接层

## 当前目录中的对应路径

- `skills/acpx-skill/`
- `skills/benchmark-agent-acpx/`
- `skills/code2workspace_agent/`

本文档文件：

- `skills/ACPX_SKILLS_GUIDE.md`
