# Generic Orchestration Harness 实现方案

## 目标

为 `generic` Supervisor Graph 编排建立一个真正可运行的本地 harness 闭环，而不只是 trace 观察层。闭环要能：

- 跑 baseline generic case 集
- 汇总 `generic_trace_summary.json` / `evaluation.json`
- 基于 train 结果修改明确的 orchestration guidance surface
- 复跑 candidate
- 用 holdout guardrail 决定 keep / discard
- 把 proposal、candidate、decision、report 全部落盘

## 优化对象

第一版只优化 generic guidance surface，不碰 runtime Python 逻辑本身。原因是：

- 这符合现有 harness “先改 surface，再比较结果”的结构
- generic 编排的很多策略已经逐步迁到 Skill asset，更适合作为 prompt surface
- 先把优化面收敛到 guidance，能更快验证 harness 闭环是否有效

本次暴露的 surface：

- `references/families/generic_qa.md`
- `references/nodes/init_generic.md`
- `references/nodes/worker_context.md`
- `references/nodes/worker_solution.md`
- `references/nodes/compose_generic.md`

其中 `init_generic.md`、`worker_solution.md`、`generic_qa.md` 是这次补齐的资产化 surface，避免 generic harness 只能改一半节点。

## Case 集设计

第一版 case 集故意选“本地代码说明题”，不依赖外网，目标是稳定观察 generic 编排是否过重、是否保留证据边界、是否真的利用 raw trace/evaluation artifact。

当前配置文件：

- `experiments/harness/configs/generic_orchestration_harness.toml`

split 设计：

- `train`
  - trace artifact 说明
  - generic evaluation 六分数说明
  - generic harness 闭环缺口说明
- `holdout`
  - `tool_activity.jsonl` 与 `raw_worker_traces` 区别
  - `unknown tool event` 修复说明

## 评分与 guardrail

每个 case 直接读取该 run 的 `generic_trace_summary.json` 分数：

- `routing_score`
- `graph_fit_score`
- `traceability_score`
- `evidence_score`
- `answer_score`
- `efficiency_score`

整体分数使用固定权重：

- routing: `0.10`
- graph_fit: `0.20`
- traceability: `0.20`
- evidence: `0.20`
- answer: `0.15`
- efficiency: `0.15`

接受规则：

- candidate 的 `train + holdout` 总分必须提升
- `holdout.traceability_score` 不能明显下降
- `holdout.mean_score` 不能比 baseline 低超过 1 分

这保证 harness 不会用牺牲 traceability 的方式换取表面答案分。

## 实现结构

新模块：

- `experiments/harness/generic_orchestration_harness/core.py`
  - config / dataclass / run layout
- `experiments/harness/generic_orchestration_harness/patching.py`
  - surface override
- `experiments/harness/generic_orchestration_harness/agent.py`
  - proposer workspace materialization
- `experiments/harness/generic_orchestration_harness/runner.py`
  - baseline / optimize 主循环
- `experiments/harness/proposers/generic_orchestration_surface_proposer.py`
  - 第一版规则型 proposer

artifact layout 延续现有 harness 风格：

- `manifest.json`
- `variants/*.json`
- `history/visible/train/<variant>/...`
- `history/private/holdout/<variant>/...`
- `history/visible/iterations/<n>/proposer_workspace/...`
- `report.json`

## 运行路径

runner 不模拟 Supervisor Graph，而是直接调用真实 CLI：

`uv run --project libs/cli code2workspace --session-workdir-mode isolated --no-mcp -n <prompt> -q`

这样每个 case 都会生成真实：

- `workspace/<session>/orchestration_runs/<run_id>/`

runner 再从真实 run 中读取：

- `evaluation.json`
- `generic_trace_summary.json`
- `final_response.md`
- stdout / stderr

为了稳定找到当前 case 对应的 run，runner 在调用前后比较已存在 run 集合，用“新出现的 run”而不是简单文件名排序。

## 第一版 proposer 策略

规则 proposer 读取 train summary 后，只做小范围 guidance 增量：

- `init_generic`
  - 窄任务优先最小图
  - 不默认拆成 context + solution 双 lane
- `worker_context`
  - 一份关键 artifact 足够时，优先读透而不是扩大检索
  - 单一主来源时说明 sufficiency / missing evidence
- `compose_generic`
  - 短答案里也保留 compact evidence boundary
- `worker_solution`
  - 足够 compose 后就停，不再继续工具回路

## 实际 live 结果

真实 optimize run：

- `experiments/harness/runs/generic-orchestration-harness/20260519T010322Z`

结果：

- baseline train: `85.08`
- candidate train: `86.50`
- baseline holdout: `84.75`
- candidate holdout: `86.88`
- decision: `accepted`

最明显变化：

- train `efficiency_score`: `85 -> 100`
- holdout `evidence_score`: `50 -> 70`
- holdout 仍保持 `traceability_score = 100`

## 已知限制

- local-code generic 问题仍然偏爱起 inspect lane，说明 planner 仍偏保守
- proposer 目前是规则型，不会做更细粒度的 surface search
- score 仍完全依赖 deterministic summary，没有接 LLM judge
- case 集还偏小，适合作为第一版闭环，不足以覆盖 generic 的全部任务族

## 下一步

- 增加更短更窄的 local-code case，专门压 `init_generic` 的最小图倾向
- 为 candidate 引入更多 proposer 变体，而不是单条规则修改
- 把 proposer 结果和最终 score delta 写成更紧凑的 Markdown report
- 在 harness 报告里增加“每 case 对应 orchestration run 链接清单”，方便手工复盘
