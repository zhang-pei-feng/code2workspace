# 算子库与 Benchmark 比对历史库设计说明

本文用比较直白的方式说明 `code2workspace` 中两个本地数据管理模块：

- `operator_store`：算子库，回答“系统现在有哪些可复用工具/工作流”。
- `benchmark_comparison_history_store`：benchmark 比对历史库，回答“哪些 benchmark 工具在什么输入上已经跑过比对计算，结果能不能复用”。

两者都采用“文件为主、SQLite 为索引”的设计。也就是说，JSON 文件是可追溯的主记录，`index.sqlite` 只是为了快速查询生成的索引，必要时可以从文件重新构建。

## 为什么要拆成两个库

如果只用一个库保存所有内容，很容易把两个问题混在一起：

- 算子定义：这个工具是什么、怎么运行、需要什么输入、产出什么结果。
- 计算结果：某一次具体运行是否成功、用了哪个数据集、输出文件在哪里。

这两类信息的生命周期不同。一个算子可以长期存在，但它会有很多次运行验证；一次计算历史只能说明“在某个输入和某个 workflow 版本下跑过”。因此当前设计把它们拆开：

| 模块 | 主要问题 | 典型使用场景 |
| --- | --- | --- |
| `operator_store` | 有哪些可用算子 | `benchmark register` 从本地库中选择工具 |
| `benchmark_comparison_history_store` | 哪些 benchmark 比对计算已经完成 | benchmark 避免重复运行，report 引用本地比对计算证据 |

## 一、算子库 operator_store

### 1. 设计目标

`operator_store` 管理的是“可复用算子”。这里的算子不只是一个命令名，而是一组可以执行和验证的资产，例如：

- WDL 工作流文件
- `inputs.json` 示例输入
- Dockerfile 或镜像引用
- 输入输出类型
- 指标字段
- 最近一次验证状态
- 历史验证记录

它的目标是让系统不再从零猜测工具怎么跑，而是从本地已有的可运行产物中检索和选择。

### 2. 目录结构

```txt
operator_store/
├── objects/
│   └── <family>/<name>/<version>/operator_product.json
├── operators/
│   └── <operator_id>/
│       ├── operator.json
│       ├── embedding.json
│       ├── versions/
│       │   └── <version>.json
│       └── validations/
│           └── <run_id>.json
└── index.sqlite
```

各目录含义：

| 路径 | 中文说明 |
| --- | --- |
| `objects/` | 保存旧的 run-level manifest，即一次运行产出的原始算子产品记录 |
| `operator_product.json` | 单次运行生成的算子产品清单，保留完整证据来源 |
| `operators/<operator_id>/` | 某个稳定算子的主目录 |
| `operator.json` | 稳定算子主记录，描述“这个算子是什么” |
| `versions/<version>.json` | 某个算子版本的运行资产和版本信息 |
| `validations/<run_id>.json` | 某次运行验证记录，描述“这次跑得怎么样” |
| `embedding.json` | 可选的向量表示，用于语义检索 |
| `index.sqlite` | 可重建查询索引，用于结构化检索、全文检索和可选向量检索 |

### 3. operator_product.json 字段说明

`operator_product.json` 是从一次 benchmark 或 github2workspace 运行中生成的原始产品记录。

| 字段 | 中文注释 |
| --- | --- |
| `schema_version` | 记录格式版本 |
| `product_id` | 本次产品记录的唯一标识，通常包含任务类型、工具名和 run id |
| `operator_id` | 稳定算子标识，不应随每次运行变化 |
| `name` | 算子名称，例如 `spades`、`Flye` |
| `family` | 算子来源或类型，例如 `benchmark`、`github2workspace` |
| `version` | 本次产物版本，当前常用 run id 作为版本 |
| `status` | 本次产物状态，例如 `registered_ready`、`completed`、`partial`、`failed` |
| `summary` | 本次产物或验证结果摘要 |
| `created_at` | 创建时间 |
| `updated_at` | 更新时间 |
| `manifest_path` | 当前 `operator_product.json` 的文件路径 |
| `source` | 来源信息，如 GitHub 仓库、commit、本地 case 目录 |
| `runtime` | 运行方式信息，如 WDL、Docker 镜像、入口 workflow |
| `inputs` | 输入定义列表 |
| `outputs` | 输出定义列表 |
| `metrics` | 指标定义列表 |
| `validation` | 本次运行验证信息 |
| `artifacts` | 与本次产物相关的证据文件路径 |
| `tags` | 检索标签，如 `wdl`、`completed`、`execution-ready` |

### 4. operator.json 字段说明

`operator.json` 是算子库最核心的稳定主记录，面向管理和检索。

| 字段 | 中文注释 |
| --- | --- |
| `schema_version` | 记录格式版本 |
| `operator_id` | 稳定算子标识，例如 `benchmark:spades` |
| `family` | 算子类别或来源 |
| `name` | 算子名称 |
| `version` | 当前记录指向的最新版本 |
| `summary` | 算子简短说明 |
| `description` | 算子较完整说明；没有单独说明时通常复用 summary |
| `source_repo` | 来源仓库 URL |
| `source_commit` | 来源 commit，若未知可为空 |
| `source` | 更完整的来源结构化信息 |
| `runtime` | 运行时配置，包含 WDL、Docker、输入文件等 |
| `inputs` | 输入字段列表 |
| `outputs` | 输出字段列表 |
| `metrics` | 该算子可产出的指标列表 |
| `tags` | 检索标签列表 |
| `input_media_types` | 输入数据类型集合，例如 `file`、`fastq` |
| `output_media_types` | 输出数据类型集合，例如 `file`、`fasta` |
| `expected_outputs` | 预期输出名称列表 |
| `validation_status` | 聚合后的当前验证状态 |
| `latest_validation_id` | 最近一次验证记录 ID |
| `created_at` | 算子主记录创建时间 |
| `updated_at` | 算子主记录更新时间 |
| `operator_path` | 当前 `operator.json` 文件路径 |
| `latest_version_path` | 最新版本记录路径 |
| `latest_validation_path` | 最新验证记录路径 |
| `latest_embedding_path` | 向量记录路径 |
| `latest_product_manifest_path` | 最近一次 run-level 产品清单路径 |
| `canonical_text` | 用于全文和向量检索的规范化文本 |
| `embedding_model` | 如果生成了 embedding，这里记录所用模型 |
| `embedding_dimensions` | embedding 维度 |

### 5. runtime 字段说明

`runtime` 描述算子如何被执行。

| 字段 | 中文注释 |
| --- | --- |
| `backend` | 运行后端，例如 `wdl`、`docker`、`unknown` |
| `image_ref` | Docker 镜像名或镜像引用 |
| `entrypoint` | 原生命令入口，若未知可为空 |
| `entry_workflow` | WDL 入口 workflow 名称 |
| `workflow_path` | WDL 文件路径 |
| `inputs_json_path` | `inputs.json` 文件路径 |
| `dockerfile_path` | Dockerfile 文件路径 |

### 6. inputs / outputs 字段说明

`inputs` 和 `outputs` 都是列表，每个元素描述一个输入或输出。

| 字段 | 中文注释 |
| --- | --- |
| `name` | 输入或输出名称 |
| `media_type` | 数据类型，如 `file`、`fastq`、`fasta`、`json` |
| `schema_path` | 对应 schema 或 WDL 字段路径，若无可为空 |
| `required` | 是否必需 |
| `path` | 示例路径或实际文件路径 |

### 7. metrics 字段说明

`metrics` 是列表，每个元素表示一个可提取或比较的指标。

| 字段 | 中文注释 |
| --- | --- |
| `name` | 指标名称 |
| `type` | 指标类型，例如 `numeric` |
| `description` | 指标含义说明 |

### 8. versions/<version>.json 字段说明

版本记录描述某个版本的算子资产。

| 字段 | 中文注释 |
| --- | --- |
| `schema_version` | 记录格式版本 |
| `operator_id` | 所属稳定算子 ID |
| `version` | 版本号 |
| `name` | 算子名称 |
| `family` | 算子类别 |
| `summary` | 版本摘要 |
| `runtime` | 此版本对应的运行配置 |
| `inputs` | 此版本输入定义 |
| `outputs` | 此版本输出定义 |
| `metrics` | 此版本指标定义 |
| `artifacts` | 此版本相关证据文件 |
| `source` | 此版本来源信息 |
| `created_at` | 创建时间 |
| `updated_at` | 更新时间 |
| `operator_path` | 主记录路径 |
| `version_path` | 当前版本记录路径 |
| `product_manifest_path` | 对应 run-level 产品清单路径 |

### 9. validations/<run_id>.json 字段说明

验证记录描述某一次运行的验证结果。

| 字段 | 中文注释 |
| --- | --- |
| `schema_version` | 记录格式版本 |
| `validation_id` | 验证记录唯一标识 |
| `operator_id` | 所属稳定算子 ID |
| `family` | 算子类别 |
| `name` | 算子名称 |
| `version` | 验证对应版本 |
| `run_id` | 运行 ID |
| `status` | 运行验证状态 |
| `dataset_id` | 数据集标识 |
| `run_dir` | 原始运行目录 |
| `summary` | 验证摘要 |
| `created_at` | 验证记录创建时间 |
| `artifacts` | 本次验证相关文件 |
| `metrics` | 本次验证涉及的指标 |
| `runtime` | 本次验证使用的运行配置 |
| `validation_path` | 当前验证记录路径 |
| `product_manifest_path` | 对应产品清单路径 |

### 10. index.sqlite 主要表说明

`index.sqlite` 是查询加速层，可以从 JSON 文件重建。

| 表名 | 中文说明 |
| --- | --- |
| `operator_records` | 算子主表，保存稳定算子的核心字段 |
| `operator_record_io` | 输入输出索引表，用于按输入/输出类型过滤 |
| `operator_record_runtime` | 运行配置索引表 |
| `operator_record_metrics` | 指标索引表 |
| `operator_record_tags` | 标签索引表 |
| `operator_record_validations` | 验证历史索引表 |
| `operator_record_fts` | FTS5 全文检索表，可选 |
| `operator_record_embeddings` | embedding 存储表 |
| `operator_record_vec` | sqlite-vec 向量检索表，可选 |
| `operator_store_meta` | 索引元信息，如 embedding 模型和维度 |

### 11. 算子检索方式

算子库对外提供统一的 `search_operators` / `search` 能力，主要过滤字段包括：

| 参数 | 中文说明 |
| --- | --- |
| `query` | 自然语言或关键词查询 |
| `family` | 限制算子类别 |
| `input_media_type` | 限制输入类型 |
| `output_media_type` | 限制输出类型 |
| `metric_name` | 限制指标名称 |
| `status` | 限制验证状态 |
| `tag` / `tags` | 限制标签 |
| `limit` | 返回数量上限 |

检索流程可以理解为：

1. 先用结构化条件缩小范围。
2. 如果有 `query`，优先走 SQLite FTS5 全文检索。
3. 如果配置了 embedding，再补充语义检索结果。
4. 合并文本结果和语义结果，返回最相关的候选算子。

## 二、Benchmark 比对历史库 benchmark_comparison_history_store

### 1. 设计目标

`benchmark_comparison_history_store` 保存的是历史 benchmark 比对计算结果。它不回答“工具怎么运行”，而回答：

- 某个工具以前是否在相同输入上跑成功过？
- 当时使用的 workflow 和 inputs 是什么？
- 输出文件和分析结果在哪里？
- 这条历史记录能否作为当前任务的证据或复用结果？

这能避免重复执行昂贵任务，也能让报告任务引用本地已经产生过的计算证据。

### 2. 目录结构

```txt
benchmark_comparison_history_store/
├── records/
│   └── <repo>/<run_id>/
│       ├── benchmark_result_record.json
│       └── embedding.json
└── index.sqlite
```

各路径含义：

| 路径 | 中文说明 |
| --- | --- |
| `records/` | 历史比对计算记录目录 |
| `records/<repo>/<run_id>/` | 某个工具在某次 benchmark 运行中的历史比对结果目录 |
| `benchmark_result_record.json` | 历史比对计算主记录 |
| `embedding.json` | 可选向量记录，用于语义检索 |
| `index.sqlite` | 可重建查询索引 |

### 3. benchmark_result_record.json 字段说明

这是 benchmark 比对历史库的主记录。

| 字段 | 中文注释 |
| --- | --- |
| `schema_version` | 记录格式版本 |
| `record_id` | 历史比对计算记录唯一标识 |
| `repo` | 工具或仓库名称，例如 `spades`、`Flye` |
| `operator_id` | 对应的稳定算子 ID |
| `dataset_key` | 数据集标识，用于判断是否属于同一数据集 |
| `workflow_signature` | workflow 签名，用于判断 WDL 或工作流是否一致 |
| `input_signature` | 输入签名，用于判断输入文件和参数是否一致 |
| `success` | 本次历史运行是否成功 |
| `returncode` | 进程返回码 |
| `run_id` | 原始运行 ID |
| `run_dir` | 原始运行目录 |
| `case_dir` | 原始 benchmark case 目录 |
| `workflow_path` | 当时使用的 WDL 路径 |
| `inputs_json_path` | 当时使用的输入 JSON 路径 |
| `status_path` | 当时的 `run/status.json` 路径 |
| `wdl_status_path` | 当时的 `wdl/status.json` 路径 |
| `result_manifest_path` | 当时的结果清单路径 |
| `analysis_path` | 当时的分析结果 JSON 路径 |
| `result_files` | 可复用的实际输出文件列表 |
| `status_payload` | 当时运行状态文件的内容快照 |
| `wdl_status_payload` | 当时 WDL 状态文件的内容快照 |
| `result_manifest` | 当时结果清单的内容快照 |
| `analysis_payload` | 当时分析 JSON 的内容快照 |
| `analysis_markdown` | 当时分析 Markdown 的内容快照 |
| `canonical_text` | 用于全文和语义检索的规范化文本 |
| `record_path` | 当前历史记录文件路径 |
| `updated_at` | 记录更新时间 |

### 4. embedding.json 字段说明

当启用 embedding 时，每条历史记录可以生成一个向量文件。

| 字段 | 中文注释 |
| --- | --- |
| `schema_version` | 记录格式版本 |
| `record_id` | 对应历史记录 ID |
| `model` | 生成向量所用模型 |
| `source_text_sha256` | 被向量化文本的哈希，用于判断是否需要重新生成 |
| `source_text` | 被向量化的规范化文本 |
| `vector` | embedding 向量 |
| `updated_at` | 向量更新时间 |

### 5. index.sqlite 主要表说明

| 表名 | 中文说明 |
| --- | --- |
| `benchmark_records` | 历史计算记录主索引表 |
| `benchmark_record_embeddings` | 历史记录 embedding 索引表 |

`benchmark_records` 的主要查询字段包括：

| 字段 | 中文说明 |
| --- | --- |
| `record_id` | 历史记录 ID |
| `repo` | 工具名 |
| `operator_id` | 稳定算子 ID |
| `dataset_key` | 数据集标识 |
| `workflow_signature` | workflow 签名 |
| `input_signature` | 输入签名 |
| `success` | 是否成功 |
| `returncode` | 返回码 |
| `run_id` | 运行 ID |
| `run_dir` | 原始运行目录 |
| `case_dir` | case 目录 |
| `workflow_path` | workflow 路径 |
| `inputs_json_path` | 输入 JSON 路径 |
| `status_path` | 运行状态路径 |
| `wdl_status_path` | WDL 状态路径 |
| `result_manifest_path` | 结果清单路径 |
| `analysis_path` | 分析结果路径 |
| `canonical_text` | 检索文本 |
| `record_path` | 主记录路径 |
| `updated_at` | 更新时间 |

### 6. Benchmark 比对历史检索参数

benchmark 比对历史库提供 `search_records`，常用过滤参数如下：

| 参数 | 中文说明 |
| --- | --- |
| `query` | 自然语言或关键词查询 |
| `repo` | 限制工具名 |
| `operator_id` | 限制稳定算子 ID |
| `dataset_key` | 限制数据集 |
| `workflow_signature` | 限制 workflow 签名 |
| `input_signature` | 限制输入签名 |
| `success_only` | 是否只返回成功记录，默认是 |
| `limit` | 返回数量上限 |

检索时先用结构化条件过滤，再根据 `canonical_text` 和可选 embedding 对候选记录排序。

### 7. 历史结果复用规则

benchmark case 执行前会尝试复用历史结果。复用不是只看工具名，而是分层判断：

1. 不能复用当前 run 自己产生的记录。
2. 历史记录必须是成功记录。
3. 如果当前 case 有 `workflow_signature`，历史记录必须完全一致。
4. 如果当前 case 有 `input_signature`，历史记录输入签名一致才优先复用。
5. 如果输入签名无法严格匹配，才使用 `dataset_key` 作为兜底判断。

复用命中后，系统会在当前 case 下重新生成这些文件：

| 文件 | 中文说明 |
| --- | --- |
| `run/status.json` | 当前 case 的复用运行状态，包含 `execution_mode = history_reuse` |
| `run/result_manifest.json` | 从历史记录恢复的结果清单 |
| `analysis.json` | 从历史记录恢复的分析结果 |
| `analysis.md` | 从历史记录恢复的 Markdown 分析 |
| `wdl/status.json` | 从历史记录恢复的 WDL 状态 |
| `run/reused_result_record.json` | 说明本次结果复用了哪条历史记录 |

这样当前 benchmark 仍然能产出完整 evidence，而不需要重新跑一遍昂贵计算。

## 三、两个库在系统流程中的关系

可以把完整流程理解为：

```txt
已有运行产物
  ↓
operator_store 记录“可用工具”
  ↓
benchmark register 从算子库选择候选工具
  ↓
benchmark case 执行
  ↓
benchmark_comparison_history_store 记录“这次比对计算结果”
  ↓
后续 benchmark 可复用结果，report 可引用结果作为本地证据
```

更具体地说：

| 阶段 | 使用的库 | 作用 |
| --- | --- | --- |
| 注册 benchmark 工具 | `operator_store` | 按任务语义、输入输出类型、状态和标签选择算子 |
| 执行 benchmark case 前 | `benchmark_comparison_history_store` | 查找是否已有可复用成功比对结果 |
| 执行 benchmark case 后 | `benchmark_comparison_history_store` | 保存新的成功比对计算记录 |
| 总结 benchmark 产物 | `operator_store` | 把可运行 case 继续沉淀为可复用算子 |
| 生成 report | `benchmark_comparison_history_store` | 把历史比对计算结果作为本地结构化证据 |

## 四、设计优点

这套设计有几个直接好处：

- 可追溯：核心记录都在 JSON 文件里，论文和实验复查时能直接定位证据。
- 可重建：SQLite 只是索引，坏了可以从文件重建。
- 可复用：算子库复用“工具能力”，比对历史库复用“benchmark 比对计算结果”。
- 可扩展：先支持结构化和全文检索，再平滑接入 embedding 和向量检索。
- 边界清楚：算子定义不会被单次运行结果污染，历史结果也不会伪装成新的算子。

## 五、当前实现入口

| 文件 | 中文说明 |
| --- | --- |
| `libs/cli/code2workspace_cli/operator_store.py` | 算子库实现，包括 manifest 写入、稳定记录生成、SQLite 索引、全文和向量检索 |
| `libs/cli/code2workspace_cli/benchmark_result_store.py` | benchmark 比对历史库实现，包括历史记录写入、检索和 embedding 支持；模块名保留旧称以兼容代码 |
| `libs/cli/code2workspace_cli/supervisor_runtime.py` | Supervisor benchmark 流程中调用两个库的地方 |
| `docs/overview/supervisor-agent-function-flows.zh.md` | Supervisor 总体流程说明，包含两个库在系统中的位置 |
