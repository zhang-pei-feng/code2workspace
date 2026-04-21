---
name: benchmark-agent-acpx
description: 通过 `skills/acpx-skill/.acpxrc.json` 用 acpx 调用 benchmark_agent，处理 benchmark、工作流复用、复用已有 workflow、workflow reuse、compare、多 workflow 结果获取任务。这里通过 shell exec 运行 `acpx --cwd skills/acpx-skill benchmark_agent exec ...`，不是 `sessions_spawn`，也不是切到某个 agent 目录执行。不用于生成报告、撰写报告或风险评估报告；这类请求应使用 report_agent。
---

# Benchmark Agent Via ACPX

对于 benchmark / compare / 工作流复用 / workflow reuse 任务，默认不要使用 `sessions_spawn`。  
必须优先尝试通过 shell `exec` 调用 `acpx --cwd skills/acpx-skill benchmark_agent exec ...`。

## 强制规则

1. benchmark 任务优先级：`exec -> acpx --cwd skills/acpx-skill benchmark_agent exec` 高于 `sessions_spawn`。
2. 如果 `sessions_spawn` 因策略被拒绝，不要把这个错误直接回复给用户，应立即回退到 `acpx` 路径。
3. `acpx` 的 cwd 固定为 `skills/acpx-skill`，由该目录下的 `.acpxrc.json` 解析真实 agent 启动脚本；不要切到外部 agent 仓库目录后直接运行 `acpx`。
4. 返回结果必须带真实状态和结果文件路径；否则按失败处理。
5. workflow 默认按本地执行路径理解，不再假设远端工作流平台。
