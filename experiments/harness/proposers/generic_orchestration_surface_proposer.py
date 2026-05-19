"""Rule-based proposer for the generic orchestration harness."""

from __future__ import annotations

import json
import os
from pathlib import Path


def _load_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _append_lines_if_missing(path: Path, lines: list[str]) -> bool:
    content = path.read_text(encoding="utf-8")
    changed = False
    for line in lines:
        if line in content:
            continue
        if not content.endswith("\n"):
            content += "\n"
        content += f"- {line}\n"
        changed = True
    if changed:
        path.write_text(content, encoding="utf-8")
    return changed


def _surface_path(current_dir: Path, manifest: dict[str, object], name: str) -> Path | None:
    item = manifest.get(name)
    if not isinstance(item, dict):
        return None
    relative = item.get("file")
    if not isinstance(relative, str):
        return None
    return current_dir.parent / relative


def main() -> int:
    workspace = Path(os.environ["CODE2WORKSPACE_HARNESS_WORKSPACE"])
    current_dir = Path(os.environ["CODE2WORKSPACE_HARNESS_CURRENT"])
    proposal_path = Path(os.environ["CODE2WORKSPACE_HARNESS_PROPOSAL"])
    manifest = _load_json(workspace / "surface_manifest.json")
    train_summary = _load_json(workspace / "train_summary.json")

    component_means = train_summary.get("component_means", {})
    if not isinstance(component_means, dict):
        component_means = {}
    findings: list[str] = []
    for outcome in train_summary.get("outcomes", []):
        if not isinstance(outcome, dict):
            continue
        for finding in outcome.get("findings", []):
            if isinstance(finding, str):
                findings.append(finding)

    changed_surfaces: list[str] = []
    reasons: list[str] = []

    init_generic = _surface_path(current_dir, manifest, "init_generic")
    if init_generic is not None and (
        float(component_means.get("graph_fit_score", 0.0)) < 90.0
        or float(component_means.get("efficiency_score", 0.0)) < 90.0
    ):
        changed = _append_lines_if_missing(
            init_generic,
            [
                "For a narrow local-code question, prefer one evidence/context worker plus compose and summarize instead of splitting into both context and solution lanes by default.",
                "Only add a second parallel worker when it answers a clearly different sub-question or materially changes the downstream conclusion.",
            ],
        )
        if changed:
            changed_surfaces.append("init_generic")
            reasons.append("tighten graph size and reduce over-orchestration on narrow generic tasks")

    worker_context = _surface_path(current_dir, manifest, "worker_context")
    if worker_context is not None and float(component_means.get("evidence_score", 0.0)) < 80.0:
        changed = _append_lines_if_missing(
            worker_context,
            [
                "When one concrete local file or one fetched source is enough for the answer, prefer reading that artifact fully over spawning broader search loops.",
                "If the answer relies on one primary source, state why that source is sufficient and what evidence is still missing.",
            ],
        )
        if changed:
            changed_surfaces.append("worker_context")
            reasons.append("improve evidence sufficiency and keep evidence collection bounded")

    compose_generic = _surface_path(current_dir, manifest, "compose_generic")
    if compose_generic is not None and (
        float(component_means.get("answer_score", 0.0)) < 85.0
        or any("evidence boundaries" in finding for finding in findings)
    ):
        changed = _append_lines_if_missing(
            compose_generic,
            [
                "For evidence-backed answers, include one compact line that separates direct evidence from inference or remaining uncertainty.",
                "If the task asked for a short answer, preserve that brevity while still naming the key artifact, source, or file that supports the conclusion.",
            ],
        )
        if changed:
            changed_surfaces.append("compose_generic")
            reasons.append("make final answers preserve evidence boundaries without inflating them")

    worker_solution = _surface_path(current_dir, manifest, "worker_solution")
    if worker_solution is not None and float(component_means.get("efficiency_score", 0.0)) < 90.0:
        changed = _append_lines_if_missing(
            worker_solution,
            [
                "Do not keep exploring after the needed command result, patch, or computed value is already available for compose.",
            ],
        )
        if changed:
            changed_surfaces.append("worker_solution")
            reasons.append("reduce unnecessary post-solution tool loops")

    summary = "No surface edits proposed."
    if changed_surfaces:
        summary = (
            "Adjust generic guidance to shrink unnecessary graphs, keep evidence bounded, "
            "and preserve compact evidence boundaries in final answers."
        )
    proposal_path.write_text(
        "# Proposal\n\n"
        f"- Summary: {summary}\n"
        f"- Why this should help: {'; '.join(reasons) if reasons else 'No repeated weakness detected from current train summary.'}\n"
        f"- Surfaces changed: {', '.join(changed_surfaces) if changed_surfaces else 'none'}\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
