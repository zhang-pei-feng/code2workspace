"""Prompt generation and repository list handling for one-shot experiments."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from pathlib import Path


def repo_root() -> Path:
    """Return the project repository root."""
    return Path(__file__).resolve().parents[2]


DEFAULT_PROMPT_TEMPLATE = (
    repo_root() / "experiments" / "harness" / "surfaces" / "one_shot_prompt.txt"
)
DEFAULT_TARGETS_FILE = repo_root() / "experiments" / "oneshot" / "targets.txt"


def repo_name_from_url(repo_url: str) -> str:
    """Extract the repository name from a GitHub URL."""
    cleaned = repo_url.rstrip("/")
    name = cleaned.rsplit("/", 1)[-1]
    return name.removesuffix(".git")


def artifact_prefix(repo_name: str) -> str:
    """Return a filesystem-safe artifact prefix."""
    return re.sub(r"[^a-zA-Z0-9_]+", "_", repo_name).strip("_")


def load_repo_urls(targets_file: Path | None = None) -> list[str]:
    """Load normalized repository URLs from a targets file."""
    source = targets_file or DEFAULT_TARGETS_FILE
    lines = source.read_text(encoding="utf-8").splitlines()
    return [line.strip() for line in lines if line.strip() and not line.lstrip().startswith("#")]


@dataclass(frozen=True)
class RepoTaskSpec:
    """Derived task parameters for one repository."""

    repo_url: str
    repo_name: str
    image_name: str
    artifact_prefix: str

    @property
    def dockerfile_name(self) -> str:
        """Return the required Dockerfile name."""
        return f"{self.artifact_prefix}_Dockerfile"

    @property
    def wdl_name(self) -> str:
        """Return the WDL filename."""
        return f"{self.artifact_prefix}.wdl"

    def to_dict(self) -> dict[str, str]:
        """Return the spec as a plain dictionary."""
        return asdict(self)


def build_repo_task_spec(repo_url: str) -> RepoTaskSpec:
    """Build one normalized task spec from a repo URL."""
    repo_name = repo_name_from_url(repo_url)
    return RepoTaskSpec(
        repo_url=repo_url,
        repo_name=repo_name,
        image_name=repo_name.lower(),
        artifact_prefix=artifact_prefix(repo_name),
    )


def build_repo_task_prompt(repo_url: str, *, template_path: Path | None = None) -> str:
    """Build the standard Docker + WDL one-shot task prompt."""
    spec = build_repo_task_spec(repo_url)
    template = (template_path or DEFAULT_PROMPT_TEMPLATE).read_text(encoding="utf-8")
    return template.format(
        repo_url=spec.repo_url,
        repo_name=spec.repo_name,
        image_name=spec.image_name,
        artifact_prefix=spec.artifact_prefix,
        dockerfile_name=spec.dockerfile_name,
        wdl_name=spec.wdl_name,
    )
