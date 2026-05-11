# 免疫逃逸 Benchmark Cases

这个目录与病毒组装不同，当前不是一类单模态任务，而是几种输入形态混合在一起：

- 结构预测
- 蛋白序列表征
- 结构/复合物打分
- 对接
- 逃逸/ACE2 结合 DMS 表

## 现状

- 工具级 `Dockerfile` / `WDL` 已经在这里。
- 但它们的 `input.json` 仍然主要指向旧绝对路径或作者示例数据。
- 如果继续沿用“一个 FASTQ 目录喂所有工具”的思路，会把 benchmark 做得不诚实。

## 推荐共享数据集层

共享数据集现在收口到：

- [../datasets/benchmark_catalog.json](/mnt/data1/zhangpf/code2workspace/.worktrees/supervisor-graph-runtime/experiments/benchmark/datasets/benchmark_catalog.json)

重点是三套：

### 1. `immune-escape-rbd-functional-dms`

- SARS-CoV-2 RBD ACE2 binding / expression DMS 表
- 更适合：
  - `esm`
  - 结构/序列模型后的功能校验

### 2. `immune-escape-rbd-antibody-escape`

- mutation-level / site-level antibody escape maps
- 更适合：
  - escape 评分
  - 变异影响排序
  - 结构/序列模型后的 escape 对照

### 3. `immune-escape-covabdab-structural-bundle`

- CoV-AbDab CSV
- PDB 结构打包
- 代表性 RBD-antibody complex
- 可派生：
  - antibody heavy/light FASTA
  - RBD FASTA
  - PDB / PDBQT

更适合：

- `ImmuneBuilder`
- `AutoDock-Vina`
- `esm`
- `ImaPEp`

## 建议

- 后续如果把这组正式接进 benchmark helper，按“两层共享数据集”来做：
  - `DMS 表型层`
  - `结构/序列层`
- `AutoDock-Vina` 只适合挂在结构层，不适合反过来定义整个免疫逃逸 benchmark。
