# Generic Experience Skill Evolution Plan

## 目标

把 generic harness 从“只改 prompt/guidance surface”推进到“持续积累 case，
把经验沉淀为可检索、可蒸馏、可复用的 skill”，让 generic 编排能力通过
经验库逐步进化。

## 核心思路

分成三层：

1. 稳定 skill 层  
   继续保留 `.code2workspace/skills/orchestration/supervisor-guidance/`
   里的长期规则与 family/node guidance。

2. 经验记录层  
   新增 `.code2workspace/skills/orchestration/generic-experience/records/*.json`，
   每条记录保留一条 accepted generic case 的抽象经验。

3. 蒸馏 skill 层  
   由经验记录自动生成
   `.code2workspace/skills/orchestration/generic-experience/generated/generic_orchestration_experience.md`，
   作为 generic planner 的附加 skill 片段。

## 经验记录字段

每条 `GenericOrchestrationExperienceRecord` 记录：

- `problem_classification`
  - `task_family`
  - `intent`
  - `evidence_mode`
  - `complexity`
  - `scope`
- `problem_abstraction`
  - `summary`
  - `constraints`
  - `tags`
- `problem_instance`
  - `prompt_excerpt`
  - `abstracted_instance`
- `trajectory`
  - `graph_shape`
  - `node_ids`
  - `round_count`
  - `node_count`
  - `tool_rhythm`
  - `stop_rule`
  - `answer_style`
  - `evidence_pattern`
- `trajectory_explain`
- `trajectory_effect`
  - `acceptance`
  - `case_score`
  - `split_mean_score`
  - `traceability_score`
  - `evidence_score`
  - `efficiency_score`
  - `completion_level`
  - `completion_status`
  - `source_url_count`
  - `findings`
  - `score_delta_vs_previous`
- `applicability`
  - `use_when`
  - `avoid_when`
- `confidence`

## 当前实现

### 1. Experience store

新增 `libs/cli/code2workspace_cli/generic_experience_store.py`：

- experience record schema
- JSON record load/write
- accepted case -> experience record 构建
- experience -> distilled guidance 重建
- 任务文本 -> top-k 匹配经验检索

### 2. Harness exporter

generic harness 在 candidate 被 accepted 后：

- 读取 accepted candidate 的 train/holdout case 结果
- 打开对应 `generic_trace_summary.json`
- 构建 experience record
- 写入 `generic-experience/records/`
- 重建 `generated/generic_orchestration_experience.md`

这让经验库随着 accepted case 自然增长。

### 3. Runtime guidance injection

generic worker prompt 现在除了原有 `generic_qa` family guidance 外，还会：

- 读取蒸馏后的 generic experience guidance
- 根据当前 task 检索 top-k matching experiences
- 把这些经验以 planning hints 的形式注入 prompt

注入规则是“用于编排，不用于直接回答”。

## 为什么这样做

相比直接持续改 `generic_qa.md`：

- 保留了 case-level 可审计经验
- 经验与稳定规则分层，避免 skill 文件不断膨胀
- generic 可以按任务检索更相关的经验，而不是全量吞下历史规则
- harness 既能继续优化稳定 guidance surface，也能持续积累经验 skill

## 当前限制

当前版本还是第一版：

- 经验匹配目前主要是规则 + 词项重叠，不是 embedding retrieval
- 蒸馏 guidance 仍偏“高分经验摘要”，还不是更抽象的长期原则学习
- 只对 accepted candidate 写经验；尚未把 rejected 经验做成负例库
- 还没有周期性把高置信经验再反向蒸馏回 `supervisor-guidance` 的慢回路

## 后续方向

1. 为经验检索加入 embedding / SQLite 索引
2. 区分正例经验和负例经验
3. 增加更强的 abstraction / applicability 归纳
4. 定期从高置信 experience record 归纳出新的稳定 generic guidance
