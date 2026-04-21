# Benchmark Datasets

这个目录是本地 benchmark skill 的统一数据集入口。

## 结构

- `benchmark_catalog.json`
  - benchmark skill 读取的 registry
- `downloads/`
  - 后续由 code2workspace 智能体或人工下载的真实数据集目录

## 使用约定

- benchmark skill 不应把 repo、dataset、workflow 深度硬编码在 Python 里。
- 新增 repo 或新增数据集时，优先修改 `benchmark_catalog.json`。
- code2workspace 智能体执行 benchmark 时，应先查看这个目录，再从
  `downloads/<dataset_key>/` 中选择合适输入。
- 如果 `downloads/<dataset_key>/` 还没有真实文件，智能体可以根据
  registry 里的 `source_urls` 和 `local_candidates` 自行决定下载或复用
  本地现成测试数据。
