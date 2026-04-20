"""Shared data shapes for the minimal web workspace."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SessionSummary:
    """Sidebar summary for one web session."""

    id: str
    title: str
    status: str
    created_at: str
    updated_at: str
    last_message_preview: str | None
    latest_run_id: str | None
    latest_run_status: str | None
    run_count: int


@dataclass(frozen=True)
class MessageRecord:
    """One persisted session message."""

    id: str
    session_id: str
    role: str
    content: str
    created_at: str
    run_id: str | None


@dataclass(frozen=True)
class RunRecord:
    """One one-shot execution run."""

    id: str
    session_id: str
    prompt: str
    status: str
    created_at: str
    started_at: str | None
    finished_at: str | None
    exit_code: int | None
    output: str
    error: str | None
