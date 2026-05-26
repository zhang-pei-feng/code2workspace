---
name: virus-variation-query
description: "查询本机 virus_variation MySQL 主库，以及可选 covid19_data 历史镜像中的谱系/导入表。用户说“查数据库/查库/数据库里/SQL/virus_variation/本地变异库/突变风险库/风险表/位点风险/某个位点/高风险突变/抗体逃逸/ACE2/受体结合/受体风险/抗原风险/基质风险/RBD/S蛋白/HA/NA/H3/H1/猴痘基因/变异统计/表结构/字段/多少条记录/毒株/谱系/lineage/strain/PQ.2 在 RBD 区域有哪些氨基酸突变”等，应优先使用本 skill。适合回答基于数据库的变异、突变、位点、基因、型别、风险评分、谱系突变、Pango lineage catalog、导入状态、记录统计和表结构问题；也可作为“变异株/疫苗/免疫逃逸/临床试验/风险研判”多源分析中的本地位点风险和本地谱系突变证据来源。单独使用时不适合纯联网疫情趋势、正式报告生成或普通论文检索。"
metadata: { "openclaw": { "emoji": "🧬", "requires": { "bins": ["mysql"] } } }
---

# Virus Variation Query

查询本机 MySQL 数据库：

- `virus_variation`：主库，包含新冠、流感、猴痘氨基酸位点风险表，以及新冠来源导入、Pango 谱系目录和谱系突变表。
- `covid19_data`：可选历史镜像，只包含部分新冠来源导入和谱系表；除非用户明确要求对照历史镜像，优先查询 `virus_variation`。

## 自然语言触发

优先使用本 skill 的典型说法：

- “查一下数据库里 BA.3.2 的 RBD 位点风险”
- “PQ.2 毒株在 RBD 区域上有哪些氨基酸突变”
- “某个新冠谱系/毒株的 S 蛋白或 RBD 突变能不能从库里查”
- “本地变异库有没有 S 蛋白 484/501 位点的抗体逃逸评分”
- “查一下 BA.2/BA.3 在数据治理库里的 Spike 突变”
- “数据治理智能体那个库里有没有 XFG / BA.3.2 的谱系突变记录”
- “最近一次 pango_lineages / ncbi_virus 导入是否成功”
- “查库统计流感 H3 HA 高抗原风险突变”
- “猴痘某个 gene 的 matrix_risk 高风险位点有哪些”
- “virus_variation 里这张表有多少条/字段是什么”

如果用户问的是最新疫情趋势、WHO/CDC 监测数据，用 `respiratory-disease-data-fetcher`；如果用户问找论文、PubMed、DOI、摘要，用 `academic-search`。

如果用户问的是“某个变异株/谱系是否可能突破疫苗或既往免疫屏障”“针对某个变异株是否有新疫苗或临床试验”“变异株风险研判”等综合问题，不要把本 skill 当作唯一来源，也不要完全跳过本 skill。应把本 skill 的结果作为本地位点风险和本地谱系突变证据之一，同时结合 `academic-search` 的论文/预印本/临床试验证据，以及 `respiratory-disease-data-fetcher` 或官方网页监测数据。若两个本地库都不能回答临床试验状态或最新流行趋势，明确说明限制。

## 数据库连接

### `virus_variation` 风险库

```bash
Host: localhost
Database: virus_variation
User: root (via sudo/auth_socket)
Root/Sudo Password: zhangpf12345
Connection: printf '%s\n' 'zhangpf12345' | sudo -S -p '' mysql -uroot virus_variation -e "SQL"
```

必须使用上面的本机 root/sudo 连接查询 `virus_variation`。旧的 `agent_virus` 用户不存在；不要再使用 `your_user`、`your_password`、`agent_virus` 或旧密码。当前 `root@localhost` 使用 `auth_socket`，直接 `mysql -uroot -p...` 可能失败，应走 `sudo mysql -uroot`。

### `covid19_data` 历史镜像库

```bash
Host: localhost
Database: covid19_data
User: root (via sudo/auth_socket)
Root/Sudo Password: zhangpf12345
Connection: printf '%s\n' 'zhangpf12345' | sudo -S -p '' mysql -uroot covid19_data -e "SQL"
```

`covid19_data` 当前只是谱系/导入表的历史镜像；正常查询谱系突变和导入状态时优先用 `virus_variation` 中的同名表。
  
## 支持的病毒数据

### `virus_variation`

| 表名 | 病毒类型 | 记录数 | 主要字段 |
|------|----------|--------|----------|
| `ncov_amino_acid_risk` | 新冠 SARS-CoV-2 | ~196k | gene, aminoacid_site, ace2, antibody, aminoacid_substitution |
| `flu_variation` | 流感 Influenza | ~524k | reference, gene, ref_aminoacid_site, anti_risk, receptor_risk_23, receptor_risk_26, matrix_risk |
| `mpxv_variation` | 猴痘 MPXV | ~1052k | gene, ref_aminoacid_site, anti_risk, matrix_risk |
| `ncov_source_harvest_runs` | 数据源导入运行记录 | 以本机为准 | run_id, source_id, query_term, fetched_records, stored_records, status, started_at, completed_at |
| `ncov_source_records` | NCBI Virus / SRA 规范化记录 | 以本机为准 | source_id, accession, organism, host, collection_date, country, region, lineage, sequence_length |
| `ncov_lineage_catalog` | Pango lineage catalog | 以本机为准 | lineage, detail_url, most_common_countries, earliest_date, designated_count, assigned_count, description, who_name |
| `ncov_lineage_mutations` | Pango constellation 谱系突变 | 以本机为准 | lineage, definition_name, label, who_name, raw_site, site_type, gene, position_start, ref_residues, alt_residues |

### `covid19_data`

| 表名 | 数据类型 |
|------|----------|
| `ncov_source_harvest_runs` | 数据源导入运行记录 |
| `ncov_source_records` | NCBI Virus / SRA 规范化记录 |
| `ncov_lineage_catalog` | Pango lineage catalog |
| `ncov_lineage_mutations` | Pango constellation 谱系突变 |

本机 MySQL 未发现 `ncov_epietl_reports`、`ncov_epietl_risk_events`、`ncov_epietl_channels` 表；EpiETL 报告和风险事件请使用 `epietl-api` skill。

## 查询规则

1. **只读访问**：仅允许 SELECT 查询，禁止数据修改
2. **结果限制**：探索性查询添加 `LIMIT 100`，大批量扫描需用户确认
3. **参数确认**：病毒类型/位点/阈值不明确时先询问用户
4. **输出格式**：≤20行显示表格，>20行显示摘要+关键记录
5. **不要编造表和字段**：查询前按本文件和 `refs/fields.md` 的字段来写 SQL；不确定时先执行 `SHOW TABLES` / `DESCRIBE 表名`
6. **表分工**：`virus_variation.ncov_amino_acid_risk` 是位点风险表，没有 `lineage`、`strain`、`region`、`mutation` 字段；`virus_variation.ncov_lineage_mutations` 是谱系突变表，可按 `lineage`、`gene`、`position_start`、`raw_site` 查询谱系定义突变，但没有 ACE2/antibody 风险评分。
7. **谱系/毒株查询流程**：用户问“某谱系/毒株有哪些 RBD/S 蛋白突变”时，先查 `virus_variation.ncov_lineage_mutations`；如果命中具体位点，再用 `virus_variation.ncov_amino_acid_risk` 按 `gene='S'` 和 `aminoacid_site` 查风险分数。若主库没有该 lineage，可再查 `covid19_data.ncov_lineage_mutations` 历史镜像；仍无命中时说明本地谱系库未收录，建议使用 PANGO/Nextstrain/论文检索等外部来源补充。
8. **Spike 字段兼容**：`ncov_lineage_mutations.gene` 里 Spike 可能是 `S` 或 `SPIKE`，`raw_site` 可能形如 `S:E484K`、`s:E484K`、`spike:E484K`。查 Spike/RBD 时不要只写 `gene='S'`；优先使用 `(gene IN ('S','SPIKE') OR LOWER(raw_site) LIKE 's:%' OR LOWER(raw_site) LIKE 'spike:%')`，再用 `position_start BETWEEN 319 AND 541` 约束 RBD。

## 常见错误：不要这样做

```bash
# 错误：占位账号、错误库/表/字段
mysql -u your_user -p your_password -e 'SELECT mutation FROM virus_variation WHERE strain="PQ.2" AND region="RBD";'

# 错误：ncov_amino_acid_risk 没有 lineage 字段
printf '%s\n' 'zhangpf12345' | sudo -S -p '' mysql -uroot virus_variation -e "SELECT * FROM ncov_amino_acid_risk WHERE lineage='PQ.2';"

# 错误：把谱系名当成 aminoacid_substitution 风险分数字段来搜
printf '%s\n' 'zhangpf12345' | sudo -S -p '' mysql -uroot virus_variation -e "SELECT * FROM ncov_amino_acid_risk WHERE aminoacid_substitution LIKE '%XFG%';"

# 错误：只查 gene='S'，会漏掉 gene='SPIKE' 或 raw_site='spike:...' 的行
SELECT * FROM ncov_lineage_mutations WHERE lineage='BA.2' AND gene='S';
```

## 常用查询模板

### 新冠高抗体逃逸位点
```sql
SELECT gene, aminoacid_site, CONCAT(ref_aminoacid,aminoacid_site,aminoacid) AS mut,
       ace2, antibody, aminoacid_substitution
FROM ncov_amino_acid_risk 
WHERE gene='S' AND antibody>=2 
ORDER BY antibody DESC LIMIT 20;
```

### 谱系 Spike/RBD 突变
```sql
SELECT lineage, raw_site, site_type, gene, position_start, position_end,
       ref_residues, alt_residues, definition_name, definition_url
FROM ncov_lineage_mutations
WHERE lineage='BA.2'
  AND (gene IN ('S','SPIKE') OR LOWER(raw_site) LIKE 's:%' OR LOWER(raw_site) LIKE 'spike:%')
  AND position_start BETWEEN 319 AND 541
ORDER BY position_start LIMIT 100;
```

命令行执行方式：

```bash
printf '%s\n' 'zhangpf12345' | sudo -S -p '' mysql -uroot virus_variation -e "
SELECT lineage, raw_site, site_type, gene, position_start, ref_residues, alt_residues
FROM ncov_lineage_mutations
WHERE lineage='BA.2'
  AND (gene IN ('S','SPIKE') OR LOWER(raw_site) LIKE 's:%' OR LOWER(raw_site) LIKE 'spike:%')
  AND position_start BETWEEN 319 AND 541
ORDER BY position_start LIMIT 100;
"
```

### 谱系突变 + 风险表联查
先在 `virus_variation.ncov_lineage_mutations` 查 lineage 的 Spike/RBD 位点；再把命中的 `position_start` 代入 `virus_variation.ncov_amino_acid_risk`：

```sql
SELECT gene, aminoacid_site,
       CONCAT(ref_aminoacid, aminoacid_site, aminoacid) AS mut,
       ace2, antibody, aminoacid_substitution
FROM ncov_amino_acid_risk
WHERE gene='S' AND aminoacid_site IN (405, 493)
ORDER BY aminoacid_site, antibody DESC, ace2 DESC LIMIT 100;
```

### 数据治理库：导入状态
```sql
SELECT run_id, source_id, query_term, status, fetched_records, stored_records,
       started_at, completed_at
FROM ncov_source_harvest_runs
ORDER BY started_at DESC LIMIT 20;
```

### 流感高抗原风险位点
```sql
SELECT ref_aminoacid_site, CONCAT(ref_aminoacid,ref_aminoacid_site,aminoacid) AS mut,
       anti_risk, receptor_risk_26, matrix_risk
FROM flu_variation 
WHERE reference='A-seg4_H3' AND anti_risk>=2 
ORDER BY anti_risk DESC LIMIT 20;
```

### 猴痘综合高风险位点
```sql
SELECT gene, ref_aminoacid_site, CONCAT(ref_aminoacid,ref_aminoacid_site,aminoacid) AS mut,
       anti_risk, matrix_risk
FROM mpxv_variation 
WHERE anti_risk>=2 AND matrix_risk>=2 
ORDER BY anti_risk DESC LIMIT 20;
```

## 辅助脚本

| 脚本 | 功能 | 示例用法 |
|------|------|----------|
| `scripts/site.sh` | 特定位点查询 | `./site.sh ncov S 484 501` |
| `scripts/risk.sh` | 高风险突变筛选 | `./risk.sh flu 2` |
| `scripts/stats.sh` | 统计汇总 | `./stats.sh mpxv` |

## 参考文档

- **字段详解**：[fields.md](refs/fields.md) - 数据库字段含义说明
- **查询示例**：[queries.md](refs/queries.md) - SQL 查询模板集合
