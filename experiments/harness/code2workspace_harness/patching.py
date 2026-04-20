"""Surface materialization and temporary workspace patching."""

from __future__ import annotations

import contextlib
from collections.abc import Iterator
from pathlib import Path

from .core import Experiment, Variant, repo_root


def build_baseline_variant(experiment: Experiment) -> Variant:
    """Build the baseline variant from configured surface bases."""
    return Variant(
        label="baseline",
        changed_surfaces=(),
        values={name: surface.base_value for name, surface in experiment.surfaces.items()},
    )


def build_variant(*, experiment: Experiment, label: str, values: dict[str, str]) -> Variant:
    """Build one variant from raw values."""
    changed_surfaces = tuple(
        sorted(
            name
            for name, surface in experiment.surfaces.items()
            if values[name] != surface.base_value
        )
    )
    return Variant(label=label, changed_surfaces=changed_surfaces, values=values)


@contextlib.contextmanager
def workspace_override_context(experiment: Experiment, variant: Variant) -> Iterator[None]:
    """Temporarily replace workspace-file surfaces inside the repo."""
    backups: dict[Path, str | None] = {}
    try:
        for name, surface in experiment.surfaces.items():
            target = repo_root() / surface.target
            backups[target] = target.read_text(encoding="utf-8") if target.exists() else None
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(variant.values[name], encoding="utf-8")
        yield
    finally:
        for target, original in backups.items():
            if original is None:
                if target.exists():
                    target.unlink()
            else:
                target.write_text(original, encoding="utf-8")
