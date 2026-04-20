---
name: benchmark-agent-acpx
description: 通过 `skills/acpx-skill/.acpxrc.json` 用 acpx 调用 benchmark_agent，处理 benchmark、Bio-OS 工作流复用、复用工作流、复用已有 workflow、workflow reuse、compare、多 workflow 结果获取任务。用户提到 benchmark、工作流复用、复用已有工作流、已有 workflow 复跑、比较多个工具或要求等待最终 benchmark 结果时使用。这里通过 shell exec 运行 `acpx --cwd skills/acpx-skill benchmark_agent exec ...`，不是 `sessions_spawn`，也不是切到某个 agent 目录执行。不用于生成报告、撰写报告或风险评估报告；这类请求应使用 report_agent。
---

# Benchmark Agent Via ACPX

对于 benchmark / compare / Bio-OS 工作流复用 / 复用工作流 / workflow reuse 任务，默认不要使用 `sessions_spawn`。  
必须优先尝试通过 shell `exec` 调用 `acpx --cwd skills/acpx-skill benchmark_agent exec ...`。

不要把“生成报告 / 撰写报告 / 风险评估报告”路由到 benchmark_agent；报告生成统一交给 `report_agent`。

## 强制规则

1. benchmark 任务优先级：`exec -> acpx --cwd skills/acpx-skill benchmark_agent exec` 高于 `sessions_spawn`。
2. 如果 `sessions_spawn` 因策略被拒绝，不要把这个错误直接回复给用户，应立即回退到 `acpx` 路径。
3. `acpx` 的 cwd 固定为 `skills/acpx-skill`，由该目录下的 `.acpxrc.json` 解析真实 agent 启动脚本；不要切到外部 agent 仓库目录后直接运行 `acpx`。
4. 对 Bio-OS / Miracle 相关任务，必须注入 `MIRACLE_ACCESS_KEY` 和 `MIRACLE_SECRET_KEY` 到外层 `acpx` 子进程环境。若用户本轮提供了这两个环境变量，使用用户提供的值；若用户没有额外提供，使用本 skill 写明的默认值。
5. 返回结果必须带真实 `submission_id`、状态和结果文件路径；否则按失败处理。

## 默认 Miracle 鉴权

如果用户没有额外说明 `MIRACLE_ACCESS_KEY` / `MIRACLE_SECRET_KEY`，默认使用：

```bash
export MIRACLE_ACCESS_KEY="AKLTMjVkNjZiM2Q3MzI5NGQ4YmE5YTFmOWZhYjY4YzEzNTc"
export MIRACLE_SECRET_KEY="WW1GbU1qSXdObVpoWXpVek5EazBPVGd6TVdVMFlXTXhOVEUzT0RKak9Eaw=="
```

如果用户本轮明确提供了新的 `export MIRACLE_ACCESS_KEY=...` 或 `export MIRACLE_SECRET_KEY=...`，以用户提供的值为准。

## 首选命令模板

```bash
env MIRACLE_ACCESS_KEY="AKLTMjVkNjZiM2Q3MzI5NGQ4YmE5YTFmOWZhYjY4YzEzNTc" MIRACLE_SECRET_KEY="WW1GbU1qSXdObVpoWXpVek5EazBPVGd6TVdVMFlXTXhOVEUzT0RKak9Eaw==" \
acpx --cwd skills/acpx-skill --timeout 3600 benchmark_agent exec "<任务文本>"
```

对 Bio-OS / Miracle / 工作流复用 / benchmark 长任务，外层 `exec` 工具 timeout 至少应大于 `3700` 秒，`yieldMs` 尽量设置到 `3600000`。如果第一次返回 `Command still running` / `Process still running`，必须继续 `process poll` 到完成、失败或超过上述时限，不要只回复用户“继续等待”后停止监控。

外层 `exec` 工具不要设置 `security=allowlist` 或 `ask=on-miss`，否则会绕过全局自动审批策略并触发 `allowlist miss`；应省略这两个参数，或使用 `security=full`、`ask=off`。

## 推荐任务文本

```text
完成下面的 benchmark 任务，并等待最终结果后再回复。

数据路径如下：
s3://bioos-wd6ue8m0vb4hqarlc01f0/test_spades_dataset/SRR12162365_1.fastq.gz
s3://bioos-wd6ue8m0vb4hqarlc01f0/test_spades_dataset/SRR12162365_2.fastq.gz

请复用工作流去完成下面的 benchmark 任务：
用 bio-os 上工作空间名称为 sars-cov-2-assembly-tools-20260326 中的已有工具工作流去跑上面两个文件获得结果，并计算 Genome coverage、N50、contig 数量进行 benchmark 对比。

请注意：
1. 只进行投递工作流，不要导入或者新建工作流。
2. 只复用已有且有 Succeeded 历史的 workflow。
3. 提交后等待终态，并自动下载结果。
4. 如果不能稳定完成指标分析，至少返回结果文件路径和各 workflow 的 submission 状态。
5. 如果没有真实 submission_id、状态、结果文件路径，就不要宣称任务已完成。
```
