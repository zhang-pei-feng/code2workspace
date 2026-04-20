---
name: acpx-skill
description: "通过 workspace 里的 .acpxrc.json 用 acpx 桥接五个外部 agent：benchmark_agent、data_governance_agent、deep_research_agent、code2workspace_agent、report_agent。只要用户提到 benchmark、工作流复用、复用工作流、复用已有 workflow、已有 workflow 复跑或 Bio-OS workflow reuse 任务，就必须使用 `exec` 运行 `acpx` 调 benchmark_agent，不要使用 `sessions_spawn`。用户要求生成/撰写任何正式报告或风险评估报告时，即使没说“报告智能体”，也必须一次性路由到 report_agent，不能用 benchmark_agent。用户要求调用 code2workspace_agent、code2workspace、paper2workspace、仓库转 workspace、生成 workspace/WDL/Bio-OS workspace 产物时路由到 code2workspace_agent。其他代码分析、仓库检查、source/数据源、snapshot、MySQL、lineage、mutation、联网调研、带来源链接总结、继续上次会话、session id/session name 也使用本 skill。"
metadata: { "openclaw": { "emoji": "🔌", "requires": { "bins": ["acpx", "python3"] } } }
---

# ACPX Skill

通过 `acpx` 调用当前 skill 目录 `.acpxrc.json` 已注册的 5 个外部 agent，并在需要时复用稳定会话。
benchmark / compare / workflow reuse 类任务统一通过 `acpx` 调 benchmark_agent，而不是 `sessions_spawn`。

## 支持的 agent

- `benchmark_agent`
- `data_governance_agent`
- `deep_research_agent`
- `code2workspace_agent`
- `report_agent`

## 默认路由

- 代码分析、看仓库、改代码、跑本地命令、benchmark 风格任务、工作流复用/复用工作流/Bio-OS workflow reuse 任务：`benchmark_agent`
- 数据治理、source、数据源、snapshot、MySQL、lineage、mutation：`data_governance_agent`
- 联网研究、搜资料、对比方案、带来源链接的总结：`deep_research_agent`
- code2workspace、paper2workspace、仓库转 workspace、生成 workspace/WDL/Bio-OS workspace 产物：`code2workspace_agent`
- 生成报告、撰写报告、报告智能体、正式报告正文、风险评估报告：`report_agent`

注意：只要 prompt 包含“生成报告/撰写报告/写报告/风险评估报告/正式报告”等报告生成意图，就应路由到 `report_agent`，不需要用户显式说“用报告智能体”；不要因为内容涉及分析、对比、风险评估或数据检索就改用 `benchmark_agent`。

默认 alias：

- `benchmark_agent` -> `benchmark-main`
- `data_governance_agent` -> `db-governance`
- `deep_research_agent` -> `deep-research`
- `code2workspace_agent` -> `code2workspace-main`
- `report_agent` -> `report-main`

默认执行策略：

- `benchmark_agent`：自适应。短句/打招呼/探活优先 one-shot `exec`；只有会话干净且空闲时才复用持久会话
- `data_governance_agent`：优先持久会话
- `deep_research_agent`：优先 one-shot `exec`
- `code2workspace_agent`：优先 one-shot `exec`，每次由适配层创建独立任务 workspace
- `report_agent`：优先 one-shot `exec`

`code2workspace_agent` 只能通过 `acpx`/`acpx_session.py` 调用，不要使用 `sessions_spawn`。如果任务文本里提到 `docker_images-agent` 或 `wdl_run-agent`，也不要从 OpenClaw 主会话直接 spawn 它们；它们是 `code2workspace_agent` 内部工作流角色。

## 工作方式

优先使用脚本：

```bash
python3 skills/acpx-skill/scripts/acpx_session.py route \
  --prompt "<用户真正要问外部 agent 的话>"
```

如果用户已经明确指定 agent 或 alias，再使用 `send`。
如果用户明确指定 agent 但不需要复用会话，也可以使用 `route --agent <agent>` 强制路由。

如果只是确认会话或读状态，使用 `ensure`、`status`、`history`。

## 常用命令

```bash
python3 skills/acpx-skill/scripts/acpx_session.py ensure \
  --agent data_governance_agent \
  --alias db-governance

python3 skills/acpx-skill/scripts/acpx_session.py route \
  --prompt "帮我问一下数据库治理那个智能体，现在接了哪些数据源"

python3 skills/acpx-skill/scripts/acpx_session.py route \
  --prompt "生成近期全球呼吸系统病原流行情况报告（新冠、流感、RSV）"

python3 skills/acpx-skill/scripts/acpx_session.py route \
  --agent code2workspace_agent \
  --prompt "请把这个仓库生成 workspace 产物"

python3 skills/acpx-skill/scripts/acpx_session.py send \
  --agent benchmark_agent \
  --alias benchmark-main \
  --prompt "请检查当前仓库结构，只给 3 条结论"

python3 skills/acpx-skill/scripts/acpx_session.py status \
  --agent data_governance_agent \
  --alias db-governance

python3 skills/acpx-skill/scripts/acpx_session.py history \
  --agent benchmark_agent \
  --alias benchmark-main \
  --limit 6
```

状态文件：

```text
./.openclaw/acpx-session-map.json
```

## 可迁移配置

为避免 skill 绑定到固定机器目录，本 skill 使用相对路径和环境变量解析外部 agent 启动命令。迁移到其他 workspace 后，只需要按需设置这些环境变量：

- `OPENCLAW_EXTERNAL_AGENTS_ROOT`
- `BENCHMARK_AGENT_ACP_COMMAND`
- `DATA_GOVERNANCE_AGENT_ACP_COMMAND`
- `DEEP_RESEARCH_AGENT_ACP_COMMAND`
- `CODE2WORKSPACE_AGENT_ACP_COMMAND`
- `REPORT_AGENT_ACP_COMMAND`
- `REPORT_AGENT_REPORTS_ROOT`

如果设置了具体 `*_ACP_COMMAND`，它会覆盖 `OPENCLAW_EXTERNAL_AGENTS_ROOT` 的默认解析。

## 规则

1. 优先使用 `alias`，不要把随机 session 名暴露给用户。
2. 发送消息前先判断 alias 是否空闲、是否干净；只有通过检查时才 `ensure` 并复用。
3. 如果任务明显落在这些 agent 之一，不要先读一堆本地文件再决定，直接桥接。
4. 用户没要求调试信息时，默认只返回关键信息，不要把整个 JSON 原样倒出来。
5. 如果用户说“继续聊”“接着问”，优先复用已有 alias。
6. `deep_research_agent` 默认要求给来源链接或来源说明。
7. 如果外部 agent 失败，直接报告失败，不要静默切换到别的 agent，也不要改成自己直接回答。
8. 如果用户明确要求“用 acpx-skill / 用某个 acpx agent 回答”，就必须把最终答案视为外部 agent 的结果；外部 agent 超时或失败时，只能汇报失败原因，不能自行补做研究。
9. 对 `deep_research_agent`：
   - 必须使用较长的外层等待时间。
   - 对真实研究题，`acpx --timeout` 默认按 `300` 处理，不要擅自降到 `120`、`80` 或更小。
   - 如果 `exec` 返回 still running，应继续等待或明确汇报超时。
   - 不要把研究题降级成你自己的 web search / 手工总结。
10. 对 `report_agent`：
   - 报告类任务只调用 `report_agent` 一次，不要并行再调用 `benchmark_agent` 或其他 agent。
   - `acpx report_agent exec` 只接受 positional prompt 或 `-f/--file`，不要使用不存在的 `--task`、`--workspace`、`--input` 等参数。
   - 正确命令形态是：
     `acpx --cwd skills/acpx-skill --format text --timeout 1800 report_agent exec "<任务文本>"`
   - 报告生成可能需要较长联网调研时间；外层 `exec` 工具 timeout 至少应大于 `1900` 秒，`yieldMs` 尽量设置到 `1800000`。如果第一次返回 `Command still running` / `Process still running`，必须继续 `process poll` 到完成、失败或超过上述时限，不要只回复用户“继续等待”后停止监控。
   - `report_agent` 完成后，面向用户的最终回复必须包含完整报告正文，不要只给“报告文件：.../final_report.md”或“点击这里查看报告”。用户拿不到服务器本地路径。
   - 如果 `report_agent` 输出里包含 `报告文件:`、`final_report.md` 或 `.../reports/...` 路径，先读取该文件，再把文件正文发给用户；路径最多作为内部排障信息，不作为正常用户答案。
   - 如果报告进程的 process session 丢失、返回 `No session found` 或网关重启后找不到运行记录，不要直接判定失败；先检查 `${REPORT_AGENT_REPORTS_ROOT}/latest_report.md`、`${REPORT_AGENT_REPORTS_ROOT}/latest/final_report.md` 和 `${REPORT_AGENT_REPORTS_ROOT}/report_*/final_report.md`，如果文件存在就读取并返回报告正文。
   - 对报告生成类请求，必须一次性生成报告正文，不要向用户反问来源、定义、地区或时间范围；如果信息不足，在报告中写“证据不足/口径限制”，继续完成报告。
11. 对 `benchmark_agent`：
   - 如果 prompt 是“你好”“hello”“回复一句话”这类短交互，不要复用 `benchmark-main`，直接 one-shot `exec`。
   - 如果 prompt 内包含 `export MIRACLE_ACCESS_KEY=...` / `export MIRACLE_SECRET_KEY=...` 这类鉴权信息，必须走 fresh one-shot `exec`，不要复用旧 alias。
   - 调用脚本时，要把这些 `export` 真正注入到子进程环境，不能只把它们当成普通文本转发给 agent。
   - 对 Bio-OS / Miracle 相关任务，如果用户没有额外提供 `MIRACLE_ACCESS_KEY` / `MIRACLE_SECRET_KEY`，默认使用本 skill 写明的默认值；如果用户提供了，则以用户提供的值为准。
   - 默认 Miracle 鉴权值：
     `MIRACLE_ACCESS_KEY="AKLTMjVkNjZiM2Q3MzI5NGQ4YmE5YTFmOWZhYjY4YzEzNTc"`
     `MIRACLE_SECRET_KEY="WW1GbU1qSXdObVpoWXpVek5EazBPVGd6TVdVMFlXTXhOVEUzT0RKak9Eaw=="`
   - benchmark / compare / 工作流复用 / 复用工作流 / Bio-OS workflow reuse 任务禁止走 `sessions_spawn`；必须通过 `acpx` 调 `benchmark_agent`。
   - `acpx` 的 cwd 固定为 `skills/acpx-skill`，通过当前 skill 目录 `.acpxrc.json` 解析真实 agent 启动脚本。
   - 不要切到外部 `report_agent` 仓库目录直接运行 `acpx`；`report_agent` 也必须通过 `acpx --cwd skills/acpx-skill report_agent exec "<任务文本>"` 调用。
   - 也不要切到外部 `benchmark_agent` 仓库目录后直接运行 `acpx benchmark_agent exec`；统一使用当前 skill 目录 `.acpxrc.json`。
   - 首选命令形态是：
     `env ... acpx --cwd skills/acpx-skill --timeout 3600 benchmark_agent exec "<任务文本>"`
   - 对 Bio-OS / Miracle / 工作流复用 / benchmark 长任务，外层 `exec` 工具 timeout 至少应大于 `3700` 秒，`yieldMs` 尽量设置到 `3600000`。如果第一次返回 `Command still running` / `Process still running`，必须继续 `process poll` 到完成、失败或超过上述时限，不要只回复用户“继续等待”后停止监控。
   - 外层 `exec` 工具不要设置 `security=allowlist` 或 `ask=on-miss`，否则会绕过全局自动审批策略并触发 `allowlist miss`；应省略这两个参数，或使用 `security=full`、`ask=off`。
   - 如果主 agent 先尝试了 `sessions_spawn` 但被策略拒绝，例如出现 `ACP agent "benchmark_agent" is not allowed by policy.`，不要把这个错误直接返回给用户；应立即改走上面的 `acpx` one-shot `exec` 路径。
   - benchmark 任务的目标是“通过 acpx 成功调用 benchmark_agent”，不是“证明 sessions_spawn 不可用”。
   - 如果 `benchmark-main` 已有在途请求，或者元数据出现 `disconnect_reason` / `last_exit_at` / 死 pid，禁止继续往这个 alias 发送消息。
   - 遇到上述情况时，自动降级为 one-shot `exec`，而不是在旧会话后面排队。
   - 如果是 Bio-OS benchmark 任务，任务文本里必须要求返回真实的 `submission_id`、状态和结果文件路径；没有这些就按失败处理。
12. 对 `code2workspace_agent`：
   - 禁止使用 `sessions_spawn(runtime="acp", agentId="code2workspace_agent")`。
   - 禁止使用 `sessions_spawn` 调用 `docker_images-agent` 或 `wdl_run-agent`；它们由 `code2workspace_agent` 内部负责。
   - 必须把用户原始 code2workspace / paper2workspace 任务文本作为一个完整 prompt 一次性转给 `code2workspace_agent`；不要在 OpenClaw 主会话拆成 Docker 阶段和 WDL 阶段分别问。
   - 首选命令形态是：
     `python3 skills/acpx-skill/scripts/acpx_session.py route --agent code2workspace_agent --prompt "<任务文本>"`
   - 也可以直接调用：
     `acpx --cwd skills/acpx-skill --format text --timeout 7200 code2workspace_agent exec "<任务文本>"`
   - 对真实 code2workspace 长任务，外层 `exec` 工具参数尽量同时设置 `timeout >= 7300` 和 `yieldMs >= 7200000`，不要只设置 timeout。这样 UI 会等待长任务完成，而不是 10 秒后把命令放到后台。
   - 如果第一次返回 `Command still running` / `Process still running`，必须继续 `process poll` 到完成、失败或超过上述时限；poll 时使用 tool result/details 里的 session 名（例如 `tidy-wharf`），不要使用 pid 数字。
   - 如果外部 agent 失败或超时，报告失败；不要在主会话里自行 `git clone`、手写 Dockerfile/WDL、`docker build`、`docker push` 或投递 Bio-OS 来替代。

## 深度研究调用约束

当目标是 `deep_research_agent` 时，优先使用这种风格的命令：

```bash
acpx --cwd skills/acpx-skill \
  --format quiet \
  --timeout 300 \
  deep_research_agent exec "<research prompt>"
```

严格要求：

- 不要把上面的 `300` 缩短成 `120`、`90`、`80`。
- 如果外层 `exec` 工具也要设 timeout，外层 timeout 至少应大于 `330`，避免外层先把子进程杀掉。
- 如果第一次仍然返回 `Command still running`，优先继续 `process poll`，而不是立刻判定失败。

## 输出约定

- 普通问答：直接给 agent 的结论
- 需要排障：补充 `session_id`
- 需要结构化输出时，整理脚本 JSON 后再给用户简洁答案
- 当结果来自外部 agent 且被你实际采用时，在答案末尾追加一个简短的“信息来源”小节，例如 `外部智能体: deep_research_agent`、`外部智能体: data_governance_agent`。
- 如果最终答案还采用了外部 agent 返回中的网页链接或数据库结果，可以一起粗粒度写出；不要把未采用的尝试也列进去。
