---
name: code2workspace_agent
description: 当用户提到 code2workspace_agent、code2workspace、paper2workspace、仓库转 workspace、代码转 workspace、生成 workspace、workspace 产物、生成/编写 WDL，或者在这类任务里要求调用 docker_images-agent / wdl_run-agent 时使用。必须通过 shell exec/acpx 调用 `skills/acpx-skill/.acpxrc.json` 里注册的 code2workspace_agent，禁止使用 sessions_spawn。
---

# code2workspace_agent Bridge

当用户说“用 code2workspace 智能体”或描述 code2workspace / paper2workspace / 仓库转 workspace / WDL 任务时，默认动作是通过 `acpx` 调用外部智能体。

## 强制规则

1. 不要使用 `sessions_spawn(runtime="acp", agentId="code2workspace_agent")`。
2. 不要使用 `sessions_spawn` 调用 `docker_images-agent` 或 `wdl_run-agent`。这两个是 `code2workspace_agent` 内部工作流角色，不是 OpenClaw 主会话的 subagent。
3. 不要在 OpenClaw 主会话里自行 `git clone`、手写 Dockerfile/WDL、`docker build` 或伪造结果来替代外部智能体。
4. `acpx` 的 cwd 固定为 `skills/acpx-skill`，由该目录下的 `.acpxrc.json` 解析真实启动脚本。
5. 把用户原始 code2workspace 任务文本作为一个完整 prompt 一次性转给 `code2workspace_agent`；不要在 OpenClaw 主会话拆成 Docker 阶段和 WDL 阶段分别问。
6. 如果外部 agent 失败或超时，直接报告失败原因，不要换成本地手工执行。
