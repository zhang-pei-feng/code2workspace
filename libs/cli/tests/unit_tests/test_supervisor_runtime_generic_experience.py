from __future__ import annotations

from pathlib import Path

from code2workspace.orchestration_runtime import TaskNode
from code2workspace_cli.supervisor_runtime import _build_worker_prompt


def test_build_worker_prompt_includes_generic_experience_guidance(monkeypatch) -> None:
    monkeypatch.setattr(
        "code2workspace_cli.supervisor_runtime.generic_experience_guidance_lines",
        lambda **_kwargs: [
            "Retrieved generic experience (demo): applies when the task is a narrow local explanation",
            "Preferred trajectory from experience: direct_or_minimal; nodes=init_generic, worker_context, summarize; tool rhythm=bounded",
        ],
    )
    node = TaskNode(
        node_id="init_generic",
        title="Plan generic graph",
        objective="Plan the generic graph.",
        capability_bundles=["plan", "task_manage", "validate"],
        metadata={
            "task": "请只基于本地代码，说明 generic trace artifact 现在记录了什么。",
            "task_type": "generic",
            "guidance_ids": ["generic_qa"],
        },
    )

    prompt = _build_worker_prompt(node=node, workspace_root=Path("/tmp/supervisor-workspace"))

    assert "Retrieved generic experience (demo)" in prompt
    assert "Preferred trajectory from experience" in prompt
