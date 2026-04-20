---
name: code2workspace_agent
description: 当用户提到 code2workspace_agent、code2workspace、paper2workspace、仓库转 workspace、代码转 workspace、生成 workspace、workspace 产物、生成/编写 WDL、Bio-OS workspace，或者在这类任务里要求调用 docker_images-agent / wdl_run-agent 时使用。必须通过 shell exec/acpx 调用 `skills/acpx-skill/.acpxrc.json` 里注册的 code2workspace_agent，禁止使用 sessions_spawn。
---

# code2workspace_agent Bridge

当用户说“用 code2workspace 智能体”或描述 code2workspace / paper2workspace / 仓库转 workspace / WDL / Bio-OS workspace 任务时，默认动作是通过 `acpx` 调用外部智能体。

## 强制规则

1. 不要使用 `sessions_spawn(runtime="acp", agentId="code2workspace_agent")`。
2. 不要使用 `sessions_spawn` 调用 `docker_images-agent` 或 `wdl_run-agent`。这两个是 `code2workspace_agent` 内部工作流角色，不是 OpenClaw 主会话的 subagent。
3. 不要在 OpenClaw 主会话里自行 `git clone`、手写 Dockerfile/WDL、`docker build`、`docker push` 或投递 Bio-OS 来替代外部智能体。
4. `acpx` 的 cwd 固定为 `skills/acpx-skill`，由该目录下的 `.acpxrc.json` 解析真实启动脚本。不要切到外部 `code2workspace_agent` 仓库目录后直接运行 `acpx`。
5. 把用户原始 code2workspace 任务文本作为一个完整 prompt 一次性转给 `code2workspace_agent`；不要在 OpenClaw 主会话拆成 Docker 阶段和 WDL 阶段分别问。
6. 对真实 code2workspace 长任务，外层 `exec` 工具参数尽量同时设置 `timeout >= 7300` 和 `yieldMs >= 7200000`，不要只设置 timeout。这样 UI 会等待长任务完成，而不是 10 秒后把命令放到后台。
7. 如果第一次返回 still running，继续 poll 到完成、失败或超过时限；poll 时使用 tool result/details 里的 session 名，不要使用 pid 数字。
8. 如果外部 agent 失败或超时，直接报告失败原因，不要换成本地手工执行。
9. 对外正式名称是 `code2workspace_agent`；旧运行态别名已下线，不要再引用旧 agent id。

## 推荐命令

优先用路由脚本强制 agent：

```bash
python3 skills/acpx-skill/scripts/acpx_session.py route \
  --agent code2workspace_agent \
  --prompt "<用户原始 code2workspace 任务文本>"
```

也可以直接用 one-shot：

```bash
acpx --cwd skills/acpx-skill \
  --format text \
  --timeout 7200 \
  code2workspace_agent exec "<用户原始 code2workspace 任务文本>"
```

输出给用户时，保留外部智能体返回的真实状态、产物路径、工作流 id、失败原因和终端日志摘要；不要编造缺失的测试结果。
