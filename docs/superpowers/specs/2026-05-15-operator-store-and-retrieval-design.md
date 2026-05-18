# Operator Store And Retrieval Design

## Goal

先把算子入库管理与检索做好，并保持设计足够简单，方便后续再接入
`benchmark` 的自动选择逻辑。

这份设计只覆盖两件事：

- 算子最重要信息应该如何入库
- 算子库应该如何支持结构化检索、全文检索，并为后续 embedding
  检索预留接口

这份设计暂不规定 `benchmark register` 的最终选算子策略；它只要求后续
`benchmark` 可以稳定复用这里定义的存储与搜索接口。

## Current Problem

当前 `operator_store` 已经能把 `benchmark` 与 `github2workspace` 结果写成
manifest，并在 `index.sqlite` 中维护查询元数据。但当前模型更像
"run-level artifact store"，还不适合长期算子管理：

- 同一算子会因为不同 `run_id` 产生多条看起来像不同算子的记录
- 算子定义与单次验证结果混在同一个 manifest 中
- 搜索只支持结构化字段过滤，不支持全文或自然语言搜索
- 现有 store 更适合保留证据，不适合作为后续稳定复用的算子主目录

## Design Principles

- manifest-first：文件仍然是 canonical source，SQLite 只是可重建索引
- stable identity：算子身份不依赖 `run_id`
- execution evidence preserved：每次运行验证结果保留为独立记录
- simple first：先支持结构化过滤和全文搜索，再接 embedding
- benchmark-independent：先不把存储结构绑死到 benchmark 的选择逻辑上

## Core Model

### 1. Operator Record

表示一个稳定算子的主记录，描述"这个算子是什么"。

必须字段：

- `operator_id`
- `family`
- `name`
- `version`
- `summary`
- `wdl_path`
- `inputs_json_path`
- `dockerfile_path` or `image_ref`
- `entry_workflow`
- `input_media_types`
- `output_media_types`
- `tags`
- `source_repo`

推荐字段：

- `aliases`
- `description`
- `expected_outputs`
- `runtime_backend`
- `resource_hints`
- `source_commit`
- `example_inputs`
- `example_outputs`
- `dataset_hints`

说明：

- `wdl_path`、`inputs_json_path`、`dockerfile_path` / `image_ref` 是当前最核心
  的可执行三件套
- `summary`、`input_media_types`、`output_media_types`、`tags` 是当前最核心
  的可检索信息

### 2. Validation Record

表示一次针对某个算子的实际验证结果，描述"这个算子最近跑得怎么样"。

必须字段：

- `validation_id`
- `operator_id`
- `version`
- `run_id`
- `status`
- `created_at`
- `run_dir`

推荐字段：

- `dataset_id`
- `validation_summary`
- `artifacts`
- `metrics`
- `runtime_image`
- `wdl_path`
- `inputs_json_path`
- `failure_reason`

`status` 初版建议统一为：

- `registered`
- `registered_ready`
- `docker_validated`
- `completed`
- `partial`
- `blocked`
- `failed`

## Storage Layout

建议把 `operator_store/` 调整为下面的形状：

```txt
operator_store/
├── operators/
│   └── <operator_id>/
│       ├── operator.json
│       ├── versions/
│       │   └── <version>.json
│       └── validations/
│           └── <run_id>.json
└── index.sqlite
```

文件职责：

- `operator.json`
  - 稳定主记录
  - 面向检索与管理
- `versions/<version>.json`
  - 版本特有信息
  - 例如某版 workflow、runtime、compatibility 信息
- `validations/<run_id>.json`
  - 单次运行证据
  - 面向可追溯性与后续排序

## SQLite Index

初版索引建议拆为 4 张主表：

- `operators`
  - `operator_id`, `family`, `name`, `version`, `summary`, `source_repo`,
    `validation_status`, `updated_at`
- `operator_io`
  - `operator_id`, `direction`, `media_type`, `name`, `required`
- `operator_tags`
  - `operator_id`, `tag`
- `operator_validations`
  - `validation_id`, `operator_id`, `version`, `run_id`, `status`,
    `dataset_id`, `created_at`, `run_dir`, `summary`

如果 SQLite 可用 FTS5，增加：

- `operator_fts`
  - `operator_id`, `name`, `summary`, `description`, `tags_text`,
    `io_text`, `source_repo`

说明：

- `operators.validation_status` 不是替代全部验证记录，而是聚合后的当前主状态
- `operator_validations` 保留完整历史，便于后面做最近成功率或 freshness 排序

## Search Interface

对外统一一个搜索接口，不暴露底层是 FTS 还是 embedding：

```python
search_operators(
    query: str | None = None,
    family: str | None = None,
    input_media_type: str | None = None,
    output_media_type: str | None = None,
    status: str | None = None,
    tags: list[str] | None = None,
    limit: int = 20,
)
```

### Phase 1

先实现：

- 结构化过滤
- SQLite FTS5 全文搜索
- 简单排序：`text_score + status_bonus + recency_bonus`

### Phase 2

后续再扩展：

- canonical text 生成
- embedding 入库
- hybrid retrieval：结构化过滤 + FTS + semantic recall

注意：Phase 2 不改变对外搜索接口。

## Canonical Search Text

为后续全文与 embedding 检索，建议为每个算子生成一段 canonical text。

建议拼接来源：

- `name`
- `aliases`
- `summary`
- `description`
- `family`
- `tags`
- `input_media_types`
- `output_media_types`
- `expected_outputs`
- `source_repo`

明确不直接把整份 WDL、整份 `inputs.json`、整份 Dockerfile 原文塞进索引文档，
避免：

- 噪音过大
- 索引膨胀
- 检索命中偏向低价值模板文本

更合适的做法是提取它们的结构化摘要字段进入 canonical text。

## Migration Strategy

从当前实现迁移时，建议保留现有 manifest-first 路径，并分两步迁移：

1. 继续写现有 `operator_product.json`
2. 同时新增稳定 `operator.json` 与 `validations/<run_id>.json`

这样可以：

- 不破坏现有 supervisor artifact 约定
- 让旧的 benchmark / github2workspace 运行结果继续可追溯
- 逐步把检索入口切到新的聚合索引

## Non-Goals For This Iteration

- 不在这一轮定义 benchmark 最终选算子算法
- 不在这一轮引入独立向量数据库
- 不在这一轮做复杂 rerank 或学习排序
- 不把算子库设计扩展成完整 workflow marketplace

## Recommended Next Step

下一步实现应优先做三件事：

1. 在 `operator_store.py` 中拆出 operator record 与 validation record
2. 把现有 run-level manifest 写入逻辑扩展为稳定主记录 + 验证记录
3. 在 SQLite 上补 `operator_fts` 与统一 `search_operators()` 接口
