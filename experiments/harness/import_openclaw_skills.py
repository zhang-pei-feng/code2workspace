"""Import reusable OpenClaw workspace skills into this repository."""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path


DEFAULT_SOURCE = Path("/home/zhangpf/.openclaw/workspace/skills")
DEFAULT_DEST = Path(__file__).resolve().parent / "skills" / "openclaw"
EXCLUDED_NAMES = {
    "all_skills_2026-04-13.tar.gz",
    "cli-prompt-setup-bundle",
    "cli-prompt-setup-bundle.tar.gz",
}


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE, help="Source OpenClaw skills directory")
    parser.add_argument("--dest", type=Path, default=DEFAULT_DEST, help="Destination directory inside this repo")
    parser.add_argument("--clean", action="store_true", help="Delete the destination first")
    return parser.parse_args()


def import_openclaw_skills(*, source: Path = DEFAULT_SOURCE, dest: Path = DEFAULT_DEST, clean: bool = False) -> list[Path]:
    """Copy supported OpenClaw skills into the repository."""
    if not source.exists():
        msg = f"source skills directory does not exist: {source}"
        raise FileNotFoundError(msg)

    if clean and dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True, exist_ok=True)

    copied: list[Path] = []
    for item in sorted(source.iterdir(), key=lambda path: path.name.lower()):
        if item.name in EXCLUDED_NAMES:
            continue
        target = dest / item.name
        if item.is_dir():
            shutil.copytree(item, target, dirs_exist_ok=True)
            copied.append(target)
            continue
        if item.is_file():
            shutil.copy2(item, target)
            copied.append(target)
    return copied


def main() -> int:
    """Run the importer."""
    args = parse_args()
    copied = import_openclaw_skills(source=args.source, dest=args.dest, clean=args.clean)
    for path in copied:
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
