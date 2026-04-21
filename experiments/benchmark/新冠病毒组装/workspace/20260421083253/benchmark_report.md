# Benchmark report

主结果目录：`/mnt/data1/zhangpf/code2workspace/results/skills/benchmark-workflow-orchestrator/20260421-covid-assembly-benchmark`
补充成功结果目录：`/mnt/data1/zhangpf/code2workspace/results/skills/benchmark-workflow-orchestrator/local-eight-repo-benchmark`

## 复用的数据集

1. `short-read-ecoli-srr001666`（SPAdes, MEGAHIT）
   - `/mnt/data1/zhangpf/code2workspace/experiments/benchmark/datasets/downloads/short-read-ecoli-srr001666/SRR001666_1.fastq.gz`
   - `/mnt/data1/zhangpf/code2workspace/experiments/benchmark/datasets/downloads/short-read-ecoli-srr001666/SRR001666_2.fastq.gz`
2. `long-read-ecoli-pacbio`（Canu, Flye）
   - `/mnt/data1/zhangpf/code2workspace/results/real-tests/canu/pacbio.fastq`
3. `trinity-rnaseq-srr390728`（TrinityRNASeq）
   - `/mnt/data1/zhangpf/code2workspace/.workspaces/oneshot/trinityrnaseq/sample_data/test_Trinity_Assembly/reads.left.fq.gz`
   - `/mnt/data1/zhangpf/code2workspace/.workspaces/oneshot/trinityrnaseq/sample_data/test_Trinity_Assembly/reads.right.fq.gz`
4. `sars-cov-2-illumina-sra`（covid-19-signal）
   - `/mnt/data1/zhangpf/code2workspace/.workspaces/oneshot/covid-19-signal/results/docker_test/real_input/E15_R1.fastq.gz`
   - `/mnt/data1/zhangpf/code2workspace/.workspaces/oneshot/covid-19-signal/results/docker_test/real_input/E15_R2.fastq.gz`
5. `ebov-amplicon-flongle`（fieldbioinformatics）
   - `/mnt/data1/zhangpf/code2workspace/.workspaces/oneshot/fieldbioinformatics/test-data/MT007544`

## 工具状态

| 工具 | 状态 | 关键产物 | 备注 |
|---|---|---|---|
| SPAdes | 成功（有完整历史成功结果）；本轮部分失败 | `/mnt/data1/zhangpf/code2workspace/results/skills/benchmark-workflow-orchestrator/local-eight-repo-benchmark/cases/spades/run/repo_native_output/contigs.fasta` ; `/mnt/data1/zhangpf/code2workspace/results/skills/benchmark-workflow-orchestrator/20260421-covid-assembly-benchmark/cases/spades/wdl/contigs.fasta` | 本轮 repo-native 失败，原因是镜像里 `/app/bin/spades.py` 不存在；但同数据集的历史完整 benchmark 已成功 |
| Canu | 成功 | `/mnt/data1/zhangpf/code2workspace/results/skills/benchmark-workflow-orchestrator/20260421-covid-assembly-benchmark/cases/canu/run/repo_native_output/ecoli.report` ; `/mnt/data1/zhangpf/code2workspace/results/real-tests/canu/ecoli-pacbio/ecoli.contigs.fasta` | repo-native 成功，WDL 也有真实产物 |
| MEGAHIT | 成功 | `/mnt/data1/zhangpf/code2workspace/results/skills/benchmark-workflow-orchestrator/20260421-covid-assembly-benchmark/cases/megahit/run/repo_native_output/final.contigs.fa` ; `/mnt/data1/zhangpf/code2workspace/results/skills/benchmark-workflow-orchestrator/20260421-covid-assembly-benchmark/cases/megahit/wdl/final.contigs.fa` | 与 SPAdes 共享同一 E. coli 短读长数据 |
| Flye | 失败（有部分产物） | `/mnt/data1/zhangpf/code2workspace/results/skills/benchmark-workflow-orchestrator/20260421-covid-assembly-benchmark/cases/Flye/run/repo_native_output/assembly.fasta` ; `/mnt/data1/zhangpf/code2workspace/results/skills/benchmark-workflow-orchestrator/20260421-covid-assembly-benchmark/cases/Flye/run/repo_native_output/assembly_info.txt` | 运行到 polishing 阶段失败，缺失 `40-polishing/consensus_1.fasta` |
| TrinityRNASeq | 成功 | `/mnt/data1/zhangpf/code2workspace/results/skills/benchmark-workflow-orchestrator/20260421-covid-assembly-benchmark/cases/trinityrnaseq/run/trinity_benchmark_output.Trinity.fasta` ; `/mnt/data1/zhangpf/code2workspace/results/skills/benchmark-workflow-orchestrator/20260421-covid-assembly-benchmark/cases/trinityrnaseq/wdl/Trinity.fasta` | 非基因组装配，不与其余工具直接横向比较 |
| covid-19-signal | 失败/外部阻塞 | `/mnt/data1/zhangpf/code2workspace/results/skills/benchmark-workflow-orchestrator/20260421-covid-assembly-benchmark/cases/covid-19-signal/docker/build.log` | docker build 依赖在线 `git clone` pangoLEARN，443 连接失败 |
| fieldbioinformatics | 失败/环境阻塞 | `/mnt/data1/zhangpf/code2workspace/results/skills/benchmark-workflow-orchestrator/20260421-covid-assembly-benchmark/cases/fieldbioinformatics/wdl/cromwell_run.log` ; `/mnt/data1/zhangpf/code2workspace/.workspaces/oneshot/fieldbioinformatics/test-data/consensus-sequences/MT007544.consensus.medaka.fasta` | WDL 实际失败，容器里 `artic: command not found` |

## 可比较的核心指标

### 1) 共享短读长数据：SPAdes vs MEGAHIT
- SPAdes（完整成功 run）
  - contig_count = 344
  - assembly_size = 4,559,369
  - n50 = 72,373
- MEGAHIT（当前 run）
  - contig_count = 472
  - assembly_size = 4,530,520
  - n50 = 18,360
- 结论：在同类 E. coli 短读长数据上，SPAdes 连续性明显更好（更少 contig、更高 N50），MEGAHIT 成功率也高，但结果更碎片化。

### 2) 共享长读长数据：Canu vs Flye
- Canu（当前 run）
  - contig_count = 1
  - assembly_size = 4,665,301
  - n50 = 4,665,301
- Flye（失败前产物）
  - contig_count = 4
  - assembly_size = 4,994,494
  - n50 = 3,597,263
- 结论：Canu 在这组 PacBio 数据上更稳，直接得到单 contig；Flye 虽然生成了 assembly.fasta，但最终 polishing 阶段崩溃，稳定性不足。

### 3) 其他工具
- TrinityRNASeq：成功产出 82 条 transcript，assembly_size 129,423，可证明 RNA-seq 流程能通。
- covid-19-signal：主要问题不是数据，而是镜像构建强依赖外网 GitHub。
- fieldbioinformatics：镜像存在，但运行环境不完整，缺少 `artic` 可执行文件；属于镜像/路径封装问题，不是数据问题。

## 总结

- 成功拿到真实可用 benchmark 结果的工具：`SPAdes`、`Canu`、`MEGAHIT`、`TrinityRNASeq`。
- 失败或受阻的工具：`Flye`、`covid-19-signal`、`fieldbioinformatics`。
- 最有价值的复用比较是两组：
  - 同一短读长数据：`SPAdes vs MEGAHIT`
  - 同一长读长数据：`Canu vs Flye`
- 当前环境下最稳的装配工具是 `Canu`；短读长组装里 `SPAdes` 质量优于 `MEGAHIT`；病毒流程的主要问题集中在镜像可重现性和离线依赖封装，而不是输入数据本身。
