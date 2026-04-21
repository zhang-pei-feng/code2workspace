"""Soft planner routing middleware for project orchestrator skills."""

from __future__ import annotations

import asyncio
import importlib.util
import logging
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Any, NotRequired, TypedDict

from langchain.agents.middleware.types import (
    AgentMiddleware,
    AgentState,
    ModelRequest,
    ModelResponse,
    PrivateStateAttr,
)
if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable


logger = logging.getLogger(__name__)


class PlannerLane(TypedDict):
    lane_id: str
    title: str
    selected_skill: str | None


class PlannerRecommendation(TypedDict):
    task_type: str
    selected_skill: str | None
    fresh_run_required: bool
    needs_isolated_workspace: bool
    lanes: list[PlannerLane]


class PlannerRoutingState(AgentState):
    planner_recommendation: NotRequired[
        Annotated[PlannerRecommendation, PrivateStateAttr]
    ]


def _planning_script_path() -> Path:
    return Path(__file__).resolve().parents[3] / ".code2workspace" / "skills" / "planning-guide" / "scripts" / "planning_tool.py"


@lru_cache(maxsize=1)
def _load_build_plan() -> Callable[[str], dict[str, Any]] | None:
    path = _planning_script_path()
    if not path.exists():
        logger.warning("Planning guide script not found at %s", path)
        return None

    spec = importlib.util.spec_from_file_location(
        "code2workspace_cli._planning_tool_runtime",
        path,
    )
    if spec is None or spec.loader is None:
        logger.warning("Could not load planning guide script from %s", path)
        return None

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    build_plan = getattr(module, "build_plan", None)
    if not callable(build_plan):
        logger.warning("Planning guide script does not expose build_plan()")
        return None
    return build_plan


def _latest_human_text(state: dict[str, Any]) -> str | None:
    messages = state.get("messages") or []
    for message in reversed(messages):
        if getattr(message, "type", None) != "human":
            continue
        content = getattr(message, "content", None)
        if isinstance(content, str) and content.strip():
            return content
        if content:
            rendered = str(content).strip()
            if rendered:
                return rendered
    return None


def build_planner_recommendation(task: str) -> PlannerRecommendation | None:
    build_plan = _load_build_plan()
    if build_plan is None:
        return None

    plan = build_plan(task)
    selected_skill = plan.get("selected_skill")
    lanes = [
        {
            "lane_id": lane["lane_id"],
            "title": lane["title"],
            "selected_skill": lane.get("selected_skill"),
        }
        for lane in plan.get("lanes", [])
    ]

    if selected_skill is None and plan.get("domain") != "multi-lane":
        return None

    return PlannerRecommendation(
        task_type=str(plan["task_type"]),
        selected_skill=selected_skill,
        fresh_run_required=bool(plan.get("fresh_run_required")),
        needs_isolated_workspace=bool(plan.get("needs_isolated_workspace")),
        lanes=lanes,
    )


def _recommendation_text(recommendation: PlannerRecommendation) -> str:
    lines = [
        "## Planner Recommendation",
        "",
        "This is soft routing guidance, not a mandatory dispatch.",
        f"- Task type: `{recommendation['task_type']}`",
    ]
    if recommendation["selected_skill"]:
        lines.append(f"- Recommended orchestrator skill: `{recommendation['selected_skill']}`")
    if recommendation["fresh_run_required"]:
        lines.append("- Fresh run recommended: yes")
    if recommendation["needs_isolated_workspace"]:
        lines.append("- Use an isolated workspace or isolated run directory when historical outputs would pollute the answer.")
    if recommendation["lanes"]:
        lines.extend(["", "### Suggested Lanes"])
        for lane in recommendation["lanes"]:
            selected = lane["selected_skill"] or "general-agent"
            lines.append(
                f"- `{lane['title']}` (`{lane['lane_id']}`) -> prefer `{selected}`"
            )
    lines.extend(
        [
            "",
            "When an orchestrator skill is recommended, read that skill before acting if the task still matches its scope.",
            "For benchmark or workspace-building tasks, write or update a user-facing report before expanding scope with extra reruns or extra cases.",
        ]
    )
    return "\n".join(lines)


class PlannerRoutingMiddleware(AgentMiddleware):
    """Inject soft planner recommendations into agent state and system prompt."""

    state_schema = PlannerRoutingState

    def before_agent(
        self, state: PlannerRoutingState, runtime: Any  # noqa: ARG002
    ) -> dict[str, PlannerRecommendation] | None:
        if state.get("planner_recommendation") is not None:
            return None
        task = _latest_human_text(state)
        if not task:
            return None
        recommendation = build_planner_recommendation(task)
        if recommendation is None:
            return None
        return {"planner_recommendation": recommendation}

    async def abefore_agent(
        self, state: PlannerRoutingState, runtime: Any  # noqa: ARG002
    ) -> dict[str, PlannerRecommendation] | None:
        return await asyncio.to_thread(self.before_agent, state, runtime)

    def wrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], ModelResponse],
    ) -> ModelResponse:
        recommendation = request.state.get("planner_recommendation")
        if recommendation is None:
            return handler(request)
        base_system_prompt = request.system_prompt or ""
        recommendation_text = _recommendation_text(recommendation)
        system_prompt = (
            f"{base_system_prompt}\n\n{recommendation_text}"
            if base_system_prompt
            else recommendation_text
        )
        return handler(request.override(system_prompt=system_prompt))

    async def awrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], Awaitable[ModelResponse]],
    ) -> ModelResponse:
        recommendation = request.state.get("planner_recommendation")
        if recommendation is None:
            return await handler(request)
        base_system_prompt = request.system_prompt or ""
        recommendation_text = _recommendation_text(recommendation)
        system_prompt = (
            f"{base_system_prompt}\n\n{recommendation_text}"
            if base_system_prompt
            else recommendation_text
        )
        return await handler(request.override(system_prompt=system_prompt))
