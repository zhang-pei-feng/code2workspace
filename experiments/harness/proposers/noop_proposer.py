"""Minimal proposer contract smoke test.

This script intentionally makes no surface edits. It only records that the
proposer workspace contract is reachable and writable.
"""

from __future__ import annotations

import os
from pathlib import Path


def main() -> int:
    workspace = Path(os.environ["CODE2WORKSPACE_HARNESS_WORKSPACE"])
    proposal_path = Path(os.environ["CODE2WORKSPACE_HARNESS_PROPOSAL"])
    proposal_path.write_text(
        "# Proposal\n\n"
        "- Summary: no-op proposer smoke run\n"
        "- Why this should help: verifies the proposer workspace contract only\n"
        "- Surfaces changed: none\n",
        encoding="utf-8",
    )
    (workspace / "noop.txt").write_text("noop\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
