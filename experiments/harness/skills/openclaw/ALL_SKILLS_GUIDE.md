# Skills 总览说明

本文档说明当前 `skills` 目录中现有 skill 的大致职责，以及推荐的路由关系。

当前目录包含：

- `academic-search`
- `acpx-skill`
- `benchmark-agent-acpx`
- `epietl-api`
- `code2workspace_agent`
- `respiratory-disease-data-fetcher`
- `respiratory-disease-wide-monitor`
- `virus-variation-query`

## 路由原则

- 查论文 / 文献：优先 `academic-search`
- 查本地 virus_variation / covid_data 数据库：优先 `virus-variation-query`
- 查结构化 source catalog / source URL / source type：优先 `epietl-api`
- 查官方网页 / 周报 / PDF / 多地区监测：优先 `respiratory-disease-wide-monitor`
- 明确要求外部 agent、继续外部会话、走 `acpx`：使用 `acpx-skill`
- 跑 benchmark / compare / workflow reuse：优先 `benchmark-agent-acpx`
- repo / code 转 workspace、生成本地 WDL 与 workspace 产物：优先 `code2workspace_agent`

## 当前约束

- workflow 默认按本地执行路径理解，不再假设远端工作流平台
- 报告生成统一走 `report_agent`
- benchmark 和 code2workspace 长任务都应通过 `acpx ... exec`，不要 `sessions_spawn`
