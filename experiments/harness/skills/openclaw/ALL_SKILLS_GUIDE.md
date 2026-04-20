# Skills 总览说明

本文档说明当前 `skills` 目录中现有的全部 skill、各自携带的资源，以及它们之间的推荐路由关系。

当前目录包含：

- `academic-search`
- `acpx-skill`
- `benchmark-agent-acpx`
- `epietl-api`
- `code2workspace_agent`
- `respiratory-disease-data-fetcher`
- `respiratory-disease-wide-monitor`
- `virus-variation-query`

另有一个补充说明文档：

- `ACPX_SKILLS_GUIDE.md`

## 目录一览

### 1. `academic-search`

路径：

`skills/academic-search/`

功能：

- 检索学术论文、预印本和文献元数据
- 支持 PubMed、Springer Nature、bioRxiv
- 可按需返回摘要、作者、期刊、DOI、链接

适合的任务：

- 查最新论文
- 查 PubMed / DOI / PMID
- 查综述、meta-analysis、systematic review
- 查临床试验、预印本
- 查 SARS-CoV-2 / 流感 / RSV / 疫苗 / 药物 / 变异研究文献

典型触发词：

- `根据最新论文信息`
- `基于最新论文`
- `查最新论文`
- `找最新文献`
- `PubMed`
- `DOI`
- `摘要`
- `临床试验`

不适合单独处理的任务：

- 本地数据库位点风险查询
- 官方监测网页和周报抓取

执行特点：

- 应优先运行 `python3 skills/academic-search/scripts/search_tools.py`
- 不应先用普通新闻或搜索摘要代替论文结果

### 2. `acpx-skill`

路径：

`skills/acpx-skill/`

功能：

- 总桥接入口
- 通过 `.acpxrc.json` 路由到外部 agent
- 当前注册 5 个外部 agent：
  - `benchmark_agent`
  - `data_governance_agent`
  - `deep_research_agent`
  - `code2workspace_agent`
  - `report_agent`

适合的任务：

- 明确要求使用 `acpx` 或外部 agent
- 需要继续外部 agent 会话
- 需要 `data_governance_agent`
- 需要 `deep_research_agent`
- 需要 `report_agent`
- 需要统一桥接到 benchmark 或 paper2workspace

默认路由：

- benchmark / compare / workflow reuse -> `benchmark_agent`
- source / 数据源 / snapshot / MySQL / lineage / mutation -> `data_governance_agent`
- 联网研究 / 带来源总结 -> `deep_research_agent`
- paper2workspace / code2workspace / WDL / workspace 产物 -> `code2workspace_agent`
- 正式报告 / 风险评估报告 -> `report_agent`

注意：

- 它是总桥接层，不应默认抢本地专用 skill 的任务
- 报告类只走 `report_agent`
- benchmark 和 paper2workspace 都要求通过 `acpx ... exec`，不要 `sessions_spawn`

### 3. `benchmark-agent-acpx`

路径：

`skills/benchmark-agent-acpx/`

功能：

- benchmark 专用桥接入口
- 统一把 benchmark / workflow reuse 类任务交给外部 `benchmark_agent`

适合的任务：

- `benchmark`
- `compare`
- `workflow reuse`
- `复用工作流`
- `复用已有 workflow`
- `已有 workflow 复跑`
- `Bio-OS workflow reuse`

强约束：

- 不用 `sessions_spawn`
- 必须通过 `acpx --cwd skills/acpx-skill benchmark_agent exec ...`
- Bio-OS / Miracle 任务要注入环境变量
- 没有真实 `submission_id`、状态、结果文件路径就不能算完成

不适合的任务：

- 正式报告生成
- paper2workspace
- 普通网页调研

### 4. `epietl-api`

路径：

`skills/epietl-api/`

功能：

- 调用 EpiETL API
- 查全球疾病监测报告、风险事件、source channel、source catalog
- 特别适合查结构化数据源目录和 source type

适合的任务：

- EpiETL / epidemic intelligence
- source catalog / source URL / source type
- Dashboard / Report Collection / News / Data 分类
- WHO COVID dashboard / CSV / hospitalization / ICU 数据源
- 中国疾控、香港 CHP、台湾 CDC 的报告集合或结构化数据源

典型触发词：

- `source catalog`
- `source url`
- `source type`
- `Dashboard`
- `Report Collection`
- `News`
- `Data`
- `flux_data.xlsx`
- `covidx_data.xlsx`

边界：

- 只要问题核心是“数据源目录、来源类型、结构化地址”，它优先于 `respiratory-disease-wide-monitor`
- 不替代本地 SQL 查询
- 不替代纯论文检索

### 5. `code2workspace_agent`

路径：

`skills/code2workspace_agent/`

功能：

- paper2workspace / code2workspace 专用桥接入口
- 统一桥接外部 `code2workspace_agent`
- 生成 workspace、WDL、Bio-OS workspace 产物

适合的任务：

- `paper2workspace`
- `code2workspace`
- `仓库转 workspace`
- `代码转 workspace`
- `生成 workspace 产物`
- `生成/编写 WDL`
- `Bio-OS workspace`

强约束：

- 不要 `sessions_spawn`
- 不要在主会话手工替代执行 Dockerfile/WDL/Bio-OS 流程
- 必须把用户原始任务整体转给外部 agent

不适合的任务：

- benchmark
- 报告生成
- 普通文献检索

### 6. `respiratory-disease-data-fetcher`

路径：

`skills/respiratory-disease-data-fetcher/`

功能：

- 获取少量固定官方来源的近期呼吸道病原监测数据
- 覆盖 WHO、U.S. CDC、中国疾控、WHO Africa、WHO variants 等少量来源

适合的任务：

- 快速看 WHO/CDC/中国疾控近期数据
- 看美国 COVID 趋势
- 看中国疾控最近一个月疫情情况
- 看 WHO 变异株信息

边界：

- 只适合少量固定源快速结果
- 如果需求可能落在更大的来源表里，应优先改走 `respiratory-disease-wide-monitor`

在多源综合问题中的作用：

- 适合作为官方监测层
- 常与 `academic-search` 和 `virus-variation-query` 组合使用

### 7. `respiratory-disease-wide-monitor`

路径：

`skills/respiratory-disease-wide-monitor/`

功能：

- 广域呼吸道病原官方网页/报告/PDF 监测
- 读取本 skill 自带的来源表 `skills/respiratory-disease-wide-monitor/整理后的数据源表.xlsx`
- 覆盖 50+ 数据源

适合的任务：

- 多国 / 多地区 / 多机构监测
- 官方网页 / 周报 / 月报 / PDF 抓取
- 变异株 / 新冠 / 流感 / RSV 官方监测更新
- “尽量全面”
- “不要只看 WHO 和 CDC”
- “从整理后的数据源表抓取”

边界：

- 不用于 source catalog / source type / 结构化 XLS CSV JSON 分类问题
- 这类目录型问题应让给 `epietl-api`
- 不用于本地 SQL 查询

执行特点：

- 通过 `scripts/fetch_sources.py` 先筛选来源，再抓取页面/PDF
- 适合给正式报告提供广域监测证据

### 8. `virus-variation-query`

路径：

`skills/virus-variation-query/`

功能：

- 查询本地 `virus_variation` MySQL 风险库
- 查询 `covid_data` 中的谱系、突变、导入记录
- 处理位点风险、谱系突变、表结构、导入状态等数据库问题

适合的任务：

- 查本地变异库
- 查位点风险
- 查 RBD / S 蛋白突变
- 查 lineage mutation
- 查导入状态
- 查表结构、字段、记录数

典型触发词：

- `查数据库`
- `查库`
- `virus_variation`
- `位点风险`
- `RBD`
- `S蛋白`
- `lineage`
- `PQ.2 在 RBD 区域有哪些氨基酸突变`

边界：

- 不替代官方监测网页和趋势数据
- 不替代论文检索
- 但在变异株综合研判里应作为本地证据层保留

## 共享资源

### `respiratory-disease-wide-monitor/整理后的数据源表.xlsx`

路径：

`skills/respiratory-disease-wide-monitor/整理后的数据源表.xlsx`

作用：

- 是 `respiratory-disease-wide-monitor` 的核心来源表
- 包含 50+ 呼吸道病原相关官方数据源、仪表板、报告页和网站入口

注意：

- 它属于 `respiratory-disease-wide-monitor` skill 自带资源，不应再视为顶层共享文件
- 如果只拷贝 `respiratory-disease-wide-monitor` 而不带上这张表，功能会不完整

## 推荐路由关系

### 论文 / 文献问题

- 优先 `academic-search`

### 本地数据库 / 变异风险 / 谱系突变问题

- 优先 `virus-variation-query`

### source catalog / source URL / source type / 结构化数据源问题

- 优先 `epietl-api`

### 广域官方网页 / 周报 / 月报 / PDF / 多地区监测问题

- 优先 `respiratory-disease-wide-monitor`

### 少量固定官方源快速查询

- 优先 `respiratory-disease-data-fetcher`

### benchmark / compare / workflow reuse

- 优先 `benchmark-agent-acpx`

### paper2workspace / code2workspace / WDL / workspace 产物

- 优先 `code2workspace_agent`

### 明确要求外部 agent / acpx / report / deep research / data governance

- 优先 `acpx-skill`

## 特别说明

### 1. `acpx-skill` 不是默认万能入口

虽然它覆盖多个外部 agent，但对下面这些问题不应优先抢路由：

- 论文检索
- 本地病毒变异数据库查询
- EpiETL source catalog 问题
- 广域呼吸道监测网页抓取

### 2. `benchmark-agent-acpx` 和 `code2workspace_agent` 是专用桥接层

这两个 skill 都是为长任务和高约束任务准备的，保留单独入口是合理的：

- 固定命令形态
- 固定超时和 poll 方式
- 禁止 `sessions_spawn`
- 失败时不能假装本地完成

### 3. 综合问题通常不是单 skill

例如“某变异株是否可能突破免疫屏障、是否有疫苗或临床试验、近期传播风险如何”这类问题，通常要联合：

- `virus-variation-query`
- `academic-search`
- `respiratory-disease-data-fetcher` 或 `respiratory-disease-wide-monitor`

## 当前打包建议

如果要整体转交当前全部 skills，建议一起包含：

- 所有 8 个 skill 目录
- `respiratory-disease-wide-monitor/整理后的数据源表.xlsx`
- `ALL_SKILLS_GUIDE.md`
- `ACPX_SKILLS_GUIDE.md`

这样接收方既能看到当前所有能力，也能看到 `acpx` 相关 skill 的单独说明。
