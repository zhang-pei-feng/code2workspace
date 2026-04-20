# 能力快照（输入输出）

- 日期：`20260421`
- 总 case 数：`12`
- 通过：`10`
- 已知问题：`0`
- 基础设施阻塞：`0`
- 行为回归：`0`
- Runner 错误：`2`

## covid-monitoring-01-next-covid-flu-peak

- 目标：`question`
- 状态：`passed`
- 结论：行为与输出均满足预期。
- 日志：`experiments/skill_tests/runs/covid-monitoring-questions/20260421/covid-monitoring-01-next-covid-flu-peak.log`

### 输入

```text
下一波新冠/流感阳性率的高峰会在什么时间？
```

### 输出（最终回答，过滤 tool trace）

```text
读取完本地监测技能说明，下一步抓取近期官方阳性率/监测趋势，再据此给出带不确定性的时间判断。继续抓取中国疾控的流感周报和急性呼吸道哨点监测，优先用中国官方数据判断“下一波”时间窗。为避免只看近两周噪声，再补一轮去年同期中国新冠与冬季流感走势，做季节性对照。按目前中国疾控最新监测看，**下一波流感阳性率高峰更可能在 2026 年冬季（大致 11 月下旬到 2027 年 1 月）**；**下一波新冠阳性率高峰更可能在 2026 年晚春到初夏（大致 4–6 月）**。  
依据是：当前 2026 年第14–15周流感阳性率仍高但已从 **16.3% 降到 15.3%**，属于春季尾段；而新冠在哨点门急诊流感样病例中的阳性率仅 **2.0%→1.8%**，整体处低位。再对照去年中国疾控数据，2025 年新冠阳性率曾在 **4–6 月由 7.0% 升到 23.8% 后回落**，而流感则主要在冬春季高发。  
所以如果问“下一波”而不是“当前这波尾声”，我判断：**流感看冬季，新冠看明年晚春初夏**。但这只是基于近一年季节性和当前走势的推断，若出现新变异株、学校/节假日传播放大，时间可前后偏移 **2–6 周**。  
信息来源：China CDC《全国急性呼吸道传染病哨点监测情况（2026年第14–15周）》；China CDC《全国新型冠状病毒感染疫情情况（2026年2月、3月；2025年4月、5月、6月）》；China CDC《流感监测周报（2026年第14–15周）》
```

## covid-monitoring-02-spring-travel-covid-spread

- 目标：`question`
- 状态：`passed`
- 结论：行为与输出均满足预期。
- 日志：`experiments/skill_tests/runs/covid-monitoring-questions/20260421/covid-monitoring-02-spring-travel-covid-spread.log`

### 输入

```text
2026 年初的春运人口流动是否促进了新冠传播？
```

### 输出（最终回答，过滤 tool trace）

```text
已确定先用官方/准官方监测源，而不是直接下结论；下一步抓取 2026 年初中国及周边新冠活动信号。已拿到中国疾控总目录和 WHO 2026-02-03 风险评估。接着下钻 2026 年 1–2 月中国疾控月报和急性呼吸道哨点监测，判断春运前后是“同步上升”还是“仅季节/背景流行”。已从月报看到：1–2 月确有“低位小幅增加”，但还不够判断是否与春运时点吻合；继续看第 4–7 周周报做时序对照。从现有官方监测看，**更可能是“有一定促进，但幅度有限”，而不是明显放大了一波新冠流行**。  
证据：China CDC 显示 2026 年 1 月新增确诊 17,916 例、2 月 19,453 例，均表述为“**低位波动增加**”；哨点监测中门急诊流感样病例的新冠阳性率大致在 **1.5%（第4周）→2.3%（第5周）→2.2%（第6周）→1.7%（第7周）→1.3%（第8周）→2.3%（第9周）**，始终属低位，没有出现春运期间持续陡升。  
这说明春运这种高接触、高流动场景**理论上会增加传播机会**，且第5周（1月26日–2月1日）短暂上冲与春运时段相符，但全国尺度数据不支持“春运显著推动了大规模传播”的强结论；同期主导病原仍更多是流感、RSV 等。  
结论置信度：**中等**。局限是全国汇总数据难直接识别因果，且春运影响可能更体现在局部城市、家庭聚集和输入输出链条，而不一定在全国总量上形成尖峰。来源：China CDC 2026年1月、2月《全国新型冠状病毒感染疫情情况》及 2026年第4–9周《全国急性呼吸道传染病哨点监测情况》；WHO 2026-02-03 风险评估称全球 COVID 风险仍为 moderate、持续传播但总体严重性稳定。
```

## covid-monitoring-03-guangzhou-event-covid-impact

- 目标：`question`
- 状态：`passed`
- 结论：行为与输出均满足预期。
- 日志：`experiments/skill_tests/runs/covid-monitoring-questions/20260421/covid-monitoring-03-guangzhou-event-covid-impact.log`

### 输入

```text
我想 2026 年8 月在广州举办一次大型运动会，是否会受到新冠的影响？
```

### 输出（最终回答，过滤 tool trace）

```text
已定位可用监测技能；接下来抓取中国/华南官方监测信号，再做 2026 年 8 月广州大型赛事的风险判断。抓取来源表中与中国/华南新冠监测相关的官方来源，并查看是否有近期周报或通报可作为判断依据。继续补充广州/广东层面的来源，并读取中疾控最新通报正文，避免只根据标题判断。已拿到中国疾控最新正文数据。再补一层华南/邻近地区监测信号，用来判断广州 2026 年 8 月大型活动的现实风险区间。再补一份香港卫生防护中心的周报页面，作为广州周边同气候带参考。会有影响，但按目前证据看，**更可能是“可管理的持续性影响”，而不是足以否定办赛的决定性影响**。对“2026年8月广州大型运动会”的判断，我会给 **中等风险、可办但需预案**。

依据：
- **中国疾控** 2026-01-09 通报显示，2025年12月全国新冠报告病例处于**低位波动**，重症和死亡很低；但本土序列中 **NB.1.8.1 及其亚分支占主导**。
- **中国疾控** 2026年第4周哨点监测显示，新冠阳性率**总体低水平**，南方省份主要检出病原更多是流感/鼻病毒/副流感，说明新冠不是当时主导病原。
- **WHO** 2026-03 总结显示，全球 SARS-CoV-2 活动**整体低且稳定**，但 NB.1.8.1 在西太区占比上升；WHO同时提示，现有监测和报告较过去稀疏，存在低估。

对广州 2026 年 8 月的含义：
- 广州夏季**人员密集、室内空调场馆多、跨地区流动大**，即使全国处于低位，也可能出现**赛前/赛中局部聚集传播**。
- 更现实的影响不一定是“停办”，而是：**运动员/工作人员缺勤、代表团输入病例、医疗保障压力、舆情风险**。
- 目前没有证据支持“到 2026 年 8 月一定会严重影响到无法举办”，但也**不能假设完全没有影响**。

建议你按“正常办赛 + 新冠专项预案”准备：
1. 赛前 6–8 周持续跟踪 **中国疾控、广东省疾控、广州疾控**。
2. 为运动员村、媒体中心、室内场馆准备**发热/呼吸道症状处置流程**。
3. 高风险岗位（医疗、接待、闭环服务）保留**快速检测、口罩、隔离房间、替补排班**。
4. 对老年观众、慢病人群发布**分层防护建议**，而不是全面限制。
5. 设定触发阈值：若赛前 2–4 周广州/广东监测出现**明显上升或新变异株风险升级**，再加强入场与医疗措施。

信息来源：
- skill: respiratory-disease-wide-monitor（中国疾控全国新型冠状病毒感染疫情情况；全国急性呼吸道传染病哨点监测）
- WHO COVID-19 Dashboard Summary (2026-03)
```

## covid-monitoring-04-clinical-vs-wastewater-trends

- 目标：`question`
- 状态：`passed`
- 结论：行为与输出均满足预期。
- 日志：`experiments/skill_tests/runs/covid-monitoring-questions/20260421/covid-monitoring-04-clinical-vs-wastewater-trends.log`

### 输入

```text
临床阳性率趋势与污水监测趋势是否一致？
```

### 输出（最终回答，过滤 tool trace）

```text
一般规律是：大方向通常一致，但不一定同步、也不一定同幅度。  
污水监测常比临床阳性率更早出现上升或回落，常领先几天到1–2周。  
不一致常见于临床检测量变化、哨点偏倚、降雨稀释/覆盖范围、以及不同病原的排毒动力学差异。  
如果你给我具体地区、病原和时间段，我可以按数据帮你判断两条趋势是否一致。
```

## covid-monitoring-05-ba32-vs-xfg-severity

- 目标：`question`
- 状态：`passed`
- 结论：行为与输出均满足预期。
- 日志：`experiments/skill_tests/runs/covid-monitoring-questions/20260421/covid-monitoring-05-ba32-vs-xfg-severity.log`

### 输入

```text
BA.3.2 和 XFG 毒株的子代中，哪一种会导致临床重症率增加？
```

### 输出（最终回答，过滤 tool trace）

```text
查询本地谱系库和监测事件库，先看 BA.3.2、XFG 是否有收录及是否存在重症/高严重度信号。已定位到可能的数据治理仓库，接着查本地谱系目录、风险事件和突变特征，看是否存在“重症率升高”证据。执行几条只读 SQL：查谱系目录、样本记录和风险事件里是否有 BA.3.2/XFG 及其子代，并看有没有“重症/住院/死亡增加”相关信号。补查报告摘要和谱系定义，确认是否有“住院/重症/死亡增加”的明确表述；如果没有，只能给出“暂无证据显示增加”。再补一层公开监测资料，确认 XFG/BA.3.2 是否被官方或技术简报标记为“重症性增加”。读取 WHO 对 XFG 和 BA.3.2 的初始风险评估，直接看是否提到住院、重症或死亡风险上升。提取 WHO 风险评估 PDF 里的文字，直接核对“clinical severity / hospitalization / ICU / death”相关结论。基于我查到的本地监测库和 WHO 变异追踪信息，**目前没有证据表明 BA.3.2 或 XFG 的子代中，哪一支已被明确证实会导致临床重症率增加**。  
现有信号更偏向于**传播优势/流行占比变化**，不是“重症性上升”：

- **XFG 及其多条子代**：本地库里收录很多子代，且监测报告主要说它**占比升高、成为优势株**，未见“住院/ICU/死亡风险上升”的明确信号。  
- **BA.3.2**：本地监测只看到“美国出现本土病例”等事件，**没有看到其子代引起重症率增加的直接证据**。

结论：**两者目前都不能说有哪一种子代明确导致临床重症率增加。**如果你要，我可以继续细分到具体子代，比如比较 **XFG.1.1、XFG.14.1、XFG.3** 的突变位点和潜在风险。
```

## covid-monitoring-06-ba32-vaccine-trials

- 目标：`question`
- 状态：`passed`
- 结论：行为与输出均满足预期。
- 日志：`experiments/skill_tests/runs/covid-monitoring-questions/20260421/covid-monitoring-06-ba32-vaccine-trials.log`

### 输入

```text
近期是否有新的针对新冠 BA.3.2 的疫苗进入临床试验？
```

### 输出（最终回答，过滤 tool trace）

```text
先查临床试验注册库和公开资料，再交叉核实是否真有“针对 BA.3.2”的新疫苗。ClinicalTrials.gov 旧接口失效，改用现行检索接口和文献数据库做交叉核实。继续核对公开注册库接口和更广泛的公开资料，确认不是检索方式导致漏报。补一轮检索近期变异株适配疫苗方向，确认当前进入临床的主流靶株是否已转向 XBB/JN.1/KP.2，而不是 BA.3.2。核对唯一检索命中的 NCT05236491，确认它是不是 BA.3.2 靶向疫苗，而不是普通加强针研究。结论：截至我刚检索到的公开信息，**没有看到近期“专门针对新冠 BA.3.2”且新进入临床试验的疫苗**。  
我查了 ClinicalTrials.gov 现行 `api/v2/studies` 检索与 PubMed：`BA.3.2[Title/Abstract] AND COVID-19 vaccine` 命中数为 **0**；ClinicalTrials.gov 用 `BA.3.2 COVID-19 vaccine` 只误命中一项普通免疫缺陷患者加强针研究 `NCT05236491`，其登记内容**未提 BA.3.2**。  
相对地，近期进入/推进临床的变异株适配疫苗公开靶向更常见的是 **XBB.1.5、JN.1、KP.2**，例如 ClinicalTrials.gov 可检到 `NCT05543616`（XBB.1.5/KP.2 适配 BNT162b2）、`NCT07079670`/`NCT07086222`（JN.1 相关 Novavax 候选）。  
如果你要，我可以继续给你整理一份“**近一年新冠更新株疫苗临床试验清单**”，按 **XBB.1.5 / JN.1 / KP.2** 分类。
```

## covid-monitoring-07-covid-flu-correlation-seasonality

- 目标：`question`
- 状态：`runner_error`
- 结论：运行器错误：Timed out after 12 minute(s)
- 日志：`experiments/skill_tests/runs/covid-monitoring-questions/20260421/covid-monitoring-07-covid-flu-correlation-seasonality.log`

### 输入

```text
历年新冠和流感阳性率是否有相关关系？新冠阳性率的波动周期有什么规律？是否和季节有关？
```

### 输出（最终回答，过滤 tool trace）

```text
已确定先用官方监测数据做定量判断，优先找可连续获取多年周度阳性率的来源。
```

## covid-monitoring-08-may-mainland-dominant-lineage

- 目标：`question`
- 状态：`runner_error`
- 结论：运行器错误：Non-zero exit code: 1
- 日志：`experiments/skill_tests/runs/covid-monitoring-questions/20260421/covid-monitoring-08-may-mainland-dominant-lineage.log`

### 输入

```text
今年 5 月，中国大陆的主要流行新冠毒株（占比最高的毒株）会是哪一株？
```

### 输出（最终回答，过滤 tool trace）

```text
Unexpected error during non-interactive execution
Traceback (most recent call last):
  File "/mnt/data1/zhangpf/code2workspace/libs/cli/code2workspace_cli/non_interactive.py", line 1019, in run_non_interactive
    await _run_agent_loop(
  File "/mnt/data1/zhangpf/code2workspace/libs/cli/code2workspace_cli/non_interactive.py", line 661, in _run_agent_loop
    await _stream_agent(agent, stream_input, config, state, console, file_op_tracker)
  File "/mnt/data1/zhangpf/code2workspace/libs/cli/code2workspace_cli/non_interactive.py", line 599, in _stream_agent
    async for chunk in agent.astream(
  File "/mnt/data1/zhangpf/code2workspace/libs/cli/code2workspace_cli/remote_client.py", line 134, in astream
    async for ns, mode, data in graph.astream(
  File "/mnt/data1/zhangpf/code2workspace/libs/cli/.venv/lib/python3.11/site-packages/langgraph/pregel/remote.py", line 967, in astream
    raise RemoteException(chunk.data)
langgraph.pregel.remote.RemoteException: {'error': 'InternalServerError', 'message': 'An internal error occurred'}

Unexpected error (RemoteException): {'error': 'InternalServerError', 'message': 
'An internal error occurred'}
```

## covid-monitoring-09-fastest-growing-sublineage

- 目标：`question`
- 状态：`passed`
- 结论：行为与输出均满足预期。
- 日志：`experiments/skill_tests/runs/covid-monitoring-questions/20260421/covid-monitoring-09-fastest-growing-sublineage.log`

### 输入

```text
近两周增长最快的亚型及其序列数有多少？
```

### 输出（最终回答，过滤 tool trace）

```text
查本地新冠谱系数据，按“最近14天相对前14天的新增序列数增幅”口径计算；若需别的病原/口径再改。已定位到本地数据治理仓库，下一步直接查库计算近14天增长最快谱系。检查本地库日期覆盖和谱系计数，先确认“近两周”按库内最新日期计算。已确认口径：按本地 `covid_data.ncov_source_records` 的 SARS‑CoV‑2 谱系记录数统计，窗口锚定库内最新采样日 2026‑03‑22。补一条对照：看近14天窗口内哪些谱系本身序列数最多，避免只看到“从0到几条”的小样本噪声。再核一下去重口径：按 `accession` 去重统计“序列数”，避免重复抓取记录影响结果。按本地 `covid_data.ncov_source_records`、以库内最新采样日 `2026-03-22` 为锚，比较 `2026-03-09~2026-03-22` 对 `2026-02-23~2026-03-08`，增长最快的亚型是 **XFG.17.3**：近两周 **3** 条序列，前两周 **0** 条，净增 **3**。  
若按“有前期基数的相对增速”看，**RE.2** 最快：近两周 **4** 条，前两周 **2** 条，增长 **2.0 倍**。  
补充：近两周序列数最多的是 **XFG.1.1（19 条）**，但它较前两周 **88 条** 是下降的。  
如果你要，我可以继续给你列出前10个“增长最快亚型”排行榜。
```

## covid-monitoring-10-s-protein-escape-sites

- 目标：`question`
- 状态：`passed`
- 结论：行为与输出均满足预期。
- 日志：`experiments/skill_tests/runs/covid-monitoring-questions/20260421/covid-monitoring-10-s-protein-escape-sites.log`

### 输入

```text
新冠病毒S蛋白上哪些位点的突变最容易逃逸抗体？
```

### 输出（最终回答，过滤 tool trace）

```text
先查本地位点风险库，再补一层文献证据，确认哪些 Spike 位点最常见于抗体逃逸。本地库首轮结果偏向 NTD 零散位点；再按 RBD/NTD 分层做聚合，避免把单个模型里的高分位点误当成总体最重要位点。补查经典深度突变扫描文献和几个公认关键位点，避免只靠库里的聚合分数。再补查几个公认热点位点的库内分数，确保回答聚焦在 RBD 主逃逸热点而不是泛泛列点。最后补一个 NTD supersite 文献点，支撑 NTD 热点结论。最容易发生抗体逃逸的，主要集中在 **Spike 的 RBD，尤其是 RBM 周边**；如果按“反复被实验和变异株验证”的重要性看，优先记这些位点：

- **E484**：最经典的抗体逃逸热点之一，对多克隆血清和多类中和抗体影响都很大。
- **F486**：Omicron 后期非常关键，常与明显免疫逃逸相关。
- **R346、K417、G446、L452、Y453、L455、F456、N460、Q493、Q498、N501、Y505**：多次出现在不同变异株/深度突变扫描中，常影响某一类或多类 RBD 抗体结合。
- 其中可特别关注：**R346 / L452 / F456 / E484 / F486 / Q493 / N501 / Y505**。

此外，**NTD supersite** 也是重要逃逸区，常见热点包括：
- **F140、Y144/145、W152、E156-F157-R158 区段、R246**
- 这类位点常通过缺失、插入或替换削弱 NTD 中和抗体识别。

简化结论：  
**RBD 里最核心的是 E484、F486，其次是 R346/K417/G446/L452/F456/Q493/N501/Y505；NTD 里最核心的是 140–158 和 246 附近。**  
信息来源：本地 `virus_variation` 位点风险库；PubMed: Greaney et al., *Cell Host Microbe* 2021 (PMID 33259788), *Nat Commun* 2021 (PMID 34234131); McCallum et al., *Cell* 2021 (PMID 33761326)。
```

## covid-monitoring-11-us-trend-deaths-ed-positivity

- 目标：`question`
- 状态：`passed`
- 结论：行为与输出均满足预期。
- 日志：`experiments/skill_tests/runs/covid-monitoring-questions/20260421/covid-monitoring-11-us-trend-deaths-ed-positivity.log`

### 输入

```text
讲一下美国新冠疫情的趋势，最近一个月美国的新冠死亡率、急诊科就诊人数和检测阳性率变化情况如何？
```

### 输出（最终回答，过滤 tool trace）

```text
先查可用监测技能与数据源，再抓美国近一个月的官方指标。已确认这个问题适合直接用固定的 U.S. CDC Trends 源；继续找可直接调用的接口或页面数据。查仓库里是否已有 CDC 趋势数据样例或接口线索，减少盲抓。CDC 页面是前端应用，直接抓到的是重定向占位页；改查它加载的脚本和公开数据接口。已定位到 CDC 页面背后的公开 JSON 数据文件；接着取近 5 周序列并计算环比/近月变化。继续追 CDC 的“死亡率”嵌入式图表，看能否拿到真正的 death rate，而不只是一条死亡占比线。查嵌入式 Power BI 的公开报表参数，看看能否直接取到 CDC 的“COVID-19 Death Rates”原始数据。继续从 CDC 嵌入的 Power BI 公共接口取“COVID-19 Death Rates”报表元数据，确认能否拿到严格意义的死亡率。继续试 Power BI 公共 API；如果能拿到 schema 和 query 接口，就能提取 CDC 的“死亡率”面板原始值。已拿到 CDC 三个趋势图的公开 JSON；同时找到“COVID-19 Death Rates”背后的 Power BI 公共接口，补查更严格的死亡率定义。尝试直接调用 Power BI 的 `querydata` 公共接口，拿美国近月“周死亡率”原始序列；先用探索到的报表查询体试一下。修正上一步的 BOM 解析问题，并单独验证死亡率查询结果。把数值算清楚后就可以汇总：近一个月检出阳性率和急诊占比都明显下降，死亡相关指标也在低位回落。把 CDC 公共接口返回的压缩行解码成最近几周的“周年龄调整死亡率”，再做最终汇总。继续把 Power BI 的压缩位掩码按正确顺序解码，确认最近几周美国新冠“周死亡率”数值。美国最近一个月的新冠趋势总体是**继续走低、处在较低水平**。按 CDC 最新可得周度数据看：

- **检测阳性率**：从截至 **2026-03-07 的 3.3%** 降到 **2026-04-11 的 1.7%**，下降 **1.6 个百分点**，约 **-48.5%**。
- **急诊科就诊占比**（因 COVID-19 就诊的 ED visits 占比）：从 **0.5%** 降到 **0.2%**，下降 **0.3 个百分点**，约 **-60%**。
- **死亡相关指标**：
  - CDC 页面上的“**全美死亡中归因于新冠的占比**”从 **2026-03-07 的 0.5%** 降到 **2026-04-04 的 0.3%**，约 **-40%**；
  - CDC 嵌入的“**周年龄调整死亡率**”近几周大致从 **0.1/10万人** 降到 **0**（最新几周接近零，处于极低水平）。

简要判断：美国近一个月新冠传播强度、急诊负担和死亡负担都在下降，没有看到近期明显反弹信号。  
信息来源：CDC Surveillance and Data Analytics 页面；CDC 公开 JSON 趋势数据（test positivity、ED visits、deaths）；CDC 嵌入 Power BI 公共接口。
```

## covid-monitoring-12-covid-flu-rsv-overview

- 目标：`question`
- 状态：`passed`
- 结论：行为与输出均满足预期。
- 日志：`experiments/skill_tests/runs/covid-monitoring-questions/20260421/covid-monitoring-12-covid-flu-rsv-overview.log`

### 输入

```text
帮我看一下近期 COVID、流感和 RSV 的监测情况。
```

### 输出（最终回答，过滤 tool trace）

```text
先抓取近期官方监测页和汇总源，优先覆盖 WHO、美国 CDC、中国疾控，并补充 RSV/流感数据。已拿到中国疾控总览页和 CDC 监测入口；下一步补抓流感周报、急性呼吸道哨点和 CDC 多病原周度摘要，提炼近期趋势。补抓最新单篇周报正文和可用的数据入口，尽量把“上升/下降、主导病原、是否处于季节尾部”说清楚。用现成 skill 脚本补查更广的官方来源，看看 WHO/CDC 是否有更直接的近期周报或摘要页。再补一轮直接的周报正文，优先抓美国 FluView 当前周报和可能可读的 COVID/RSV 监测页。抓取中国疾控最新月报正文，补上 COVID 的最新数值。近期看，三种病原整体都不在高位，但**流感活动相对最明显，RSV 处于回落期，COVID 维持低水平小幅波动**。  
- **中国**：第15周急性呼吸道哨点监测显示，门急诊样本阳性前三是**流感 15.3%**、鼻病毒 8.8%、副流感 6.9%；**RSV 2.6%，较上周下降 1.2 个百分点**；**新冠 1.8%，总体低位**。住院重症呼吸道感染中，RSV 为 **5.0%**，也在下降。  
- **流感**：中国流感周报显示第15周南北方**流感阳性率下降**，但仍以**B 型流感为主**；全国报告 **23 起**流感样病例暴发，较前一周 56 起下降。  
- **COVID**：中国 2026 年 3 月新增确诊 **26,306 例**、重症 **60 例**、死亡 **2 例**，属**低位波动增加**；本土序列仍几乎全是奥密克戎，**NB.1.8.1 及其亚分支**占主导，现有证据**未提示额外公共卫生风险的新变异株**。WHO 也提示全球 SARS-CoV-2 监测更多转入常规呼吸道监测，近期变异株面板还有技术性缺口。  
- **美国/全球补充**：CDC 当前框架仍把 COVID、流感、RSV 作为同一季节性呼吸道病原持续监测；RSV 页面提示其季节通常秋季起、冬季达峰、春季结束，和目前中国“RSV 下降”的信号一致。  

信息来源：China CDC 全国急性呼吸道传染病哨点监测情况（2026年第15周）；China CDC 中国流感监测周报（2026年第15周）；China CDC 全国新型冠状病毒感染疫情情况（2026年3月）；WHO COVID-19 dashboard；CDC RESP-NET / RSV Surveillance。
```
