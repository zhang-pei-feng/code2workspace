# 能力快照（输入输出）

- 日期：`20260420`
- 总 case 数：`8`
- 通过：`4`
- 已知问题：`0`
- 基础设施阻塞：`0`
- 行为回归：`3`
- Runner 错误：`1`

## capability-snapshot-01-academic-pubmed-latest

- 目标：`skill`
- 状态：`passed`
- 结论：行为与输出均满足预期。
- 日志：`/mnt/data1/zhangpf/code2workspace/results/skill-tests/20260420/capability-snapshot-01-academic-pubmed-latest.log`

### 输入

```text
在 PubMed 上帮我找几篇关于 SARS-CoV-2 疫苗与抗病毒药物研究的最新文献。请给出题目、年份/发表日期、期刊/预印本来源、链接（PMID/DOI/URL）和一句摘要。不要用普通网页搜索。
```

### 输出（最终回答，过滤 tool trace）

```text
进度：已确认应使用 academic-search skill 的 PubMed 模式；接下来并行检索疫苗与抗病毒药物最新文献。并行检索 2 个主题：SARS-CoV-2 疫苗、SARS-CoV-2 抗病毒药物；优先取较新的 PubMed 结果并带摘要细节。已拿到首批结果；我先筛掉不够贴题的记录，再补一轮更聚焦的 PubMed 查询，确保都是 SARS-CoV-2 疫苗/抗病毒药物研究。下面是基于 **PubMed 检索**筛到的几篇较新的 SARS-CoV-2 **疫苗**与**抗病毒药物**研究文献；我尽量选了主题更贴近“疫苗/药物研究”本身的条目。

### 疫苗研究
1. **Correlates of severe and delta COVID-19 in a phase 3 trial of the AZD1222 vaccine.**  
   - **日期**：2026-04-18  
   - **来源**：NPJ Vaccines  
   - **链接**：PMID 42000737；DOI 10.1038/s41541-026-01411-1；https://pubmed.ncbi.nlm.nih.gov/42000737/  
   - **一句摘要**：该 3 期 AZD1222 试验分析显示，接种后抗 Spike IgG 和中和抗体滴度越高，重症 COVID-19 风险越低。

2. **Immunosenescence and CMV-Associated Immune Signatures on SARS-CoV-2 Booster Responses.**  
   - **日期**：2026-04-17  
   - **来源**：The Journals of Gerontology. Series A, Biological Sciences and Medical Sciences  
   - **链接**：PMID 41999211；DOI 10.1093/gerona/glag095；https://pubmed.ncbi.nlm.nih.gov/41999211/  
   - **一句摘要**：这项研究发现第四剂双价 BNT162b2 能稳定提升体液免疫，但细胞免疫增强幅度受年龄、既往感染和 CMV 相关免疫衰老影响。

3. **Impact of SARS-CoV-2 vaccination on CD4+ and CD8+ T lymphocyte profiles in an HIV-positive and HIV-negative female cohort.**  
   - **日期**：2026-04-03  
   - **来源**：Laboratory Medicine  
   - **链接**：PMID 42001311；DOI 10.1093/labmed/lmag014；https://pubmed.ncbi.nlm.nih.gov/42001311/  
   - **一句摘要**：在南非女性队列中，SARS-CoV-2 疫苗接种并未显著改变 CD4+/CD8+ T 细胞水平，但 HIV 状态与免疫细胞分布差异相关。

### 抗病毒药物研究
4. **Effectiveness and safety of molnupiravir among patients with mild to moderate COVID-19: a prospective, observational, cohort study.**  
   - **日期**：2026-04-16  
   - **来源**：Scientific Reports  
   - **链接**：PMID 41991956；DOI 10.1038/s41598-026-44971-x；https://pubmed.ncbi.nlm.nih.gov/41991956/  
   - **一句摘要**：这项前瞻性队列研究提示，在既往已有免疫基础的人群中，molnupiravir 对降低住院或死亡的额外获益可能有限。

5. **Effectiveness of oral antivirals in reducing adverse outcomes in asthmatic patients with non-severe COVID-19: A multi-institutional retrospective cohort study.**  
   - **日期**：2026-04-17  
   - **来源**：Medicine  
   - **链接**：PMID 41995569；DOI 10.1097/MD.0000000000048378；https://pubmed.ncbi.nlm.nih.gov/41995569/  
   - **一句摘要**：多机构回顾性研究显示，口服抗病毒药尤其 nirmatrelvir/ritonavir 与哮喘合并非重症 COVID-19 患者较低的不良结局风险相关。

6. **Bayesian reanalysis of early remdesivir for the treatment of COVID-19 in outpatients with high risk of progression to severe disease.**  
   - **日期**：2026  
   - **来源**：PLOS ONE  
   - **链接**：PMID 41990093；DOI 10.1371/journal.pone.0346878；https://pubmed.ncbi.nlm.nih.gov/41990093/  
   - **一句摘要**：对 PINETREE 试验的贝叶斯重分析支持早期使用 remdesivir 可显著降低高风险门诊 COVID-19 患者住院或死亡风险。

7. **Dual antiviral and anti-inflammatory effects of BAY 11-7082 in SARS-CoV-2 infection via inhibition of the canonical NF-κB signaling pathway.**  
   - **日期**：2026-04-16  
   - **来源**：Scientific Reports  
   - **链接**：PMID 41991649；DOI 10.1038/s41598-026-48699-6；https://pubmed.ncbi.nlm.nih.gov/41991649/  
   - **一句摘要**：该研究报道 BAY 11-7082 在 SARS-CoV-2 感染中同时表现出抗病毒和抗炎作用，机制与抑制经典 NF-κB 通路有关。

8. **Potency of Artocarpus Heterophyllus Leaves Extract as an Antiviral against SARS-CoV-2.**  
   - **日期**：2026-04-02  
   - **来源**：The Kobe Journal of Medical Sciences  
   - **链接**：PMID 41991153；DOI 10.24546/0100503458；https://pubmed.ncbi.nlm.nih.gov/41991153/  
   - **一句摘要**：该体外研究显示菠萝蜜叶提取物及其分离组分对 SARS-CoV-2 具有较强抑制活性，提示其中可能存在候选抗病毒分子。

信息来源：
- skill: academic-search (PubMed)

如果你要，我可以继续按 **“更高影响因子优先”** 或 **“只要 2024–2025/2025–2026 的临床研究”** 再精筛一版。
```

## capability-snapshot-02-academic-high-impact

- 目标：`skill`
- 状态：`passed`
- 结论：行为与输出均满足预期。
- 日志：`/mnt/data1/zhangpf/code2workspace/results/skill-tests/20260420/capability-snapshot-02-academic-high-impact.log`

### 输入

```text
在 PubMed 上检索 SARS-CoV-2 疫苗/抗病毒药物研究的最新论文，并尽量限定为 Nature 系/高影响期刊（优先 Nature / Nature Medicine / Nature Communications / Communications Medicine / NPJ Vaccines）。请直接用 academic-search(PubMed) 的结构化检索结果筛选出 3 篇，给出题目、期刊、日期、链接（PMID/DOI/URL）和一句摘要；不要用普通网页搜索。
```

### 输出（最终回答，过滤 tool trace）

```text
已定位到 academic-search 的 PubMed 用法；接着用其结构化检索拿候选结果，再按期刊和时间筛 3 篇。已拿到 PubMed 结构化结果；现在只按结果本身筛“最新 + 期刊优先级高 + 主题确属疫苗/抗病毒”的 3 篇。按 PubMed 结构化检索结果筛出 3 篇，优先保留 Nature 系且主题明确属于 SARS-CoV-2 疫苗/抗病毒研究：

1. **Next-generation inhibitors of SARS-CoV-2 Mpro overcome the deficiencies of Paxlovid**  
   - 期刊：**Nature Communications**  
   - 日期：**2026-04-04**  
   - 链接：PMID **41935038**；DOI **10.1038/s41467-026-71436-6**；PubMed: https://pubmed.ncbi.nlm.nih.gov/41935038/  
   - 一句话摘要：该研究开发了新一代 SARS-CoV-2 主蛋白酶（Mpro）抑制剂，可克服 Paxlovid 在耐药突变和药代动力学方面的不足，并在动物模型中显示出优于 Paxlovid 的抗病毒效果。

2. **YL1004 is a SARS-CoV-2 papain-like protease inhibitor with immunomodulatory and antiviral activity in mice**  
   - 期刊：**Nature Communications**  
   - 日期：**2026-01-26**  
   - 链接：PMID **41587976**；DOI **10.1038/s41467-026-68795-5**；PubMed: https://pubmed.ncbi.nlm.nih.gov/41587976/  
   - 一句话摘要：该文报道口服 PLpro 抑制剂 YL1004 具有跨变异株抗 SARS-CoV-2 活性，还能恢复宿主抗病毒免疫信号，并在小鼠致死感染模型中实现完全保护。

3. **Self-amplifying COVID-19 mRNA vaccination induces longitudinally enhanced antibody function in a Phase 3 trial**  
   - 期刊：**NPJ Vaccines**  
   - 日期：**2026-03-30**  
   - 链接：PMID **41912532**；DOI **10.1038/s41541-026-01431-x**；PubMed: https://pubmed.ncbi.nlm.nih.gov/41912532/  
   - 一句话摘要：这项 3 期试验相关研究显示，自扩增 mRNA 疫苗 ARCT-154 作为加强针可诱导更持久、功能更强且覆盖漂移变异株的抗体反应。

信息来源：
- skill: academic-search (PubMed)
```

## capability-snapshot-03-academic-biorxiv-latest

- 目标：`skill`
- 状态：`runner_error`
- 结论：运行器错误：Timed out after 6 minute(s)
- 日志：`/mnt/data1/zhangpf/code2workspace/results/skill-tests/20260420/capability-snapshot-03-academic-biorxiv-latest.log`

### 输入

```text
请用 academic-search 的 bioRxiv 来源，在最近 14 天的窗口内筛选出 3 篇与 SARS-CoV-2 疫苗或抗病毒药物研究相关的最新预印本。请给出题目、日期、链接（bioRxiv URL/DOI）和一句摘要，并明确标注这是预印本；不要用普通网页搜索。
```

### 输出（最终回答，过滤 tool trace）

```text
已确认 skill 要求：bioRxiv 需按日期窗口抓取，再在结果中筛选主题相关记录。继续检索最近 14 天窗口并过滤 SARS-CoV-2 疫苗/抗病毒药物预印本。上一次窗口日期用了错误范围，已校正为当前环境日期 2026-04-20 的最近 14 天。重新按 bioRxiv 日期窗口检索并筛选相关预印本。检索脚本本身只返回日期窗口内的前 N 条，需要补充检查 bioRxiv API 返回结构，确认是否要做分页/完整过滤，避免漏掉相关预印本。用 bioRxiv API 分页抓取整个 14 天窗口，再按 SARS-CoV-2 + 疫苗/抗病毒药物关键词过滤，避免只看前 100 条而漏掉相关预印本。
```

## capability-snapshot-04-virus-antibody-hotspots

- 目标：`skill`
- 状态：`behavior_regression`
- 结论：存在未满足的行为或输出预期：log:covid_data, log:S蛋白
- 日志：`/mnt/data1/zhangpf/code2workspace/results/skill-tests/20260420/capability-snapshot-04-virus-antibody-hotspots.log`

### 输入

```text
新冠病毒 S 蛋白上哪些位点的突变最容易逃逸抗体？请查询本地风险数据库（例如 ncov_amino_acid_risk / virus_variation）给出证据：列出高风险位点和风险等级/评分，并简要解释这些位点为何容易逃逸。不要查网页。
```

### 输出（最终回答，过滤 tool trace）

```text
已确认本地 skill 的数据库连接和表结构，接着直接查询 `virus_variation.ncov_amino_acid_risk` 提取 S 蛋白高抗体逃逸位点与评分。
```

## capability-snapshot-05-virus-site-484-501

- 目标：`skill`
- 状态：`behavior_regression`
- 结论：存在未满足的行为或输出预期：log:covid_data
- 日志：`/mnt/data1/zhangpf/code2workspace/results/skill-tests/20260420/capability-snapshot-05-virus-site-484-501.log`

### 输入

```text
484 位点和 501 位点的所有可能突变及其风险评分是什么？请基于本地数据库查询给出两个位点的突变谱（至少包含突变形式与抗体逃逸/ACE2 相关风险评分字段），并做简要对比。不要查网页。
```

### 输出（最终回答，过滤 tool trace）

```text
已确认应查 `virus_variation.ncov_amino_acid_risk`，下一步直接提取 S 蛋白 484 和 501 位点的全部替换及 antibody/ace2 风险分。基于本地库 `virus_variation.ncov_amino_acid_risk` 的查询结果，S:484 与 S:501 位点各有 **19 种**替换记录。字段包含：`mutation`、`antibody`、`ace2`、`aminoacid_substitution`。

**484 位点突变谱（E484\*）**
- antibody=2, ace2=2：E484G, E484R
- antibody=2, ace2=0：E484A, E484C, E484D, E484F, E484K, E484N, E484Q, E484S, E484T, E484Y
- antibody=1, ace2=2：E484I, E484L, E484M, E484P, E484V, E484W
- antibody=1, ace2=0：E484H

**501 位点突变谱（N501\*）**
- antibody=2, ace2=0：N501A, N501E, N501F, N501G, N501I, N501K, N501L, N501M, N501P, N501R, N501S, N501T, N501V, N501Y
- antibody=1, ace2=0：N501C, N501D, N501H, N501Q, N501W

**简要对比**
- **抗体逃逸分布**：两者都以 `antibody=2` 为主；501 位点略更集中（14/19），484 位点为 12/19。
- **ACE2 相关风险**：**484 位点明显更突出**，有 8 个突变 `ace2=2`，其中 E484G/E484R 同时具备高抗体逃逸与高 ACE2 风险；**501 位点本库全部为 `ace2=0`**。
- **结论**：按本地风险库，**484 位点更像“兼具免疫逃逸与受体结合风险”的热点位点**；**501 位点更偏向抗体逃逸风险聚集，但未体现 ACE2 风险升高**。

如需，我可以继续把这两个位点结果整理成表格版（含 `aminoacid_substitution` 一并逐条列出）。
```

## capability-snapshot-06-monitor-who-covid

- 目标：`skill`
- 状态：`passed`
- 结论：行为与输出均满足预期。
- 日志：`/mnt/data1/zhangpf/code2workspace/results/skill-tests/20260420/capability-snapshot-06-monitor-who-covid.log`

### 输入

```text
用 respiratory-disease-data-fetcher 技能，讲一下 WHO 的最新新冠疫情情况：最近一个月（近 28 天）全球有多少感染病例？最近七天感染病例最多的国家是哪个？请给出数字与时间窗口口径，并标注信息来源。
```

### 输出（最终回答，过滤 tool trace）

```text
已读技能说明，开始抓取 WHO 最新数据并核对时间窗。已拿到 WHO 概览页；下一步用 WHO 官方 CSV 计算最近完整 7 天各国新增病例，确定病例最多国家。在核对 WHO 可下载周度统计表与概览页的时间差，优先以更晚的官方 CSV 作为“最新”口径。按 WHO 当前可下载的最新周度病例表口径：

- **最近一个月（近 28 天）全球新增感染病例**：**31,341 例**
  - **时间窗口**：**2026-03-02 至 2026-03-29**
  - **口径说明**：WHO 将 “Last 28 days” 定义为**最近 4 个完整流行病学周**；我据 WHO 周度 CSV 取最近 4 个完整周汇总得到该值。

- **最近七天感染病例最多的国家**：**巴西（Brazil），2,282 例**
  - **时间窗口**：**2026-03-23 至 2026-03-29**
  - **口径说明**：WHO 将 “Last 7 days” 定义为**最近 1 个完整流行病学周**；按 WHO 最新周度国家病例表，巴西为该周新增病例最多国家。

补充说明：WHO 概览页当前展示的 “Last 28 days” 仍写到 **2026-02-16 至 2026-03-15、38,516 例**，但 WHO 官方下载数据页提供的周度 CSV 已更新到 **week ending 2026-03-29**。为回答“最新”情况，这里采用**更新时间更晚的 WHO 官方可下载周度数据**。

**信息来源**
- skill: respiratory-disease-data-fetcher（WHO COVID-19 dashboard Cases）https://data.who.int/dashboards/covid19/cases
- skill: respiratory-disease-data-fetcher（WHO COVID-19 dashboard Data 下载页）https://data.who.int/dashboards/covid19/data
- WHO 官方 CSV：`WHO-COVID-19-global-data.csv` 与 `WHO-COVID-19-global-table-data.csv`
```

## capability-snapshot-07-monitor-china-cdc

- 目标：`skill`
- 状态：`behavior_regression`
- 结论：存在未满足的行为或输出预期：tool:fetch_url, log:中国疾控, log:确诊, log:重症
- 日志：`/mnt/data1/zhangpf/code2workspace/results/skill-tests/20260420/capability-snapshot-07-monitor-china-cdc.log`

### 输入

```text
用 respiratory-disease-data-fetcher 技能，最近一个月中国新冠病毒的诊疗量和确诊病例、重症病例分别是多少？有哪些变异株？请按中国疾控发布口径给出要点，并标注信息来源。
```

### 输出（最终回答，过滤 tool trace）

```text

```

## capability-snapshot-08-governance-ncbi-virus

- 目标：`oneshot`
- 状态：`passed`
- 结论：行为与输出均满足预期。
- 日志：`/mnt/data1/zhangpf/code2workspace/results/skill-tests/20260420/capability-snapshot-08-governance-ncbi-virus.log`

### 输入

```text
刷新 ncbi_virus 最新 snapshot，并给出记录概览与质量问题（显式 command 直跑 governance_ops.py）。
```

### 输出（最终回答，过滤 tool trace）

```text
{
  "run_dir": "/mnt/data1/zhangpf/code2workspace/results/skills/data-governance-ops/snapshots/ncbi_virus/20260420T143908Z",
  "source": "ncbi_virus",
  "mode": "live",
  "query": null,
  "record_count": 5,
  "records": [
    {
      "uid": "3275430657",
      "accession": "PZ298256",
      "title": "Severe acute respiratory syndrome coronavirus 2 isolate SARS-CoV-2/human/IND/SARSCoV2_Amrita_Delta_Sgene_VIS05/2021 surface glycoprotein (S) gene, partial cds",
      "organism": "Severe acute respiratory syndrome coronavirus 2",
      "country": "human",
      "collection_date": "",
      "lineage": "",
      "raw": {
        "uid": "3275430657",
        "term": "3275430657",
        "caption": "PZ298256",
        "title": "Severe acute respiratory syndrome coronavirus 2 isolate SARS-CoV-2/human/IND/SARSCoV2_Amrita_Delta_Sgene_VIS05/2021 surface glycoprotein (S) gene, partial cds",
        "extra": "gi|3275430657|gb|PZ298256.1|",
        "gi": 3275430657,
        "createdate": "2026/04/18",
        "updatedate": "2026/04/18",
        "taxid": 2697049,
        "slen": 485,
        "biomol": "genomic",
        "moltype": "rna",
        "topology": "not-set",
        "sourcedb": "insd",
        "subtype": "isolate|host|gb_acronym|country|isolation_source|collection_date",
        "subname": "SARS-CoV-2/human/IND/SARSCoV2_Amrita_Delta_Sgene_VIS05/2021|Homo sapiens|SARS-CoV-2|India: Kerala|nasal swab|2021-09-13",
        "geneticcode": "1",
        "organism": "Severe acute respiratory syndrome coronavirus 2",
        "statistics": "",
        "properties": {
          "na": "1",
          "value": "1"
        },
        "oslt": {
          "indexed": true,
          "value": "PZ298256.1"
        },
        "accessionversion": "PZ298256.1"
      }
    },
    {
      "uid": "3275033959",
      "accession": "PZ298142",
      "title": "Severe acute respiratory syndrome coronavirus 2 isolate SARS-CoV-2/human/USA/CA-LACPHL-AY16315/2026 ORF1ab polyprotein (ORF1ab) and ORF1a polyprotein (ORF1ab) genes, complete cds; surface glycoprotein (S) and ORF3a protein (ORF3a) genes, partial cds; envelope protein (E) and membrane glycoprotein (M) genes, complete cds; ORF6 gene, complete sequence; ORF8 protein (ORF8) gene, partial cds; and nucleocapsid phosphoprotein (N) and ORF10 protein (ORF10) genes, complete cds",
      "organism": "Severe acute respiratory syndrome coronavirus 2",
      "country": "human",
      "collection_date": "",
      "lineage": "",
      "raw": {
        "uid": "3275033959",
        "term": "3275033959",
        "caption": "PZ298142",
        "title": "Severe acute respiratory syndrome coronavirus 2 isolate SARS-CoV-2/human/USA/CA-LACPHL-AY16315/2026 ORF1ab polyprotein (ORF1ab) and ORF1a polyprotein (ORF1ab) genes, complete cds; surface glycoprotein (S) and ORF3a protein (ORF3a) genes, partial cds; envelope protein (E) and membrane glycoprotein (M) genes, complete cds; ORF6 gene, complete sequence; ORF8 protein (ORF8) gene, partial cds; and nucleocapsid phosphoprotein (N) and ORF10 protein (ORF10) genes, complete cds",
        "extra": "gi|3275033959|gb|PZ298142.1|",
        "gi": 3275033959,
        "createdate": "2026/04/17",
        "updatedate": "2026/04/17",
        "taxid": 2697049,
        "slen": 29677,
        "biomol": "genomic",
        "moltype": "rna",
        "topology": "not-set",
        "sourcedb": "insd",
        "projectid": "746690",
        "subtype": "isolate|host|gb_acronym|country|isolation_source|collection_date",
        "subname": "SARS-CoV-2/human/USA/CA-LACPHL-AY16315/2026|Homo sapiens|SARS-CoV-2|USA: California|clinical|2026-03-25",
        "geneticcode": "1",
        "organism": "Severe acute respiratory syndrome coronavirus 2",
        "biosample": "SAMN57334115",
        "statistics": "",
        "properties": {
          "na": "1",
          "value": "1"
        },
        "oslt": {
          "indexed": true,
          "value": "PZ298142.1"
        },
        "accessionversion": "PZ298142.1"
      }
    },
    {
      "uid": "3275033945",
      "accession": "PZ298141",
      "title": "Severe acute respiratory syndrome coronavirus 2 isolate SARS-CoV-2/human/USA/CA-LACPHL-AY16314/2026 ORF1ab polyprotein (ORF1ab) and ORF1a polyprotein (ORF1ab) genes, complete cds; surface glycoprotein (S) and ORF3a protein (ORF3a) genes, partial cds; and envelope protein (E), membrane glycoprotein (M), ORF6 protein (ORF6), ORF7a protein (ORF7a), ORF7b (ORF7b), ORF8 protein (ORF8), nucleocapsid phosphoprotein (N), and ORF10 protein (ORF10) genes, complete cds",
      "organism": "Severe acute respiratory syndrome coronavirus 2",
      "country": "human",
      "collection_date": "",
      "lineage": "",
      "raw": {
        "uid": "3275033945",
        "term": "3275033945",
        "caption": "PZ298141",
        "title": "Severe acute respiratory syndrome coronavirus 2 isolate SARS-CoV-2/human/USA/CA-LACPHL-AY16314/2026 ORF1ab polyprotein (ORF1ab) and ORF1a polyprotein (ORF1ab) genes, complete cds; surface glycoprotein (S) and ORF3a protein (ORF3a) genes, partial cds; and envelope protein (E), membrane glycoprotein (M), ORF6 protein (ORF6), ORF7a protein (ORF7a), ORF7b (ORF7b), ORF8 protein (ORF8), nucleocapsid phosphoprotein (N), and ORF10 protein (ORF10) genes, complete cds",
        "extra": "gi|3275033945|gb|PZ298141.1|",
        "gi": 3275033945,
        "createdate": "2026/04/17",
        "updatedate": "2026/04/17",
        "taxid": 2697049,
        "slen": 29786,
        "biomol": "genomic",
        "moltype": "rna",
        "topology": "not-set",
        "sourcedb": "insd",
        "projectid": "746690",
        "subtype": "isolate|host|gb_acronym|country|isolation_source|collection_date",
        "subname": "SARS-CoV-2/human/USA/CA-LACPHL-AY16314/2026|Homo sapiens|SARS-CoV-2|USA: California|clinical|2026-03-25",
        "geneticcode": "1",
        "organism": "Severe acute respiratory syndrome coronavirus 2",
        "biosample": "SAMN57334117",
        "statistics": "",
        "properties": {
          "na": "1",
          "value": "1"
        },
        "oslt": {
          "indexed": true,
          "value": "PZ298141.1"
        },
        "accessionversion": "PZ298141.1"
      }
    },
    {
      "uid": "3275033932",
      "accession": "PZ298140",
      "title": "Severe acute respiratory syndrome coronavirus 2 isolate SARS-CoV-2/human/USA/CA-LACPHL-AY16313/2026 ORF1ab polyprotein (ORF1ab), ORF1a polyprotein (ORF1ab), surface glycoprotein (S), ORF3a protein (ORF3a), envelope protein (E), membrane glycoprotein (M), ORF6 protein (ORF6), ORF7a protein (ORF7a), ORF7b (ORF7b), ORF8 protein (ORF8), nucleocapsid phosphoprotein (N), and ORF10 protein (ORF10) genes, complete cds",
      "organism": "Severe acute respiratory syndrome coronavirus 2",
      "country": "human",
      "collection_date": "",
      "lineage": "",
      "raw": {
        "uid": "3275033932",
        "term": "3275033932",
        "caption": "PZ298140",
        "title": "Severe acute respiratory syndrome coronavirus 2 isolate SARS-CoV-2/human/USA/CA-LACPHL-AY16313/2026 ORF1ab polyprotein (ORF1ab), ORF1a polyprotein (ORF1ab), surface glycoprotein (S), ORF3a protein (ORF3a), envelope protein (E), membrane glycoprotein (M), ORF6 protein (ORF6), ORF7a protein (ORF7a), ORF7b (ORF7b), ORF8 protein (ORF8), nucleocapsid phosphoprotein (N), and ORF10 protein (ORF10) genes, complete cds",
        "extra": "gi|3275033932|gb|PZ298140.1|",
        "gi": 3275033932,
        "createdate": "2026/04/17",
        "updatedate": "2026/04/17",
        "taxid": 2697049,
        "slen": 29776,
        "biomol": "genomic",
        "moltype": "rna",
        "topology": "not-set",
        "sourcedb": "insd",
        "projectid": "746690",
        "subtype": "isolate|host|gb_acronym|country|isolation_source|collection_date",
        "subname": "SARS-CoV-2/human/USA/CA-LACPHL-AY16313/2026|Homo sapiens|SARS-CoV-2|USA: California|clinical|2026-03-15",
        "geneticcode": "1",
        "organism": "Severe acute respiratory syndrome coronavirus 2",
        "biosample": "SAMN57334099",
        "statistics": "",
        "properties": {
          "na": "1",
          "value": "1"
        },
        "oslt": {
          "indexed": true,
          "value": "PZ298140.1"
        },
        "accessionversion": "PZ298140.1"
      }
    },
    {
      "uid": "3275033919",
      "accession": "PZ298139",
      "title": "Severe acute respiratory syndrome coronavirus 2 isolate SARS-CoV-2/human/USA/CA-LACPHL-AY16312/2026 ORF1ab polyprotein (ORF1ab), ORF1a polyprotein (ORF1ab), surface glycoprotein (S), ORF3a protein (ORF3a), envelope protein (E), membrane glycoprotein (M), ORF6 protein (ORF6), ORF7a protein (ORF7a), ORF7b (ORF7b), ORF8 protein (ORF8), nucleocapsid phosphoprotein (N), and ORF10 protein (ORF10) genes, complete cds",
      "organism": "Severe acute respiratory syndrome coronavirus 2",
      "country": "human",
      "collection_date": "",
      "lineage": "",
      "raw": {
        "uid": "3275033919",
        "term": "3275033919",
        "caption": "PZ298139",
        "title": "Severe acute respiratory syndrome coronavirus 2 isolate SARS-CoV-2/human/USA/CA-LACPHL-AY16312/2026 ORF1ab polyprotein (ORF1ab), ORF1a polyprotein (ORF1ab), surface glycoprotein (S), ORF3a protein (ORF3a), envelope protein (E), membrane glycoprotein (M), ORF6 protein (ORF6), ORF7a protein (ORF7a), ORF7b (ORF7b), ORF8 protein (ORF8), nucleocapsid phosphoprotein (N), and ORF10 protein (ORF10) genes, complete cds",
        "extra": "gi|3275033919|gb|PZ298139.1|",
        "gi": 3275033919,
        "createdate": "2026/04/17",
        "updatedate": "2026/04/17",
        "taxid": 2697049,
        "slen": 29795,
        "biomol": "genomic",
        "moltype": "rna",
        "topology": "not-set",
        "sourcedb": "insd",
        "projectid": "746690",
        "subtype": "isolate|host|gb_acronym|country|isolation_source|collection_date",
        "subname": "SARS-CoV-2/human/USA/CA-LACPHL-AY16312/2026|Homo sapiens|SARS-CoV-2|USA: California|clinical|2026-03-20",
        "geneticcode": "1",
        "organism": "Severe acute respiratory syndrome coronavirus 2",
        "biosample": "SAMN57334097",
        "statistics": "",
        "properties": {
          "na": "1",
          "value": "1"
        },
        "oslt": {
          "indexed": true,
          "value": "PZ298139.1"
        },
        "accessionversion": "PZ298139.1"
      }
    }
  ]
}
{
  "snapshot_path": "/mnt/data1/zhangpf/code2workspace/results/skills/data-governance-ops/snapshots/ncbi_virus/20260420T143908Z/snapshot.json",
  "issue_count": 5,
  "issues": [
    {
      "accession": "PZ298256",
      "code": "missing_collection_date",
      "level": "warning"
    },
    {
      "accession": "PZ298142",
      "code": "missing_collection_date",
      "level": "warning"
    },
    {
      "accession": "PZ298141",
      "code": "missing_collection_date",
      "level": "warning"
    },
    {
      "accession": "PZ298140",
      "code": "missing_collection_date",
      "level": "warning"
    },
    {
      "accession": "PZ298139",
      "code": "missing_collection_date",
      "level": "warning"
    }
  ]
}
```
