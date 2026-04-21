#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SKILL_ROOT = Path(__file__).resolve().parents[1]
WORKSPACE_ROOT = SKILL_ROOT.parents[1]
STATE_PATH = WORKSPACE_ROOT / ".openclaw" / "acpx-session-map.json"
EXTERNAL_AGENTS_ROOT = Path(
    os.environ.get("OPENCLAW_EXTERNAL_AGENTS_ROOT", WORKSPACE_ROOT / "external-agents")
)
CODE2WORKSPACE_AGENT_ROOT = Path(
    os.environ.get(
        "CODE2WORKSPACE_AGENT_ROOT",
        EXTERNAL_AGENTS_ROOT / "code2workspace_agent",
    )
)
CODE2WORKSPACE_WORKSPACE_ROOT = Path(
    os.environ.get(
        "CODE2WORKSPACE_AGENT_WORKSPACE_ROOT",
        CODE2WORKSPACE_AGENT_ROOT / "workspace",
    )
)
CODE2WORKSPACE_NATIVE_ACP_COMMAND = os.environ.get(
    "CODE2WORKSPACE_AGENT_ACP_COMMAND",
    str(SKILL_ROOT / "scripts" / "agent_wrappers" / "code2workspace_agent-acp.sh"),
)

DEFAULT_ALIASES = {
    "benchmark_agent": "benchmark-main",
    "code2workspace_agent": "code2workspace-main",
    "data_governance_agent": "db-governance",
    "deep_research_agent": "deep-research",
    "report_agent": "report-main",
}

ONE_SHOT_AGENTS = {
    "code2workspace_agent",
    "deep_research_agent",
    "report_agent",
}

AGENT_TIMEOUT_SECONDS = {
    "benchmark_agent": 3600,
    "code2workspace_agent": 7200,
    "deep_research_agent": 300,
    "report_agent": 1800,
}

REPORT_PATH_RE = re.compile(r"([^\s`'\"<>]*reports/[^\s`'\"<>]*final_report\.md)")

ROUTES = [
    (
        "report_agent",
        (
            "report_agent",
            "报告智能体",
        ),
    ),
    (
        "deep_research_agent",
        (
            "deep_research_agent",
            "深度研究",
            "deep research",
            "联网调研",
            "搜资料",
            "来源链接",
            "research",
            "对比方案",
            "文献",
        ),
    ),
    (
        "data_governance_agent",
        (
            "data_governance_agent",
            "数据治理",
            "数据库治理",
            "data governance",
            "source",
            "数据源",
            "snapshot",
            "mysql",
            "lineage",
            "mutation",
            "导入状态",
        ),
    ),
    (
        "code2workspace_agent",
        (
            "code2workspace_agent",
            "paper2workspace",
            "paper to workspace",
            "code2workspace",
            "code to workspace",
            "仓库转 workspace",
            "仓库转workspace",
            "代码转 workspace",
            "代码转workspace",
            "生成 workspace",
            "创建 workspace",
            "workspace artifact",
            "workspace 产物",
            "生成 wdl",
        ),
    ),
    (
        "benchmark_agent",
        (
            "benchmark_agent",
            "benchmark",
            "看代码",
            "改代码",
            "仓库分析",
            "本地命令",
            "分析仓库",
            "检查脚本",
            "代码分析",
            "工作流复用",
            "复用工作流",
            "复用已有工作流",
            "复用已有 workflow",
            "已有 workflow 复跑",
            "workflow reuse",
            "reuse workflow",
        ),
    ),
]

REPORT_EXPLICIT_MARKERS = (
    "report_agent",
    "报告智能体",
)

REPORT_TASK_MARKERS = (
    "报告",
    "report",
    "简报",
    "周报",
    "流行情况",
    "流行态势",
    "风险评估",
    "risk assessment",
    "生成",
    "撰写",
    "写一份",
)

RESPIRATORY_TOPIC_MARKERS = (
    "呼吸系统",
    "呼吸道",
    "呼吸系统病原",
    "呼吸道病原",
    "新冠",
    "covid",
    "sars-cov-2",
    "流感",
    "influenza",
    "rsv",
    "毒株",
    "变异株",
    "谱系",
    "lineage",
    "variant",
)


@dataclass(frozen=True)
class SessionMetadata:
    id: str
    session_id: str
    agent_session_id: str
    agent: str
    cwd: str
    name: str
    created: str
    last_activity: str
    last_prompt: str
    closed: str
    closed_at: str
    pid: str
    agent_started_at: str
    last_exit_code: str
    last_exit_signal: str
    last_exit_at: str
    disconnect_reason: str
    history_entries: str

    def as_dict(self) -> dict[str, str]:
        return {
            "id": self.id,
            "session_id": self.session_id,
            "agent_session_id": self.agent_session_id,
            "agent": self.agent,
            "cwd": self.cwd,
            "name": self.name,
            "created": self.created,
            "last_activity": self.last_activity,
            "last_prompt": self.last_prompt,
            "closed": self.closed,
            "closed_at": self.closed_at,
            "pid": self.pid,
            "agent_started_at": self.agent_started_at,
            "last_exit_code": self.last_exit_code,
            "last_exit_signal": self.last_exit_signal,
            "last_exit_at": self.last_exit_at,
            "disconnect_reason": self.disconnect_reason,
            "history_entries": self.history_entries,
        }


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    if hasattr(args, "prompt_file"):
        args.prompt = resolve_prompt_text(args)
    try:
        return args.func(args)
    except RuntimeError as exc:
        print_json({"error": str(exc)})
        return 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Persist and reuse acpx sessions for workspace agents."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    ensure_parser = subparsers.add_parser("ensure", help="Ensure a session exists.")
    add_agent_args(ensure_parser)
    ensure_parser.set_defaults(func=run_ensure)

    send_parser = subparsers.add_parser("send", help="Send a prompt using a saved alias.")
    add_agent_args(send_parser)
    add_prompt_args(send_parser)
    send_parser.add_argument(
        "--format",
        default="quiet",
        choices=["text", "json", "quiet"],
        help="acpx output format.",
    )
    send_parser.set_defaults(func=run_send)

    route_parser = subparsers.add_parser("route", help="Route prompt to a default agent.")
    add_prompt_args(route_parser)
    route_parser.add_argument(
        "--agent",
        choices=sorted(DEFAULT_ALIASES),
        help="Force a registered acpx agent instead of inferring from the prompt.",
    )
    route_parser.add_argument(
        "--format",
        default="quiet",
        choices=["text", "json", "quiet"],
        help="acpx output format.",
    )
    route_parser.set_defaults(func=run_route)

    status_parser = subparsers.add_parser("status", help="Show saved session metadata.")
    add_agent_args(status_parser)
    status_parser.set_defaults(func=run_status)

    history_parser = subparsers.add_parser("history", help="Show recent session history.")
    add_agent_args(history_parser)
    history_parser.add_argument("--limit", type=int, default=10, help="History limit.")
    history_parser.set_defaults(func=run_history)

    return parser


def add_agent_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--agent", required=True, help="Registered acpx agent name.")
    parser.add_argument("--alias", required=True, help="Stable workspace alias.")


def add_prompt_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--prompt", help="Prompt text.")
    parser.add_argument("--prompt-file", help="Path to a UTF-8 file containing prompt text.")


def resolve_prompt_text(args: argparse.Namespace) -> str:
    if args.prompt and args.prompt_file:
        raise RuntimeError("Use either --prompt or --prompt-file, not both.")
    if args.prompt_file:
        return Path(args.prompt_file).read_text(encoding="utf-8")
    if args.prompt:
        return args.prompt
    raise RuntimeError("Missing prompt. Provide --prompt or --prompt-file.")


def canonical_agent_name(agent: str) -> str:
    return agent


def run_ensure(args: argparse.Namespace) -> int:
    agent = canonical_agent_name(args.agent)
    session_name = build_session_name(agent, args.alias)
    run_acpx([agent, "sessions", "ensure", "--name", session_name], quiet=False)
    metadata = fetch_session_metadata(agent, session_name)
    save_mapping(agent, args.alias, metadata)
    print_json(
        {
            "agent": agent,
            "requested_agent": args.agent,
            "alias": args.alias,
            "session_name": session_name,
            "session_id": metadata.id,
            "agent_session_id": metadata.session_id,
            "state_path": str(STATE_PATH),
        }
    )
    return 0


def run_send(args: argparse.Namespace) -> int:
    agent = canonical_agent_name(args.agent)
    session_name = build_session_name(agent, args.alias)
    prompt = normalize_prompt(agent, args.prompt)
    env_overrides = resolve_prompt_env(agent, args.prompt)
    if should_use_one_shot(agent, session_name, args.prompt):
        output = run_acpx(
            ["--format", args.format, agent, "exec", prompt],
            quiet=True,
            env_overrides=env_overrides,
            agent=agent,
        )
        response = materialize_report_response(agent, output)
        print_json(
            {
                "agent": agent,
                "requested_agent": args.agent,
                "alias": args.alias,
                "mode": "one-shot-fallback",
                "reason": fallback_reason(agent, session_name, args.prompt),
                "response": response.rstrip(),
            }
        )
        return 0
    run_acpx([agent, "sessions", "ensure", "--name", session_name], quiet=False)
    metadata = fetch_session_metadata(agent, session_name)
    save_mapping(agent, args.alias, metadata)
    output = run_acpx(
        ["--format", args.format, agent, "-s", session_name, prompt],
        quiet=True,
        env_overrides=env_overrides,
        agent=agent,
    )
    response = materialize_report_response(agent, output)
    print_json(
        {
            "agent": agent,
            "requested_agent": args.agent,
            "alias": args.alias,
            "session_name": session_name,
            "session_id": metadata.id,
            "agent_session_id": metadata.session_id,
            "response": response.rstrip(),
        }
    )
    return 0


def run_route(args: argparse.Namespace) -> int:
    agent = canonical_agent_name(args.agent or infer_agent(args.prompt))
    alias = DEFAULT_ALIASES[agent]
    prompt = normalize_prompt(agent, args.prompt)
    session_name = build_session_name(agent, alias)
    env_overrides = resolve_prompt_env(agent, args.prompt)
    if agent in ONE_SHOT_AGENTS or should_use_one_shot(agent, session_name, args.prompt):
        output = run_acpx(
            ["--format", args.format, agent, "exec", prompt],
            quiet=True,
            env_overrides=env_overrides,
            agent=agent,
        )
        response = materialize_report_response(agent, output)
        print_json(
            {
                "agent": agent,
                "alias": alias,
                "mode": "one-shot",
                "reason": fallback_reason(agent, session_name, args.prompt),
                "response": response.rstrip(),
            }
        )
        return 0

    run_acpx([agent, "sessions", "ensure", "--name", session_name], quiet=False)
    metadata = fetch_session_metadata(agent, session_name)
    save_mapping(agent, alias, metadata)
    output = run_acpx(
        ["--format", args.format, agent, "-s", session_name, prompt],
        quiet=True,
        env_overrides=env_overrides,
        agent=agent,
    )
    response = materialize_report_response(agent, output)
    print_json(
        {
            "agent": agent,
            "alias": alias,
            "session_name": session_name,
            "session_id": metadata.id,
            "agent_session_id": metadata.session_id,
            "response": response.rstrip(),
        }
    )
    return 0


def materialize_report_response(agent: str, output: str) -> str:
    if agent == "code2workspace_agent":
        return materialize_code2workspace_response(output)
    if agent != "report_agent":
        return output
    match = REPORT_PATH_RE.search(output)
    if not match:
        return output
    report_path = Path(match.group(1))
    try:
        report_text = report_path.read_text(encoding="utf-8").strip()
    except OSError:
        return output
    return report_text or output


def materialize_code2workspace_response(output: str) -> str:
    if output.strip():
        return output
    workspace_root = CODE2WORKSPACE_WORKSPACE_ROOT
    latest_workspace = latest_child_dir(workspace_root)
    if latest_workspace is None:
        return (
            "code2workspace_agent returned an empty final response and no task "
            f"workspace was found under {workspace_root}."
        )
    log_dir = latest_workspace / "log"
    known_logs = [
        str(path)
        for name in ("agent.log", "model_io.log", "tool_call.log", "task_complete.log")
        if (path := log_dir / name).exists()
    ]
    log_text = ", ".join(known_logs) if known_logs else f"{log_dir} (missing or empty)"
    return (
        "code2workspace_agent returned an empty final response. "
        f"Latest task workspace: {latest_workspace}. "
        f"Available logs: {log_text}. "
        "Treat this as NOT COMPLETED unless those logs contain real successful local validation evidence."
    )


def latest_child_dir(path: Path) -> Path | None:
    try:
        children = [child for child in path.iterdir() if child.is_dir()]
    except OSError:
        return None
    if not children:
        return None
    return max(children, key=lambda child: child.stat().st_mtime)


def run_status(args: argparse.Namespace) -> int:
    agent = canonical_agent_name(args.agent)
    session_name = build_session_name(agent, args.alias)
    metadata = fetch_session_metadata(agent, session_name)
    save_mapping(agent, args.alias, metadata)
    print_json(
        {
            "agent": agent,
            "requested_agent": args.agent,
            "alias": args.alias,
            "session_name": session_name,
            "session_id": metadata.id,
            "agent_session_id": metadata.session_id,
            "metadata": metadata.as_dict(),
            "state_path": str(STATE_PATH),
        }
    )
    return 0


def run_history(args: argparse.Namespace) -> int:
    agent = canonical_agent_name(args.agent)
    session_name = build_session_name(agent, args.alias)
    metadata = fetch_session_metadata(agent, session_name)
    save_mapping(agent, args.alias, metadata)
    output = run_acpx(
        [agent, "sessions", "history", "--limit", str(args.limit), session_name],
        quiet=True,
    )
    print_json(
        {
            "agent": agent,
            "requested_agent": args.agent,
            "alias": args.alias,
            "session_name": session_name,
            "session_id": metadata.id,
            "agent_session_id": metadata.session_id,
            "history": output.rstrip(),
        }
    )
    return 0


def build_session_name(agent: str, alias: str) -> str:
    return f"{agent}--{alias.strip().replace(' ', '-')}"


def run_acpx(
    args: list[str],
    *,
    quiet: bool,
    env_overrides: dict[str, str] | None = None,
    agent: str | None = None,
) -> str:
    acpx_cwd = resolve_acpx_cwd(agent)
    command = ["acpx", "--cwd", str(acpx_cwd)]
    agent_timeout = AGENT_TIMEOUT_SECONDS.get(agent or "")
    if agent_timeout:
        command.extend(["--timeout", str(agent_timeout)])
    command.extend(args)
    env = os.environ.copy()
    if env_overrides:
        env.update(env_overrides)
    try:
        completed = subprocess.run(
            command,
            cwd=acpx_cwd,
            env=env,
            capture_output=True,
            text=True,
            check=False,
            timeout=(agent_timeout + 120) if agent_timeout else None,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(
            f"acpx command timed out after {exc.timeout}s for {agent or 'unknown agent'}"
        ) from exc
    if completed.returncode != 0:
        msg = completed.stderr.strip() or completed.stdout.strip() or "acpx command failed"
        raise RuntimeError(msg)
    if not quiet and completed.stdout:
        print(completed.stdout.rstrip(), file=sys.stderr)
    return completed.stdout


def resolve_acpx_cwd(agent: str | None) -> Path:
    if agent != "code2workspace_agent":
        return WORKSPACE_ROOT
    return ensure_code2workspace_task_workspace()


def ensure_code2workspace_task_workspace() -> Path:
    CODE2WORKSPACE_WORKSPACE_ROOT.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    candidate = CODE2WORKSPACE_WORKSPACE_ROOT / f"workspace_{timestamp}"
    suffix = 1
    while candidate.exists():
        candidate = CODE2WORKSPACE_WORKSPACE_ROOT / f"workspace_{timestamp}_{suffix:02d}"
        suffix += 1
    candidate.mkdir(parents=True)
    (candidate / ".acpxrc.json").write_text(
        json.dumps(
            {
                "agents": {
                    "code2workspace_agent": {
                        "command": CODE2WORKSPACE_NATIVE_ACP_COMMAND
                    }
                }
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return candidate


def infer_agent(prompt: str) -> str:
    text = prompt.lower()
    if is_report_agent_prompt(text):
        return "report_agent"
    if is_workflow_reuse_prompt(text):
        return "benchmark_agent"
    for agent, keywords in ROUTES:
        if any(keyword in text for keyword in keywords):
            return agent
    return "benchmark_agent"


def is_report_agent_prompt(text: str) -> bool:
    if any(marker in text for marker in REPORT_EXPLICIT_MARKERS):
        return True
    return any(marker in text for marker in REPORT_TASK_MARKERS) and any(
        marker in text for marker in RESPIRATORY_TOPIC_MARKERS
    )


def is_workflow_reuse_prompt(text: str) -> bool:
    workflow_markers = ("工作流", "workflow")
    reuse_markers = ("复用", "复跑", "已有", "reuse", "rerun", "existing")
    return any(marker in text for marker in workflow_markers) and any(
        marker in text for marker in reuse_markers
    )


def normalize_prompt(agent: str, prompt: str) -> str:
    if is_strict_output_prompt(prompt):
        return prompt
    if agent == "deep_research_agent":
        return (
            f"{prompt}\n\n要求：\n"
            "1. 给出简洁结论。\n"
            "2. 优先抓取并阅读来源内容后再总结分析，不要把链接列表当作答案；只在必要时附少量关键来源链接或来源说明。\n"
            "3. 不要展开冗长研究过程。"
        )
    if agent == "report_agent":
        return (
            f"{prompt}\n\n要求：\n"
            "1. 使用 report_agent 完成正式中文报告，不要改由其他 agent。\n"
            "2. 如果涉及新冠、流感、RSV 或呼吸系统病原，优先检索近期官方/权威来源，并说明数据日期和地域范围。\n"
            "3. 不要编造具体数字；无法确认的数据明确标注为信息缺口或口径限制。\n"
            "4. 对风险评估报告，按用户给出的评估维度组织内容。\n"
            "5. 不要向用户反问澄清，不要停在“请提供来源/定义/时间范围”。如果证据不足或命名不确定，在报告正文中列为证据缺口并继续完成一次性报告。\n"
            "6. 输出完整报告正文，至少包含标题、核心要点、评估维度、综合研判、风险提示和来源说明。\n"
            "7. 不要只输出“报告文件”路径或让用户点击本地文件；用户无法访问服务器本地路径。"
        )
    if agent == "benchmark_agent":
        return (
            f"{prompt}\n\n上下文路径：{EXTERNAL_AGENTS_ROOT}\n\n要求：\n"
            "1. 把 benchmark_agent 理解为 superagent 仓库里的通用代码/仓库分析 agent。\n"
            "2. 如果涉及本地仓库，请尽量绑定路径或命令结果。\n"
            "3. workflow 默认按本地执行路径理解，不要假设远端工作流平台。\n"
            "4. 不要把泛化猜测当成仓库事实。"
        )
    if agent == "code2workspace_agent":
        return (
            f"{prompt}\n\n上下文路径：{CODE2WORKSPACE_AGENT_ROOT}\n\n要求：\n"
            "1. 你是 code2workspace_agent，负责把用户给出的仓库、代码或任务转成可运行 workspace 产物。\n"
            "2. 使用适配层分配的当前工作目录保存中间文件、Docker/WDL、本地执行结果和日志。\n"
            "3. 如果需要 Dockerfile、WDL 或真实运行验证，必须返回真实产物路径、真实状态和失败原因；不要编造成功。\n"
            "4. 不要把当前 OpenClaw workspace 当作你的任务工作目录。\n"
            "5. 这是一次 ACP one-shot 自动执行请求；用户已经授权完整执行。不要等待用户确认计划，不要只写 todo 后停止；如果使用 todo，必须立刻把第一项设为 in_progress 并继续执行。\n"
            "6. 对任务中提到的 docker_images-agent 和 wdl_run-agent，按你的内部流程顺序调用；不要把它们交还给 OpenClaw 主会话。"
        )
    return prompt


def should_use_one_shot(agent: str, session_name: str, prompt: str) -> bool:
    if agent in ONE_SHOT_AGENTS:
        return True
    if agent == "benchmark_agent" and is_short_chat_prompt(prompt):
        return True
    if session_has_inflight_process(agent, session_name):
        return True
    metadata = safe_fetch_session_metadata(agent, session_name)
    if metadata and is_stale_session(metadata):
        return True
    return False


def fallback_reason(agent: str, session_name: str, prompt: str) -> str:
    if agent in ONE_SHOT_AGENTS:
        return "agent-default-one-shot"
    if agent == "benchmark_agent" and is_short_chat_prompt(prompt):
        return "short-chat-uses-one-shot"
    if session_has_inflight_process(agent, session_name):
        return "session-busy"
    metadata = safe_fetch_session_metadata(agent, session_name)
    if metadata and is_stale_session(metadata):
        return "session-stale"
    return "persistent-session-allowed"


def is_short_chat_prompt(prompt: str) -> bool:
    stripped = " ".join(prompt.split()).strip()
    if not stripped:
        return False
    if len(stripped) > 24:
        return False
    chat_markers = ("你好", "hello", "hi", "在吗", "在不在", "回复我一句")
    lower = stripped.lower()
    return any(marker in stripped for marker in chat_markers) or any(
        marker in lower for marker in chat_markers
    )

def resolve_prompt_env(agent: str, prompt: str) -> dict[str, str]:
    del agent
    del prompt
    return {}


def safe_fetch_session_metadata(agent: str, session_name: str) -> SessionMetadata | None:
    try:
        return fetch_session_metadata(agent, session_name)
    except RuntimeError:
        return None


def is_stale_session(metadata: SessionMetadata) -> bool:
    if metadata.closed.lower() == "yes":
        return True
    if metadata.disconnect_reason not in {"-", "", "none"}:
        return True
    if metadata.last_exit_at not in {"-", "", "none"}:
        return True
    if metadata.pid not in {"-", "", "none"} and not is_pid_alive(metadata.pid):
        return True
    return False


def is_pid_alive(pid: str) -> bool:
    if not pid.isdigit():
        return False
    try:
        os.kill(int(pid), 0)
    except OSError:
        return False
    return True


def session_has_inflight_process(agent: str, session_name: str) -> bool:
    current_pid = os.getpid()
    output = subprocess.run(
        ["ps", "-eo", "pid=,args="],
        cwd=WORKSPACE_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if output.returncode != 0:
        return False
    target = f" {agent} -s {session_name} "
    for line in output.stdout.splitlines():
        parts = line.strip().split(None, 1)
        if len(parts) != 2 or not parts[0].isdigit():
            continue
        pid = int(parts[0])
        if pid == current_pid:
            continue
        cmd = parts[1]
        if target in f" {cmd} " and " exec " not in f" {cmd} ":
            return True
    return False


def is_strict_output_prompt(prompt: str) -> bool:
    text = prompt.lower()
    markers = (
        "只回复",
        "仅回复",
        "reply exactly",
        "reply only",
        "do not use any tools",
        "不要使用任何工具",
    )
    return any(marker in text for marker in markers)


def fetch_session_metadata(agent: str, session_name: str) -> SessionMetadata:
    output = run_acpx([agent, "sessions", "show", session_name], quiet=True)
    data = parse_key_value_output(output)
    return SessionMetadata(
        id=data.get("id", "-"),
        session_id=data.get("sessionId", "-"),
        agent_session_id=data.get("agentSessionId", "-"),
        agent=data.get("agent", "-"),
        cwd=data.get("cwd", "-"),
        name=data.get("name", session_name),
        created=data.get("created", "-"),
        last_activity=data.get("lastActivity", "-"),
        last_prompt=data.get("lastPrompt", "-"),
        closed=data.get("closed", "-"),
        closed_at=data.get("closedAt", "-"),
        pid=data.get("pid", "-"),
        agent_started_at=data.get("agentStartedAt", "-"),
        last_exit_code=data.get("lastExitCode", "-"),
        last_exit_signal=data.get("lastExitSignal", "-"),
        last_exit_at=data.get("lastExitAt", "-"),
        disconnect_reason=data.get("disconnectReason", "-"),
        history_entries=data.get("historyEntries", "-"),
    )


def parse_key_value_output(output: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for line in output.splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        result[key.strip()] = value.strip()
    return result


def save_mapping(agent: str, alias: str, metadata: SessionMetadata) -> None:
    state = load_state()
    agents = state.setdefault("agents", {})
    agent_state = agents.setdefault(agent, {})
    agent_state[alias] = {
        "session_name": metadata.name,
        "session_id": metadata.id,
        "agent_session_id": metadata.session_id,
        "cwd": metadata.cwd,
        "updated_at": now_iso(),
        "metadata": metadata.as_dict(),
    }
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n")


def load_state() -> dict[str, Any]:
    if not STATE_PATH.exists():
        return {"version": 1, "agents": {}}
    return json.loads(STATE_PATH.read_text())


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def print_json(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    raise SystemExit(main())
