# 论文实验设计中文稿

本文档用于把 `code2workspace` 当前已经完成的实验、正在进行的实验以及后续仍需补做的实验统一成一份正式论文风格的实验设计说明。该文档的组织方式已经参照本地开题报告样例中的“研究主要内容、研究方案和思路、论文框架结构、工作进度安排”栏目进行重组。这里的实验分为两类：

- 已有证据实验：仓库内已经有日志、summary、artifact 支撑的实验
- 待补做实验：当前尚未完成，但应在论文中提前定义的问题与设计

## 1. 研究主要内容

结合当前项目状态，论文实验部分主要围绕以下内容展开。

- 构建标准化的 one-shot repository runner，并形成可比较的仓库级结果
- 引入权威轻量 benchmark，补充通用软件工程能力验证
- 识别影响真实仓库任务完成率的关键 harness 因素
- 设计 evidence-backed completion judgment，提高完成标签的可信度
- 将 harness 调整形式化为 surface-based variant 优化过程
- 在已有实验与待补实验基础上分析系统有效性、局限性与后续优化方向

## 2. 实验目标

本课题的实验不以“单次运行是否恰好成功”为唯一目标，而是服务于以下三个研究判断。

- 智能体在真实重型仓库任务上是否能够进入真实执行路径
- harness 设计是否会显著影响任务完成率与失败模式
- 基于显式 surfaces 的优化框架是否比非结构化 prompt 调参更可复现、更可审计

## 3. 研究问题

建议在论文中明确列出以下研究问题。

### RQ1

在真实软件仓库的 Docker + WDL 任务上，当前 `code2workspace` one-shot 基线能够达到何种完成水平？

### RQ2

系统级 harness 设计因素，例如 shell 能力暴露、prompt surface 和 completion judgment，是否会显著改变运行结果？

### RQ3

对于 `spades`、`canu`、`megahit` 这类重型科学仓库，失败主要来自任务本身不可做，还是来自执行可靠性与 harness 不稳定？

### RQ4

将 harness 优化形式化为 surface-based variant search 后，是否能够提供比人工 prompt 迭代更强的可追溯性与泛化控制？

## 4. 实验对象

当前建议的实验仓库集合如下。

| 仓库 | 类型 | 当前状态 | 论文中的角色 |
| --- | --- | --- | --- |
| `SWE-bench Lite` | 通用软件工程 benchmark | 待补测 | 通用能力验证 |
| `spades` | 重型科学仓库 | 已形成正反例链路 | 核心个案 |
| `canu` | 重型科学仓库 | 已进入真实构建，30 分钟超时 | 难例 |
| `megahit` | 重型科学仓库 | 已进入真实构建，30 分钟超时 | 难例 |
| `Flye` | 科学仓库 | 已定位最短真实入口，尚未闭环 | 部分失败例 |
| `trinityrnaseq` | 重型科学仓库 | 30 分钟超时 | 难例 |
| `v-pipe` | 工作流型仓库 | 已自动完成 | 正例 |
| `covid-19-signal` | 工作流型仓库 | 已自动完成 | 正例 |
| `fieldbioinformatics` | 工作流型仓库 | 已自动完成 | 正例 |

## 5. 研究方案和思路

参考开题报告样例的写法，本文实验部分可以概括为以下实施路径。

1. 整理 one-shot runner、prompt 模板和结果目录结构，形成标准化实验入口。
2. 在代表性仓库上运行标准化 baseline，记录 prompt、日志、summary 与 manifest。
3. 通过 `spades` 等核心案例归纳失败模式，区分能力缺失、执行策略不足与具体工程错误。
4. 将 harness 中的 prompt 与 completion 规则显式化为 surfaces。
5. 采用 variant、split、keep/discard 机制组织外环优化。
6. 比较 baseline 与 candidate 的结果，并分析已完成实验和待补实验。

## 6. 实验环境与约束

论文中应明确记录以下环境前提。

- 运行平台为本地服务器环境
- one-shot 默认预算为 30 分钟
- 任务要求包含 Docker 镜像构建、真实数据验证、WDL 编写与 Cromwell 执行
- 重型生物信息学仓库运行成本高，因此实验设计必须强调分阶段验证，而不是大规模穷举

## 7. 对比方法

建议在论文中显式定义以下对比组。

### B0 历史弱基线

早期 one-shot 路径，完成判定弱、shell 能力未稳定暴露。

用途：

- 说明为什么初始 baseline 方法学不足
- 不一定要求全量重跑，可作为历史对照叙事使用

### B1 标准化 one-shot 基线

当前 `experiments/oneshot/run_repo_task.py` 路径下的标准化运行方式，具备：

- 标准 prompt 模板
- 机器可读 manifest/summary
- 30 分钟预算
- shell 能力允许

### B2 人工 prompt 迭代基线

在观察失败后由研究者手动修改 prompt 或策略再运行。

用途：

- 作为工程实践中的自然基线
- 用于与 harness 框架在可复现性和可审计性上对比

### M1 Harness baseline variant

当前 harness 配置下的 baseline surfaces，不做 proposer 修改，直接在 `train/holdout` 上评估。

### M2 Harness candidate variant

在 baseline surfaces 基础上修改部分 surfaces 后形成的 candidate variant。

## 8. 评价指标

建议采用“结果指标 + 过程指标 + 方法指标”三层结构。

### 8.1 结果指标

- `completed` 数量
- `completed` 比例
- WDL `Succeeded` 数量
- 真实输出工件落盘数量

### 8.2 过程指标

- 是否进入真实 `docker build`
- 是否进入真实 `docker run`
- 是否进入真实 Cromwell `run`
- 首次进入真实构建的时间
- 单次运行总时长
- 超时数量
- setup 失败数量

### 8.3 方法指标

- 是否具有结构化 variant 记录
- 是否具有 split-level 评估结果
- 是否具有 keep/discard 决策记录
- 是否具有 evidence-backed completion judgment

## 9. 论文框架结构中的实验部分落点

参考样例中的“论文框架结构”写法，实验内容在整篇论文中的落点建议如下。

- 第一章用于提出研究问题和实验动机
- 第二章用于说明相关技术与已有方法
- 第三章用于介绍系统实现与 one-shot runner
- 第四章用于说明 harness 方法与 completion judgment
- 第五章集中呈现实验结果与分析
- 结论部分用于概括实验发现与后续待补工作

如果只看实验章内部结构，则建议按以下顺序组织。

1. 实验目标与研究问题
2. 实验环境与实验对象
3. 评价指标与记录方式
4. 已完成 baseline 结果
5. 典型案例分析
6. harness 方法实验
7. 待补实验设计
8. 局限性与有效性威胁

## 10. 已有实验

### 10.1 已有实验 A：标准化 one-shot 结果概览

该实验已经具备仓库级 summary 与 manifest，可直接写入论文结果表。

| 仓库 | 代表性运行 | 状态 | 完成情况 | 当前可用结论 |
| --- | --- | --- | --- | --- |
| `spades` | `20260416T123616Z` | `finished` | 未完成 | 已进入真实构建 |
| `canu` | `20260416T151417Z` | `timed_out` | 未完成 | 已进入真实构建，受预算限制 |
| `megahit` | `20260416T154420Z` | `timed_out` | 未完成 | 已进入真实构建，暴露外部依赖问题 |
| `Flye` | `20260417T003012Z` | `finished` | 未完成 | 真实入口已确定，但尚未闭环 |
| `trinityrnaseq` | `20260417T003257Z` | `timed_out` | 未完成 | 长时程难例 |
| `v-pipe` | `20260417T010342Z` | `completed` | 完成 | 形成自动完成正例 |
| `covid-19-signal` | `20260417T012910Z` | `completed` | 完成 | 形成自动完成正例 |
| `fieldbioinformatics` | `20260417T014050Z` | `completed` | 完成 | 形成自动完成正例 |

### 10.2 已有实验 B：`spades` 失败模式演化

该实验已形成完整的个案叙事，可直接作为论文核心案例。

可支持的关键结论：

- 早期失败首先来自 shell/execute 能力缺失
- 恢复 shell 后，问题转移为“进入真实执行过慢”
- 进入真实构建后，问题变成具体可修正的工程错误
- 手工延续工作区最终形成了 `Succeeded` 正例证据

### 10.3 已有实验 C：Harness 原型有效性

当前 harness 原型已具备以下方法学能力：

- explicit surfaces
- baseline variant
- candidate variant
- proposer workspace
- `train/holdout` split
- keep/discard decision
- final report

这部分即使尚未做出大量 candidate 对比，也足以支撑“方法实现已经成立”的论文叙述。

## 11. 待补做实验

以下实验尚未全部完成，但非常适合写入论文的“实验设计”部分，并在后续有时间时继续补数据。

### 11.1 计划实验 P1：SWE-bench Lite 通用能力验证实验

目的：

- 引入一个权威但实验成本相对可控的公开 benchmark，验证 agent 在通用软件工程仓库修复场景下的能力

设计：

- 选择 `SWE-bench Lite` 作为通用能力评测集
- 不必一开始跑全量，优先选取 20 到 50 题代表性子集
- 统一使用当前 one-shot 或等价非交互执行路径
- 记录每题是否成功生成补丁、是否通过测试、是否解决 issue，以及总耗时

预期结论：

- 即便在不做大规模调参的情况下，`SWE-bench Lite` 也能为论文提供“通用软件工程能力”这一层的权威补充证据

### 11.2 计划实验 P2：shell 能力消融实验

目的：

- 验证 shell 能力是否是重型仓库进入真实执行路径的系统性前提

设计：

- 选择 `spades`
- 对比开启与关闭 shell 能力的 one-shot 运行
- 观察是否进入真实 `docker build`、`docker run` 和 Cromwell 执行

预期结论：

- 不暴露 shell 时，智能体大概率停留在阅读和规划阶段

### 11.3 计划实验 P3：执行策略 prompt surface 对比

目的：

- 验证“尽快进入最短真实执行路径”的 prompt 是否优于开放式仓库阅读 prompt

设计：

- 在相同仓库集合上比较两版 `one_shot_prompt`
- 记录首次真实构建时间、完成数与超时数

预期结论：

- 强制收敛到最短真实执行路径的 prompt 更适合高成本仓库任务

### 11.4 计划实验 P4：完成判定规则对比

目的：

- 验证 evidence-backed completion judgment 是否能减少伪阳性

设计：

- 对比“输出包含 `COMPLETED` 即完成”与“多源证据完成判定”
- 在历史 run 上回放检查两种口径的标签差异

预期结论：

- 弱判定会将部分“只做了准备工作”的运行误记为完成

### 11.5 计划实验 P5：运行预算对比实验

目的：

- 验证 30 分钟是否只是工程预算，而非任务本质上限

设计：

- 对 `canu`、`megahit`、`trinityrnaseq` 至少选择其中 2 个仓库
- 比较 30 分钟与 60 分钟预算下的结果

预期结论：

- 部分重仓库的失败可能是预算不足而非能力不足

### 11.6 计划实验 P6：Harness variant 泛化实验

目的：

- 验证某个 candidate variant 在 `holdout` 上是否仍有效

设计：

- 在 `train` 上观察失败模式并修改 surfaces
- 同时报告 `train` 与 `holdout` 结果
- 使用当前 keep/discard 规则决定是否接受 candidate

预期结论：

- 只在 `train` 上变好但在 `holdout` 上不变或退化的 variant 不应接受

### 11.7 计划实验 P7：proposer 外环替换实验

目的：

- 验证从当前 `[proposer].command` smoke contract 迁移到更完整的 DeepAgents proposer 后，是否能带来更稳定的 surface 修改质量

设计：

- 保持同一组 surfaces、同一组仓库 split
- 对比当前 smoke proposer 与更完整 proposer 的 candidate 质量

预期结论：

- 更完整 proposer 可能提升候选修改的可解释性与迭代有效性

## 12. 工作进度安排

参考开题报告样例中的“工作进度安排”表格，后续论文与实验可以按下面的方式推进。已完成和待完成部分可以共存在一张表中，写论文时也更自然。

| 序号 | 阶段任务 | 状态 | 时间安排建议 |
| --- | --- | --- | --- |
| 1 | 整理系统目标、研究问题与仓库任务列表 | 已完成 | 2026-04 中旬 |
| 2 | 完成 one-shot runner 标准化与结果持久化 | 已完成 | 2026-04 中旬 |
| 3 | 收集 `spades`、`canu`、`megahit` 等 baseline 证据 | 已完成基础部分 | 2026-04 中旬 |
| 4 | 完成 harness 原型与 thesis method 草稿 | 已完成 | 2026-04 中下旬 |
| 5 | 补写论文总大纲、实验设计与章节框架 | 已完成 | 2026-04-19 |
| 6 | 补做 SWE-bench Lite 子集评测 | 待完成 | 2026-04 下旬 |
| 7 | 补做 shell 消融、预算对比、completion 规则对比实验 | 待完成 | 2026-04 下旬 |
| 8 | 补做 harness candidate/holdout 对比实验 | 待完成 | 2026-04 下旬到 2026-05 上旬 |
| 9 | 完成第 3 章与第 5 章正文初稿 | 待完成 | 2026-05 上旬 |
| 10 | 完成第 1 章、第 2 章和结论部分 | 待完成 | 2026-05 中旬 |
| 11 | 统一格式、补图表、交叉检查与定稿 | 待完成 | 2026-05 中下旬 |

## 13. 建议写入论文的实验组织方式

为了让论文结构更像正式论文而不是开发日志，建议实验章按以下顺序组织。

1. 先给出实验目标、对象、环境和评价指标。
2. 再给出 `SWE-bench Lite` 与 one-shot baseline 的双层评测结构。
3. 然后用 `spades` 作为深度个案分析失败模式。
4. 接着说明 harness 框架与 variant 评估机制。
5. 最后列出已完成实验与待补做实验，并在结尾写“当前已验证什么、仍需补什么”。

## 14. 预留图表清单

下面这些图表最适合后续继续补做。

| 编号建议 | 图表内容 | 当前是否可做 |
| --- | --- | --- |
| 表 5-1 | 仓库任务列表与难度特征 | 可做 |
| 表 5-2 | one-shot 结果总表 | 可做 |
| 表 5-3 | SWE-bench Lite 子集结果表 | 需补实验 |
| 表 5-4 | `spades` 演化时间线 | 可做 |
| 表 5-5 | 不同 completion 判定口径对比 | 需补整理 |
| 表 5-6 | harness baseline/candidate 结果对比 | 需补 candidate 实验 |
| 图 5-1 | 各仓库完成状态柱状图 | 可做 |
| 图 5-2 | 失败类型分布图 | 需人工归类 |
| 图 5-3 | SWE-bench Lite 子集 resolved 比例图 | 需补实验 |
| 图 5-4 | 30 分钟与 60 分钟预算对比图 | 需补实验 |

## 15. 写作时的口径约束

后续正式写实验章时，建议统一遵守以下口径。

- 明确区分“自动 one-shot 完成”与“手工延续工作区完成”
- 明确区分“已有证据”与“计划补做实验”
- 不把工程上尚未稳定的 candidate 夸大为已经验证的通用结论
- 对于尚未完成的实验，以“实验设计”或“后续计划验证”表述，而不要写成既成事实

## 16. 当前最推荐的论文实验主线

如果时间有限，只保留一条最强的实验叙事，建议采用下面这版。

1. 用 one-shot 总表给出整体结果全景。
2. 用 `spades` 证明失败模式是逐层暴露的，而不是任务本质不可做。
3. 用 completion judgment 说明为什么需要证据化评估。
4. 用 harness 方法说明为什么要把 prompt 调参变成 surface-based variant 优化。
5. 用 1 到 2 个待补做实验说明后续可验证方向。

这条主线最稳，也最符合你当前仓库里已经形成的证据密度。
