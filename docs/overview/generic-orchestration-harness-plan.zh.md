# Generic Orchestration Harness 实现方案

## 目标

为 `generic` Supervisor Graph 编排建立一个真正可运行的本地 harness 闭环，而不只是 trace 观察层。闭环要能：

- 跑 baseline generic case 集
- 汇总 `generic_trace_summary.json` / `evaluation.json`
- 基于 train 结果生成 `generic-experience` 经验候选
- 复跑 candidate
- 用 holdout guardrail 决定 keep / discard
- 把 proposal、candidate、decision、report 全部落盘

## 优化对象

当前 generic harness 不再暴露 `supervisor-guidance` 下的可编辑 surface，也不再
使用 surface proposer。优化对象收敛为：

- `.code2workspace/skills/orchestration/generic-experience/records/*.json`
- `.code2workspace/skills/orchestration/generic-experience/generated/generic_orchestration_experience.md`

每轮候选只做一件事：从当前 train split 中已完成且高分的真实 generic run 抽取
经验记录，重建 distilled guidance，然后用这批经验重跑 train / holdout。候选通过
guardrail 就保留经验；失败则恢复进入该轮前的 `generic-experience` 快照。

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
- `experiments/harness/generic_orchestration_harness/runner.py`
  - baseline / optimize 主循环、experience candidate 导出、快照恢复

artifact layout 延续现有 harness 风格：

- `manifest.json`
- `variants/*.json`
- `history/visible/train/<variant>/...`
- `history/private/holdout/<variant>/...`
- `history/visible/iterations/<n>/experience_candidate.json`
- `history/visible/iterations/<n>/generic_experience_snapshot/...`
- `report.json`

## 运行路径

runner 不模拟 Supervisor Graph，而是直接调用真实 CLI：

`uv run --project libs/cli EpiMindAgent --session-workdir-mode isolated --no-mcp -n <prompt> -q`

这样每个 case 都会生成真实：

- `workspace/<session>/orchestration_runs/<run_id>/`

runner 再从真实 run 中读取：

- `evaluation.json`
- `generic_trace_summary.json`
- `final_response.md`
- stdout / stderr

为了稳定找到当前 case 对应的 run，runner 在调用前后比较已存在 run 集合，用“新出现的 run”而不是简单文件名排序。

## Experience Candidate 策略

每轮 candidate 直接从当前 train 结果生成经验：

- 只选择 `returncode = 0`、`completion_status = completed`、总分不低于阈值的
  case
- 从 `generic_trace_summary.json`、`graph_round_*.json` 和原始 prompt 中抽取
  problem classification、trajectory、effect、applicability、confidence
- 写入 `generic-experience/records/`
- 重建 `generated/generic_orchestration_experience.md`
- 复跑 train / holdout，由真实 runtime 的 experience 注入路径决定是否改善回答

这样优化压力集中在 case memory 本身，而不是反复改写
`supervisor-guidance` 的 family/node 文本。

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

2026-05-25 追加实践：

- 配置新增一个本地代码 holdout case，检查 generic harness 是否真的形成
  `accepted candidate -> experience records -> distilled guidance -> worker
  prompt 注入` 的 skill 进化链路。
- 配置新增三个 `scorecard` case，用于阶段性回放真实 generic 研判题：
  春运与新冠传播、下一波新冠/流感阳性率高峰、BA.3.2 与 XFG 子代重症率。
- `scorecard` baseline:
  `experiments/harness/runs/generic-orchestration-harness/20260525T002747Z`
  - `3/3` return code 0
  - mean score `97.0`
  - 三题均达到 `D6.evidence_boundary_preserved`
  - 回答形态基本符合“口头判断、不要正式写作、说明证据边界”
- `holdout` baseline:
  `experiments/harness/runs/generic-orchestration-harness/20260525T003726Z`
  - `3/3` return code 0
  - mean score `92.0`
  - 新增 skill 进化链路题达到 `D6.evidence_boundary_preserved`
  - 回答正确区分“离线经验沉淀并回注”和“在线即时自进化”

实践暴露的新观察：

- 真实公共卫生题的 score 很高，但 `source_urls` 候选集合较宽，会混入
  Wikipedia / 社交媒体等低权重来源；最终回答主要使用 CDC/WHO 等较强证据，
  但后续 scorecard 可以增加“权威来源优先/低权重来源不支撑核心结论”的检查。
- 最终回答会附带“判断轨迹（可审计摘要）”，利于 harness 审计，但对“口头判断、
  不要正式写作”的用户形态来说略偏正式；后续可把这作为 compose_generic 的风格
  guardrail。

## 已知限制

- local-code generic 问题仍然偏爱起 inspect lane，说明 planner 仍偏保守
- experience 抽取目前是规则型 abstraction，不是 LLM 归纳
- score 仍完全依赖 deterministic summary，没有接 LLM judge
- 常规 train/holdout case 集仍偏小；`scorecard` 已开始覆盖真实研判题，但还不参与
  optimize keep/discard

## 下一步

- 增加更短更窄的 local-code case，专门压 `init_generic` 的最小图倾向
- 把 experience candidate 与最终 score delta 写成更紧凑的 Markdown report
- 在 harness 报告里增加“每 case 对应 orchestration run 链接清单”，方便手工复盘
- 为 real-world scorecard 增加来源质量与口头回答风格检查，避免高分掩盖低权重
  来源候选过宽或回答过正式的问题
