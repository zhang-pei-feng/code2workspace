# COVID / assembly benchmark summary

主工作区报告：`/mnt/data1/zhangpf/code2workspace/experiments/benchmark/新冠病毒组装/workspace/20260421090800/benchmark_report.md`

## 说明

- `experiments/benchmark/新冠病毒组装` 当前可见 7 个 case：`spades`、`canu`、`megahit`、`Flye`、`trinityrnaseq`、`covid-19-signal`、`fieldbioinformatics`。
- 第 8 个工具 `v-pipe` 没放在这个 case 目录里，但已有真实 benchmark 结果保存在：
  `results/skills/benchmark-workflow-orchestrator/local-eight-repo-benchmark/cases/v-pipe/`
- 本报告优先使用已有真实 benchmark 产物，不伪造结果。

## 复用数据策略

1. 共享短读长数据：`short-read-ecoli-srr001666`
   - 复用于：`SPAdes`、`MEGAHIT`
2. 共享长读长数据：`long-read-ecoli-pacbio`
   - 复用于：`Canu`、`Flye`
3. 共享 SARS-CoV-2 Illumina 数据：`sars-cov-2-illumina-sra`
   - 复用于：`v-pipe`、`covid-19-signal`
4. 单独数据
   - `TrinityRNASeq`：`trinity-rnaseq-srr390728`
   - `fieldbioinformatics`：`ebov-amplicon-flongle`

## 结果总览

| 工具 | 共享数据 | 状态 | 关键指标/产物 | 备注 |
|---|---|---|---|---|
| SPAdes | short-read-ecoli-srr001666 | 成功（历史完整 run）；当前 WDL 也有产物 | 最佳完整 run：contig_count=344, assembly_size=4,559,369, n50=72,373 | 当前 20260421 run 的 repo-native 失败，但历史完整 benchmark 可用 |
| Canu | long-read-ecoli-pacbio | 成功 | contig_count=1, assembly_size=4,665,301, n50=4,665,301 | 长读长组最稳 |
| MEGAHIT | short-read-ecoli-srr001666 | 成功 | contig_count=472, assembly_size=4,530,520, n50=18,360 | 与 SPAdes 可直接对比 |
| Flye | long-read-ecoli-pacbio | 部分成功/最终失败 | 部分产物：contig_count=4, assembly_size=4,994,494, n50=3,597,263 | polishing 阶段缺失 `40-polishing/consensus_1.fasta` |
| TrinityRNASeq | trinity-rnaseq-srr390728 | 成功 | transcript_count=82, assembly_size=129,423 | RNA-seq transcriptome，不适合和基因组装配直接横比 |
| v-pipe | sars-cov-2-illumina-sra | 失败 | 无最终共识序列 | 统一下载目录与 V-pipe 期望目录结构不一致 |
| covid-19-signal | sars-cov-2-illumina-sra | 失败/阻塞 | 无最终共识序列 | Docker build 依赖在线拉取 pangoLEARN，当前网络失败 |
| fieldbioinformatics | ebov-amplicon-flongle | 失败/环境阻塞 | benchmark 无有效产物 | 容器执行时 `artic: command not found` |

## 可比较分析

### 1. 同一短读长数据：SPAdes vs MEGAHIT

- SPAdes：`344 contigs`, `N50 72,373`, `assembly_size 4,559,369`
- MEGAHIT：`472 contigs`, `N50 18,360`, `assembly_size 4,530,520`

结论：在同一短读长数据上，SPAdes 连续性明显更好；MEGAHIT 也稳定，但结果更碎片化。

### 2. 同一长读长数据：Canu vs Flye

- Canu：`1 contig`, `N50 4,665,301`
- Flye：`4 contigs`, `N50 3,597,263`，但最终失败

结论：Canu 在这组长读长数据上更稳，直接给出单 contig；Flye 有中间结果，但稳定性不足。

### 3. 同一 SARS-CoV-2 Illumina 数据：v-pipe vs covid-19-signal

- `v-pipe`：能启动流程，但要求 `/benchmark-input/<sample>/<date>/raw_data/*.fastq.gz` 这类教程式目录布局；统一 benchmark 数据目录只提供平铺的 `SRR10903401_R1.fastq.gz` 等文件，最终报 `MissingInputException`。
- `covid-19-signal`：主要阻塞不是输入数据，而是镜像构建强依赖外网 `git clone https://github.com/cov-lineages/pangoLEARN.git`；当前 443 连接失败。

结论：这组共享 SARS-CoV-2 数据理论上最有价值，但当前没有拿到可直接比较的最终产物；阻塞主要来自流程封装和依赖管理，而不是数据本身。

## 根因汇总

- `SPAdes` 当前 run：镜像入口 `/app/bin/spades.py` 不存在；历史完整 run 可补足真实结果。
- `Flye`：polishing 阶段缺少 `consensus_1.fasta`。
- `v-pipe`：输入目录结构与流程预期不匹配。
- `covid-19-signal`：Docker build 依赖外网 GitHub/pangoLEARN。
- `fieldbioinformatics`：容器内缺少 `artic` 可执行文件。

## 结论

- 成功获得真实可分析结果的工具：`SPAdes`、`Canu`、`MEGAHIT`、`TrinityRNASeq`。
- 有部分产物但未完整成功：`Flye`。
- 失败/受阻：`v-pipe`、`covid-19-signal`、`fieldbioinformatics`。
- 当前最有价值的共享数据对比有两组：
  - `SPAdes vs MEGAHIT`
  - `Canu vs Flye`
- 如果下一轮要把“同一份 SARS-CoV-2 数据跑尽量多工具”做得更完整，优先要修的是：
  1. 为 `v-pipe` 补齐教程所需目录层级；
  2. 把 `covid-19-signal` 的在线依赖改成离线打包；
  3. 修复 `fieldbioinformatics` 镜像中的 `artic` 安装/路径。