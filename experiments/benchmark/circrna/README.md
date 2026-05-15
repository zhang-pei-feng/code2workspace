# circRNA Benchmark Cases

这个目录里的工具已经收拢到一个任务族里，但它们还没有完全统一到共享数据集层。

## 现状

- 这里的 `Dockerfile` / `workflow.wdl` 基本可视为工具级 case 资产。
- 多数 `input.json` 仍然保留历史机器上的绝对路径或工具作者示例路径。
- 共享数据集入口现在统一收口到：
  - [../datasets/benchmark_catalog.json](/mnt/data1/zhangpf/code2workspace/.worktrees/supervisor-graph-runtime/experiments/benchmark/datasets/benchmark_catalog.json)
  - 重点看：
    - `circrna-hela-rnaser-paired`
    - `circrna-blood-prjna722046`

## 推荐共享数据集

### 1. `circrna-hela-rnaser-paired`

适合大多数 circRNA detection / reconstruction 工具的主共享数据集：

- matched HeLa `ribo-` / `RNase R+` paired-end RNA-seq
- 支持用同一套原始读段去派生：
  - `FASTQ`
  - `SAM/BAM`
  - `unmapped BAM`
  - `junction list`
  - `Bowtie/BWA` 索引
- 适合：
  - `ACValidator`
  - `AutoCirc`
  - `CIRI3`
  - `CircAST`
  - `acfs`
  - `circompara2`
  - `find-circ`

### 2. `circrna-blood-prjna722046`

适合血液场景的独立共享数据集：

- `AQUARIUM-HB` 明确是 human blood circRNA pipeline
- 它的示例文档直接使用 `PRJNA722046 / SRR6450118`
- 因此不建议硬绑到 HeLa / HEK293 这类通用细胞系 benchmark 上

## 建议

- 后续如果把 `cirrna` 真接进 benchmark helper，先接 `circrna-hela-rnaser-paired`。
- `AQUARIUM-HB` 作为血液专用子集单独保留，不和通用检测工具强行共用同一 biological dataset。
