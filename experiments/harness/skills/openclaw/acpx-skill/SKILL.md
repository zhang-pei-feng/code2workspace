---
name: acpx-skill
description: "通过 workspace 里的 .acpxrc.json 用 acpx 桥接五个外部 agent：benchmark_agent、data_governance_agent、deep_research_agent、code2workspace_agent、report_agent。benchmark / compare / 工作流复用任务默认走 benchmark_agent；code2workspace / paper2workspace / workspace / WDL 产物任务默认走 code2workspace_agent；正式报告任务只走 report_agent。"
metadata: { "openclaw": { "emoji": "🔌", "requires": { "bins": ["acpx", "python3"] } } }
---

# ACPX Skill

通过 `acpx` 调用当前 skill 目录 `.acpxrc.json` 已注册的 5 个外部 agent，并在需要时复用稳定会话。

## 默认路由

- benchmark / compare / workflow reuse：`benchmark_agent`
- 数据治理、source、snapshot、MySQL、lineage、mutation：`data_governance_agent`
- 联网研究、搜资料、带来源链接的总结：`deep_research_agent`
- code2workspace、paper2workspace、仓库转 workspace、生成 workspace/WDL 产物：`code2workspace_agent`
- 生成报告、撰写报告、正式报告正文、风险评估报告：`report_agent`

## 规则

1. 如果用户明确要求“用 acpx-skill / 用某个外部 agent 回答”，就必须真的桥接到外部 agent。
2. 报告类任务只走 `report_agent`，不要改路由到 `benchmark_agent`。
3. `code2workspace_agent` 和 `benchmark_agent` 的长任务优先使用 `acpx ... exec`，不要 `sessions_spawn`。
4. 外部 agent 失败时，直接报告失败，不要在主会话里伪造替代结果。
5. workflow 默认按本地执行路径理解，不再假设远端工作流平台。
