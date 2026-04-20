import { Plus, RefreshCw, Search, Trash2 } from "lucide-react";
import { useMemo, useState } from "react";

import { Button } from "@/components/ui/button";
import { cn, formatTimestamp, statusTone, truncate } from "@/lib/utils";
import type { SessionSummary } from "@/types";

type SessionSidebarProps = {
  sessions: SessionSummary[];
  activeSessionId: string | null;
  loading: boolean;
  onCreateSession: () => Promise<void>;
  onRefresh: () => Promise<void>;
  onSelectSession: (sessionId: string) => void;
  onDeleteSession: () => Promise<void>;
};

export function SessionSidebar({
  sessions,
  activeSessionId,
  loading,
  onCreateSession,
  onRefresh,
  onSelectSession,
  onDeleteSession,
}: SessionSidebarProps) {
  const [query, setQuery] = useState("");
  const filtered = useMemo(() => {
    const normalized = query.trim().toLowerCase();
    if (!normalized) return sessions;
    return sessions.filter((session) =>
      [session.title, session.status, session.latest_run_status, session.last_message_preview]
        .filter(Boolean)
        .join(" ")
        .toLowerCase()
        .includes(normalized),
    );
  }, [query, sessions]);

  return (
    <aside className="flex min-h-0 flex-col rounded-[2rem] border border-[var(--line)] bg-[var(--paper)] shadow-[var(--panel-shadow)]">
      <div className="border-b border-[var(--line)] px-5 py-5">
        <div className="flex items-start justify-between gap-4">
          <div>
            <div className="text-[0.68rem] font-semibold uppercase tracking-[0.22em] text-[var(--muted-ink)]">
              Session Registry
            </div>
            <h2 className="mt-1 font-[var(--font-display)] text-2xl text-[var(--ink)]">
              Lab Threads
            </h2>
          </div>
          <div className="rounded-full bg-[var(--panel-soft)] px-3 py-1 text-xs font-semibold uppercase tracking-[0.12em] text-[var(--muted-ink)]">
            {sessions.length} total
          </div>
        </div>
        <div className="mt-4 flex items-center gap-2">
          <Button variant="primary" className="flex-1" onClick={() => void onCreateSession()}>
            <Plus className="h-4 w-4" />
            New session
          </Button>
          <Button variant="secondary" size="icon" onClick={() => void onRefresh()} disabled={loading}>
            <RefreshCw className={cn("h-4 w-4", loading && "animate-spin")} />
          </Button>
          <Button variant="danger" size="icon" onClick={() => void onDeleteSession()} disabled={!activeSessionId}>
            <Trash2 className="h-4 w-4" />
          </Button>
        </div>
        <label className="mt-4 flex items-center gap-3 rounded-full border border-[var(--line)] bg-[var(--panel-soft)] px-4 py-3">
          <Search className="h-4 w-4 text-[var(--muted-ink)]" />
          <input
            className="w-full bg-transparent text-sm text-[var(--ink)] outline-none placeholder:text-[var(--muted-ink)]"
            placeholder="Filter sessions by title, status, or recent message"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
          />
        </label>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto px-3 py-3">
        <div className="grid gap-2">
          {filtered.length === 0 ? (
            <div className="rounded-[1.5rem] border border-dashed border-[var(--line)] bg-[var(--panel-soft)] px-4 py-6 text-sm text-[var(--muted-ink)]">
              {query ? "No sessions match the current filter." : "No sessions yet. Create one to begin."}
            </div>
          ) : (
            filtered.map((session) => {
              const active = session.id === activeSessionId;
              const tone = statusTone(session.latest_run_status || session.status);
              return (
                <button
                  key={session.id}
                  type="button"
                  onClick={() => onSelectSession(session.id)}
                  className={cn(
                    "group rounded-[1.5rem] border px-4 py-4 text-left transition-all",
                    active
                      ? "border-[var(--accent-strong)] bg-[var(--accent-soft)] shadow-[var(--card-shadow)]"
                      : "border-[var(--line)] bg-[var(--paper)] hover:bg-[var(--panel-soft)]",
                  )}
                >
                  <div className="flex items-center justify-between gap-3">
                    <div className="font-medium text-[var(--ink)]">
                      {truncate(session.title, 48) || "Untitled session"}
                    </div>
                    <div className={cn("status-dot", `status-dot-${tone}`)} />
                  </div>
                  <div className="mt-2 line-clamp-2 min-h-[2.6rem] text-sm leading-6 text-[var(--muted-ink)]">
                    {truncate(session.last_message_preview, 120) || "No messages yet."}
                  </div>
                  <div className="mt-3 flex items-center justify-between text-[0.68rem] font-semibold uppercase tracking-[0.14em] text-[var(--muted-ink)]">
                    <span>{session.run_count} runs</span>
                    <span>{formatTimestamp(session.updated_at)}</span>
                  </div>
                </button>
              );
            })
          )}
        </div>
      </div>
    </aside>
  );
}
