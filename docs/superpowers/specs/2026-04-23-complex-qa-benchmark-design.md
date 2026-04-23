# Complex QA Benchmark Design

## Goal

为 `code2workspace` 增加一条可重复、可优化、可审计的复杂问答评测路径，用于：

- 整理已有与新增的复杂问答题目为版本化题集
- 对题集执行统一格式的基线重跑
- 保存完整运行链路，而不只保存最终答案
- 用 harness 自动优化 `planning-guide` 及相关技能，提升答案的准确性、完备性、合理性与调用链路合理性

这条路径与现有 repo-to-Docker/WDL harness 并行存在，不替代它。

## Scope

第一版复杂问答题集 `complex-qa-suite-v1` 采用 12 题，覆盖趋势分析、数据库检索、论文检索、跨源整合、其他研判、报告生成六类任务。

### Benchmark v1 Cases

1. 今年 5 月，中国大陆的主要流行新冠毒株（占比最高的毒株）会是哪一株？
2. 近两周增长最快的亚型及其序列数有多少？
3. 未来 BA.3.2 和 XFG.1.1 毒株的 RBD 区域是否会趋同进化？
4. 当前中国 JN.1 毒株占比及其近期在中国的流行趋势如何？是否可以认为几乎没有了？
5. PQ.2 毒株在 RBD 区域上有哪些氨基酸突变？
6. BA.3.2 和 XFG 毒株的子代能否突破接种了 KP.2 毒株疫苗人群的免疫屏障？
7. 近期是否有新的针对新冠 BA.3.2 的疫苗进入临床试验？
8. 最新的新冠疫苗是哪个公司生产的？用的是什么毒株？
9. 临床阳性率趋势与污水监测趋势是否一致？
10. BA.3.2 和 XFG 毒株的子代中，哪一种有更强的免疫逃逸能力、可能由哪些位点驱动、能否突破中国人群免疫屏障、以及单抗 BD55-1205 是否仍有效？
11. 下一波新冠/流感阳性率的高峰会在什么时间？
12. XFG.1.1 毒株的风险评估报告（按 WHO 风格的相对增长速率、临床重症率、免疫逃逸能力三个维度）

其中一部分题目来自已测过的 `covid-monitoring-*` 与 `capability-snapshot-*` case；这些题目仍然需要作为新题集成员统一重跑，不沿用旧结果作为主基线。

## Non-Goals

- 不在第一轮引入人工评分闭环
- 不把复杂问答硬塞进当前 repo-to-workspace repo benchmark
- 不要求第一轮 outer-loop 自动修改 Python 数据抓取脚本
- 不在第一轮追求通用 benchmark 平台化

## Architecture

### 1. Case Catalog Layer

新增一个版本化复杂问答题集目录，保存题目与评测元数据。

建议目录结构：

- `experiments/skill_tests/cases/complex_qa/`
- `experiments/skill_tests/datasets/complex_qa_suite_v1/`
- `experiments/skill_tests/batches/complex-qa-suite-v1.md`

每个 case 仍使用 TOML，但补充以下元数据字段：

- `task_family`
- `question_type`
- `source_hints`
- `source_urls`
- `preferred_skills`
- `judge_focus`
- `prior_case_refs`
- `weight`
- `timeout_minutes`

题集目录中的总表文件需要明确记录：

- case 清单
- 是否来自旧题
- 期望涉及的数据源类型
- 重点观察的技能链路
- train / holdout / scorecard 划分

### 2. Real Run Artifact Layer

保留 `experiments/skill_tests` 作为真实运行入口，因为它已经能直接驱动 `code2workspace` 并保存原始日志。

对现有 runner 的增强目标：

- 支持复杂问答案例的递归组织方式
- 为每个 case 额外写出结构化 trace 文件，而不是只保留 `.log`
- 在汇总中保留 case 元数据，方便后续 judge 与 harness 消费

每个 case 的标准产物为：

- `*.prompt.txt`
- `*.log`
- `*.answer.txt`
- `*.trace.json`
- `*.judge.json`

每个 batch 的标准产物为：

- `summary.json`
- `SUMMARY_ZH.md`
- `CAPABILITY_SNAPSHOT_ZH.md`
- `TRACE_SUMMARY_ZH.md`
- `JUDGE_SUMMARY_ZH.md`

原始 `.log` 仍是最终可信链路记录；`trace.json` 是便于自动分析的结构化副本。

### 3. Structured Trace Contract

`trace.json` 至少需要包含：

- `tool_invocations`
- `tool_names`
- `subagents`
- `summary_lines`
- `repo_paths`
- `answer_char_count`
- `tool_invocation_count`
- `trace_warnings`

如果日志中能稳定提取到更多规划信号，还应附加：

- `planner_recommendation`
- `selected_skill_hints`
- `source_usage_hints`

第一版不要依赖“完美重建完整思维链”；目标是稳定提取足以审计的执行链路与规划痕迹。

### 4. Judge Layer

复杂问答不能只用关键词判断，因此采用双层自动评分。

#### 4.1 Rule Layer

规则层输出 0-20 分，负责最低限度的结构性质量检查：

- 运行成功且答案非空
- 产物完整
- 存在可分析 trace
- 题目要求的最小结构被满足
- 存在最基本的数据源/来源说明

规则层不是主评分器，主要用于过滤明显坏样本与给 judge 补充结构信号。

#### 4.2 Model Judge Layer

模型 judge 输出 0-80 分，按统一 rubric 打分：

- `accuracy`：0-30
- `completeness`：0-20
- `reasonableness`：0-15
- `trace_rationality`：0-15

judge 输入至少包含：

- 题目
- case 元数据
- 最终答案
- 结构化 trace
- 规则层特征

judge 输出必须是严格 JSON，至少包含：

- `overall_score`
- `rule_score`
- `judge_score`
- `dimension_scores`
- `verdict`
- `major_issues`
- `trace_findings`
- `improvement_hints`

最终 case 分数为：

- `total_score = rule_score + judge_score`

### 5. Complex QA Harness Layer

新增一条并行的 harness 路径，例如：

- `experiments/harness/complex_qa_harness/`

这条 harness 不复用现有 repo benchmark 的“通过个数”口径，而是按复杂问答综合分优化。

支持的命令与现有 harness 保持一致的操作方式：

- `validate`
- `run-baseline`
- `optimize`

但内部语义改为：

- baseline：运行整套问题集并打分
- optimize：修改 planner/skill surfaces，重新运行 train/holdout，并根据综合分决定 keep/discard

### 6. Surface Strategy

第一轮 outer-loop 只暴露与复杂问答质量最相关的 surface：

- `.code2workspace/skills/planning-guide/SKILL.md`
- `.code2workspace/skills/planning-guide/references/source-selection.md`
- `.code2workspace/skills/planning-guide/references/case-cross-source-synthesis.md`
- `.code2workspace/skills/planning-guide/scripts/planning_tool.py`
- `.code2workspace/skills/academic-search/SKILL.md`
- `.code2workspace/skills/respiratory-disease-data-fetcher/SKILL.md`
- `.code2workspace/skills/virus-variation-query/SKILL.md`
- `.code2workspace/skills/multi-source-report/SKILL.md`

如果后续数据表明仅改文本 surface 不足，再考虑把相关 `agents/openai.yaml` 或脚本逻辑纳入第二阶段 surface。

### 7. Proposer Strategy

优先走命令 proposer，而不是依赖外部 deepagents。

新增一个本地 proposer 脚本，负责：

- 读取 proposer workspace 中的 train 失败样本、judge 结果与当前 surface
- 通过 `code2workspace` 非交互运行或直接模型调用生成新的 surface 内容
- 只修改 `current/` 下的 surface 文件与 `proposal.md`

这样可以保持：

- outer-loop 仍然由 harness 驱动
- proposer 的行为同样可以留下日志和请求记录
- 不依赖额外仓库或另一个运行时

## Scoring And Acceptance

每个 split 的总分采用 case `total_score` 的加权平均值。

第一版 acceptance rule：

- `candidate` 的 `train + holdout` 平均分之和必须高于当前 accepted variant
- `holdout` 平均分不能出现明显回退
- 若总分几乎持平，则优先选择 `trace_rationality` 更高的 variant

这比当前 repo benchmark 的“pass 个数”更适合复杂问答任务。

## Dataset Split

第一版建议：

- `train`: 8 题
- `holdout`: 4 题
- `scorecard`: 可选，保留给后续新增题或人工挑选题

split 需要显式版本化，不允许运行时临时抽样。

## Reporting

每次 baseline 或 optimize 运行后，需要生成：

- 题级别分数表
- 维度分数表
- 调用链异常摘要
- 前后版本差异摘要
- 被接受/拒绝的理由

对用户可读的核心报告至少包含：

- 哪些题改善了
- 哪些题退化了
- 哪些 skill / planner surface 被修改了
- judge 认为的主要问题模式

## Validation

需要覆盖三类验证：

1. runner / parser 单测
- case 新字段解析
- trace 文件输出
- answer / trace / judge 产物路径正确

2. judge 单测
- 规则层特征计算
- judge prompt 结构
- JSON 解析与容错

3. harness 单测
- config 加载
- baseline 聚合
- optimize keep/discard 逻辑
- proposer workspace 产物复制与展示

## Execution Plan

按以下顺序实现：

1. 固化题集目录、case schema 与 batch 入口
2. 增强 `skill_tests` runner，补 trace 产物与复杂问答元数据
3. 增加 judge 脚本与评分汇总
4. 新建 `complex_qa_harness`
5. 新建 proposer 命令路径
6. 跑完整 baseline
7. 跑数轮优化并记录变更

## Risks And Mitigations

### Risk 1: judge 漂移或过于宽松

缓解：

- 保留 rule layer
- 保存完整 judge 输入输出
- 后续人工抽查时能回溯判分依据

### Risk 2: outer-loop 过拟合 train

缓解：

- 显式 holdout
- acceptance 不能只看 train
- proposer workspace 中不暴露 holdout 细节

### Risk 3: 自动 proposer 修改范围过大

缓解：

- 第一轮只开放少量高价值 surface
- proposer 只允许编辑 `current/`
- 每轮必须记录 `proposal.md`

### Risk 4: 运行时间过长

缓解：

- 题集控制在 12 题
- baseline 与 split 内 case 允许并发
- report 类题目单独设置更长 timeout，普通题使用更短 timeout

## Decision Summary

最终采用的方案是：

- 用新的复杂问答题集统一旧题与新题
- 用 `skill_tests` 负责真实运行与全链路保存
- 用 rule + model judge 做全自动综合评分
- 用新的 `complex_qa_harness` 做 train/holdout 优化闭环
- 优先优化 `planning-guide` 与相关技能文本 / planner surface
