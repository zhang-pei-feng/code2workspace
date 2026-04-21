"""Tests for soft planner routing middleware."""

from __future__ import annotations

from unittest.mock import AsyncMock, Mock

from code2workspace_cli.planner_routing import (
    PlannerRoutingMiddleware,
    build_planner_recommendation,
)


def test_build_planner_recommendation_for_benchmark() -> None:
    recommendation = build_planner_recommendation(
        "请对 8 个仓库执行本地 docker + wdl benchmark 并汇总结果"
    )

    assert recommendation is not None
    assert recommendation["task_type"] == "benchmark"
    assert recommendation["selected_skill"] == "benchmark-workflow-orchestrator"
    assert recommendation["fresh_run_required"] is True
    assert recommendation["needs_isolated_workspace"] is True


def test_build_planner_recommendation_for_paper2workspace() -> None:
    recommendation = build_planner_recommendation(
        "把一个 xxx.github 仓库变成有工作流的工作空间"
    )

    assert recommendation is not None
    assert recommendation["task_type"] == "paper2workspace"
    assert recommendation["selected_skill"] == "paper2workspace-orchestrator"


def test_build_planner_recommendation_for_ambiguous_task() -> None:
    recommendation = build_planner_recommendation("检查一下当前目录并总结")
    assert recommendation is None


def test_wrap_model_call_injects_soft_routing_prompt() -> None:
    middleware = PlannerRoutingMiddleware()
    request = Mock()
    request.system_prompt = "Base system prompt"
    request.state = {
        "planner_recommendation": {
            "task_type": "benchmark",
            "selected_skill": "benchmark-workflow-orchestrator",
            "fresh_run_required": True,
            "needs_isolated_workspace": True,
            "lanes": [
                {
                    "lane_id": "benchmark",
                    "title": "Benchmark",
                    "selected_skill": "benchmark-workflow-orchestrator",
                }
            ],
        }
    }
    overridden_request = Mock()
    request.override.return_value = overridden_request
    handler = Mock(return_value="ok")

    result = middleware.wrap_model_call(request, handler)

    request.override.assert_called_once()
    system_prompt = request.override.call_args.kwargs["system_prompt"]
    assert "benchmark-workflow-orchestrator" in system_prompt
    assert "soft routing" in system_prompt.lower()
    assert "write or update a user-facing report" in system_prompt.lower()
    assert result == "ok"


async def test_awrap_model_call_injects_soft_routing_prompt() -> None:
    middleware = PlannerRoutingMiddleware()
    request = Mock()
    request.system_prompt = "Base system prompt"
    request.state = {
        "planner_recommendation": {
            "task_type": "paper2workspace",
            "selected_skill": "paper2workspace-orchestrator",
            "fresh_run_required": True,
            "needs_isolated_workspace": True,
            "lanes": [
                {
                    "lane_id": "workspace",
                    "title": "Workspace",
                    "selected_skill": "paper2workspace-orchestrator",
                }
            ],
        }
    }
    overridden_request = Mock()
    request.override.return_value = overridden_request
    handler = AsyncMock(return_value="ok")

    result = await middleware.awrap_model_call(request, handler)

    request.override.assert_called_once()
    system_prompt = request.override.call_args.kwargs["system_prompt"]
    assert "paper2workspace-orchestrator" in system_prompt
    assert "isolated workspace" in system_prompt.lower()
    assert result == "ok"
