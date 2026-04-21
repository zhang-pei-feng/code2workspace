# 能力快照问题集（索引）

这份索引用于快速查看 capability snapshot 覆盖了哪些能力点，以及对应的 case 文件名。

> 运行：`uv run --project libs/cli python experiments/skill_tests/runner.py --date <YYYYMMDD> --case <case>.toml`

## 论文检索

- `capability-snapshot-01-academic-pubmed-latest.toml`  
  问题：在 PubMed 上帮我找几篇关于 sars-cov2 疫苗药物研究的文献。
- `capability-snapshot-02-academic-high-impact.toml`  
  问题：找几篇 sars-cov2 疫苗药物研究的最新论文，以 nature 等高影响因子的结果为主。
- `capability-snapshot-03-academic-biorxiv-latest.toml`  
  问题：找几篇 bioarxiv 上的 sars-cov2 疫苗药物研究的最新论文。

## 本地变异风险数据库

- `capability-snapshot-04-virus-antibody-hotspots.toml`  
  问题：新冠病毒S蛋白上哪些位点的突变最容易逃逸抗体？
- `capability-snapshot-05-virus-site-484-501.toml`  
  问题：484位点和501位点的所有可能突变及其风险评分是什么？

## 官方监测数据源

- `capability-snapshot-06-monitor-who-covid.toml`  
  问题：用 respiratory-disease-data-fetcher 技能，讲一下 WHO 的最新新冠疫情情况，最近一个月全球有多少感染病例，最近七天感染病例最多的国家是哪个？
- `capability-snapshot-07-monitor-china-cdc.toml`  
  问题：用 respiratory-disease-data-fetcher 技能，最近一个月中国新冠病毒的诊疗量和确诊病例，重症病例分别是多少？有哪些变异株？

## 数据治理 Ops

- `capability-snapshot-08-governance-ncbi-virus.toml`  
  任务：刷新 `ncbi_virus` 最新 snapshot，并给出记录概览与质量问题（显式 command 直跑 `governance_ops.py`）。

