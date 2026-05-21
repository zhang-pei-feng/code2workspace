# 算子库、数据集库与 Benchmark 比对历史库设计说明

本文用比较直白的方式说明 `code2workspace` 里三块最重要的本地证据库：

- `operator_store`：算子库，回答“现在有哪些可复用工具 / 工作流”。
- `dataset_store`：数据集库，回答“有哪些可复用输入数据 / 输入包”。
- `benchmark_comparison_history_store`：benchmark 比对历史库，回答“哪些 benchmark 比对计算已经跑过，结果能不能复用”。

三者都采用同一种主思路：**文件为主，SQLite 为索引**。JSON 文件是可追溯的主记录，`index.sqlite` 只是快速查询层，坏了可以从文件重建。

## 为什么要拆成三库

这三个问题其实不是一件事：

- 算子定义：这个工具是什么、怎么跑、能产出什么。
- 数据集定义：这个工具要拿什么输入跑，输入包是什么结构。
- 运行历史：某次具体执行是否成功，是否能复用，输出在哪里。

把它们拆开后，系统就能更清楚地区分三种资产：

| 模块 | 主要问题 | 典型使用场景 |
| --- | --- | --- |
| `operator_store` | 有哪些可用算子 | `benchmark register` 从本地库中选择工具 |
| `dataset_store` | 有哪些可用输入数据 / 输入包 | benchmark 注册时匹配输入，generic/report 计算时挑选本地数据 |
| `benchmark_comparison_history_store` | 哪些 benchmark 比对计算已经完成 | benchmark 避免重复运行，report 引用本地比对计算证据 |

## 总体关系

可以把完整流程理解为：

```txt
已有运行产物 / 样本输入
  ↓
operator_store 记录“可用工具”
dataset_store 记录“可用输入”
benchmark_comparison_history_store 记录“已发生的比对计算”
  ↓
runtime / supervisor 在这三者之间做匹配、复用和证据拼装
```

系统里的本地计算逻辑通常按这个顺序思考：

1. 先看有没有可复用的 `existing_data`。
2. 如果需要新计算，再从 `operator_store` 里选一个能做事的算子。
3. 再从 `dataset_store` 里选一个合适的数据集或输入包。
4. 如果是 benchmark 场景，再查 `benchmark_comparison_history_store` 看是否已有可复用结果。

---

## 一、算子库 `operator_store`

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

### 3. 写入模型

当前 `operator_store` 是 **manifest-first**：

1. 先写 `operator_product.json`。
2. 再根据这份 manifest 归一化出 `operator.json`、`versions/<version>.json`、`validations/<run_id>.json`。
3. 如果 embedding 可用，再写 `embedding.json`。
4. 最后把这些内容同步进 SQLite。

这意味着：

- 文件是事实来源。
- 索引只是查询副本。
- 同一算子的不同版本和不同验证记录都能挂在同一个稳定 `operator_id` 下。

### 4. `operator_product.json` 字段

`operator_product.json` 是一次运行的原始产品记录，通常来自 benchmark 注册或 github2workspace 产物。

| 字段 | 中文注释 |
| --- | --- |
| `schema_version` | 记录格式版本 |
| `product_id` | 本次产品记录的唯一标识，通常包含任务类型、工具名和 run id |
| `operator_id` | 稳定算子标识，不应随每次运行变化 |
| `name` | 算子名称，例如 `spades`、`Flye` |
| `family` | 算子来源或类型，例如 `benchmark`、`github2workspace` |
| `version` | 本次产物版本，常用 run id |
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

### 5. `operator.json` 字段

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
| `input_media_types` | 输入数据类型集合 |
| `output_media_types` | 输出数据类型集合 |
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
| `false_positive` | github2workspace 评估里是否被判定为 false positive |
| `completion_level` | github2workspace 的完成层级 |
| `unsupported_claims` | 最终回答中被判定为不成立的说法 |
| `required_evidence_missing` | 还缺哪些关键证据 |

### 6. runtime / inputs / outputs / metrics

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

`inputs` 和 `outputs` 都是列表，每个元素描述一个输入或输出。

| 字段 | 中文注释 |
| --- | --- |
| `name` | 输入或输出名称 |
| `media_type` | 数据类型，如 `file`、`fastq`、`fasta`、`json` |
| `schema_path` | 对应 schema 或 WDL 字段路径，若无可为空 |
| `required` | 是否必需 |
| `path` | 示例路径或实际文件路径 |

`metrics` 是列表，每个元素表示一个可提取或比较的指标。

| 字段 | 中文注释 |
| --- | --- |
| `name` | 指标名称 |
| `type` | 指标类型，例如 `numeric` |
| `description` | 指标含义说明 |

### 7. `versions/<version>.json` 和 `validations/<run_id>.json`

版本记录描述某个版本的算子资产，验证记录描述某一次运行的验证结果。

这两个文件的作用是把“稳定算子”拆成两层：

- `versions/` 说“这一版有什么资产”。
- `validations/` 说“这一版在某次运行里表现如何”。

这样既能保留历史，也不会把每次运行的噪声直接写死到主记录里。

### 8. SQLite 索引

`index.sqlite` 是查询加速层，可以从 JSON 文件重建。

主要表如下：

| 表名 | 中文说明 |
| --- | --- |
| `operator_records` | 算子主表，保存稳定算子的核心字段 |
| `operator_record_io` | 输入输出索引表，用于按输入 / 输出类型过滤 |
| `operator_record_runtime` | 运行配置索引表 |
| `operator_record_metrics` | 指标索引表 |
| `operator_record_tags` | 标签索引表 |
| `operator_record_validations` | 验证历史索引表 |
| `operator_record_fts` | FTS5 全文检索表，可选 |
| `operator_record_embeddings` | embedding 存储表 |
| `operator_record_vec` | sqlite-vec 向量检索表，可选 |
| `operator_store_meta` | 索引元信息，如 embedding 模型和维度 |

### 9. 检索方式

`operator_store` 对外提供统一的 `search` / `search_operators`。

常用过滤字段包括：

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

检索流程是：

1. 先用结构化条件缩小范围。
2. 如果有 `query`，优先走 SQLite FTS5 全文检索。
3. 如果配置了 embedding，再补充语义检索结果。
4. 合并文本结果和语义结果，返回最相关的候选算子。

### 10. 具体用途

在当前系统里，`operator_store` 主要承担两件事：

- benchmark register 时找候选工具。
- github2workspace / benchmark 完成后，把可复用的产物沉淀成稳定算子。

---

## 二、数据集库 `dataset_store`

### 1. 设计目标

`dataset_store` 保存的是“可复用输入数据 / 输入包”。它解决的问题和算子库不同：

- 这个计算需要什么数据？
- 这些数据是 fasta、fastq、csv，还是别的输入包？
- 它和哪些算子兼容？
- 有没有已知的标签、域、来源说明、文件列表？

它的目标是让系统在做本地计算时，不只知道“能跑什么算子”，还知道“用什么数据跑”。

### 2. 目录结构

```txt
dataset_store/
├── datasets/
│   └── <dataset_id>/
│       ├── dataset.json
│       └── embedding.json
└── index.sqlite
```

各路径含义：

| 路径 | 中文说明 |
| --- | --- |
| `datasets/` | 数据集记录目录 |
| `datasets/<dataset_id>/dataset.json` | 数据集主记录 |
| `datasets/<dataset_id>/embedding.json` | 可选向量记录，用于语义检索 |
| `index.sqlite` | 可重建查询索引 |

### 3. 写入模型

`DatasetStore.write_dataset()` 的行为和算子库一致：

1. 先写 `dataset.json`。
2. 归一化字段后写入 SQLite。
3. 如可用则生成 `embedding.json`。

它支持两种来源：

- 人工或脚本写入的 dataset manifest。
- 从已有 workspace / benchmark 资产整理出来的输入包记录。

### 4. `dataset.json` 字段

`dataset.json` 是数据集主记录。

| 字段 | 中文注释 |
| --- | --- |
| `schema_version` | 记录格式版本 |
| `dataset_id` | 数据集标识 |
| `name` | 数据集名称 |
| `version` | 数据集版本 |
| `domain` | 领域，例如 `genome_assembly`、`immune_escape` |
| `source` | 来源说明 |
| `license` | 许可信息 |
| `summary` | 简短摘要 |
| `files` | 文件清单 |
| `tags` | 标签 |
| `compatible_operator_ids` | 兼容算子列表 |
| `canonical_text` | 用于检索的规范化文本 |
| `record_path` | 当前记录路径 |
| `updated_at` | 更新时间 |

`files` 里的单个元素通常包含：

| 字段 | 中文注释 |
| --- | --- |
| `name` | 文件别名 |
| `role` | 文件角色，例如 `input_fasta`、`metadata` |
| `media_type` | 媒体类型，例如 `fastq`、`fasta`、`csv` |
| `uri` | 文件路径或资源 URI |
| `sha256` | 文件校验值，若有则写入 |
| `size_bytes` | 文件大小，若有则写入 |

### 5. 规范化文本

`canonical_text` 是数据集检索的核心。

它会把这些内容串起来：

- dataset_id
- name
- version
- domain
- summary
- source
- tags
- compatible_operator_ids
- 文件元信息

这样无论用关键词检索还是语义检索，都能把“数据本身描述”连同“它适配什么算子”一起召回。

### 6. SQLite 索引

`dataset_store` 的索引结构更轻，但足够支撑本地检索：

| 表名 | 中文说明 |
| --- | --- |
| `dataset_records` | 数据集主表 |
| `dataset_files` | 文件明细表 |
| `dataset_tags` | 标签表 |
| `dataset_compatible_operators` | 兼容算子关系表 |
| `dataset_record_embeddings` | embedding 存储表 |

还有几个常用索引：

- `domain`
- `media_type`
- `tag`

### 7. 检索方式

`DatasetStore.search_datasets()` 也是“结构化过滤 + 文本 / 语义排序”的模式。

过滤参数包括：

| 参数 | 中文说明 |
| --- | --- |
| `query` | 自然语言或关键词查询 |
| `dataset_id` | 精确限定数据集 |
| `domain` | 限定领域 |
| `media_type` | 限定文件类型 |
| `tag` | 限定标签 |
| `limit` | 返回上限 |

检索流程是：

1. 先按 `dataset_id`、`domain`、`media_type`、`tag` 做结构化过滤。
2. 如果有 `query`，先对候选记录做文本匹配。
3. 再尝试 embedding 语义分数。
4. 以文本分数和语义分数混合排序，返回前 `limit` 条。

### 8. embedding 机制

`dataset_store` 的 embedding 处理有三个层级：

1. 优先用 OpenAI 兼容 `/embeddings`。
2. 再回退到上层封装的 embedding 适配器。
3. 如果都不可用，再回退到本地 hash embedding。

这使得数据集库在离线、受限或网关能力不完整时仍可工作，只是语义质量会下降。

### 9. 兼容算子关系

`compatible_operator_ids` 很关键，它不是装饰字段，而是调度提示。

它告诉系统：

- 这个数据集理论上能喂给哪些算子。
- benchmark register 时可以减少盲搜。
- local computation 时可以直接给 worker 一个更窄的候选范围。

### 10. 具体用途

当前 `dataset_store` 主要用于：

- benchmark 注册时，和算子库一起选“工具 + 输入包”。
- report / generic 的 local computation 里，优先找现成的数据证据。
- 让已整理过的输入包成为可复用资产，而不是散落在 workspace 里的临时文件。

---

## 三、Benchmark 比对历史库 `benchmark_comparison_history_store`

### 1. 设计目标

`benchmark_comparison_history_store` 保存的是历史 benchmark 比对计算结果。它不回答“工具怎么运行”，也不回答“输入是什么”，而是回答：

- 某个工具以前是否在相同输入上跑成功过？
- 当时使用的 workflow 和 inputs 是什么？
- 输出文件和分析结果在哪里？
- 这条历史记录能否作为当前任务的证据或复用结果？

它的主要价值是避免重复执行昂贵任务，也让 report 任务可以引用本地已经产生过的计算证据。

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

### 3. `benchmark_result_record.json` 字段

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
| `canonical_text` | 用于全文和语义检索的规范化文本 |
| `record_path` | 当前历史记录文件路径 |
| `updated_at` | 记录更新时间 |

### 4. `embedding.json` 字段

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

### 5. SQLite 索引

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

### 6. 检索方式

`benchmark_comparison_history_store` 提供 `search_records()`。

常用过滤参数如下：

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

### 8. 当前实现里的一个补充

现在的 Supervisor runtime 会在历史库为空时，先尝试从已有 run 产物里回填历史记录。也就是说，历史库不是一个孤立数据库，而是可以从 workspace 里的现有证据反向补出来的。

---

## 四、三个库在系统流程中的关系

可以把它们想成三层：

| 层 | 库 | 作用 |
| --- | --- | --- |
| 工具层 | `operator_store` | 记录“能做什么” |
| 输入层 | `dataset_store` | 记录“拿什么做” |
| 历史层 | `benchmark_comparison_history_store` | 记录“以前怎么做过” |

一个完整的本地计算 / benchmark 决策通常是：

1. 从 `operator_store` 找可执行算子。
2. 从 `dataset_store` 找兼容数据集或输入包。
3. 从 `benchmark_comparison_history_store` 找是否已有成功比对结果可直接复用。
4. 若需要新跑，再把新结果写回历史库，并在合适的时候沉淀回算子库。

---

## 五、设计优点

这套设计有几个直接好处：

- 可追溯：核心记录都在 JSON 文件里，论文和实验复查时能直接定位证据。
- 可重建：SQLite 只是索引，坏了可以从文件重建。
- 可复用：算子库复用“工具能力”，数据集库复用“输入资产”，历史库复用“已发生的计算结果”。
- 可扩展：先支持结构化和全文检索，再平滑接入 embedding 和向量检索。
- 边界清楚：算子定义、输入定义和运行历史不会互相污染。

---

## 六、当前实现入口

| 文件 | 中文说明 |
| --- | --- |
| `libs/cli/code2workspace_cli/operator_store.py` | 算子库实现，包括 manifest 写入、稳定记录生成、SQLite 索引、全文和向量检索 |
| `libs/cli/code2workspace_cli/dataset_store.py` | 数据集库实现，包括 dataset 写入、兼容算子关系、SQLite 索引、全文和向量检索 |
| `libs/cli/code2workspace_cli/benchmark_result_store.py` | benchmark 比对历史库实现，包括历史记录写入、检索和 embedding 支持；模块名保留旧称以兼容代码 |
| `libs/cli/code2workspace_cli/supervisor_runtime.py` | Supervisor benchmark / report / generic 流程中调用这三库的地方 |
| `docs/overview/supervisor-agent-function-flows.zh.md` | Supervisor 总体流程说明，包含三库在系统中的位置 |
