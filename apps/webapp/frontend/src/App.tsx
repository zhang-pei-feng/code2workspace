import { type ReactNode, useCallback, useEffect, useMemo, useState } from "react";
import { BrowserRouter, Navigate, Route, Routes, useNavigate, useParams } from "react-router-dom";
import { Activity, AlertTriangle, PanelsTopLeft } from "lucide-react";

import { createRun, createSession, deleteSession, getSession, listSessions } from "@/api";
import { RunInspector } from "@/components/run/RunInspector";
import { SessionSidebar } from "@/components/session/SessionSidebar";
import { SessionRuntimeProvider } from "@/components/thread/SessionRuntimeProvider";
import { WorkspaceThread } from "@/components/thread/WorkspaceThread";
import { cn, formatTimestamp } from "@/lib/utils";
import type { SessionPayload, SessionSummary } from "@/types";

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<WorkspaceRoute />} />
        <Route path="/sessions/:sessionId" element={<WorkspaceRoute />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  );
}

function WorkspaceRoute() {
  const { sessionId } = useParams();
  const navigate = useNavigate();

  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [activeSession, setActiveSession] = useState<SessionPayload | null>(null);
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);
  const [sessionsLoading, setSessionsLoading] = useState(true);
  const [sessionLoading, setSessionLoading] = useState(false);
  const [actionBusy, setActionBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const refreshSessions = useCallback(async () => {
    setSessionsLoading(true);
    try {
      const payload = await listSessions();
      setSessions(payload);
      setError(null);
      return payload;
    } catch (err) {
      const message = err instanceof Error ? err.message : "Failed to load sessions";
      setError(message);
      return [];
    } finally {
      setSessionsLoading(false);
    }
  }, []);

  const loadSession = useCallback(async (id: string) => {
    setSessionLoading(true);
    try {
      const payload = await getSession(id);
      setActiveSession(payload);
      setSelectedRunId((current) => {
        if (current && payload.runs.some((run) => run.id === current)) return current;
        return payload.runs[0]?.id || null;
      });
      setError(null);
      return payload;
    } catch (err) {
      const message = err instanceof Error ? err.message : "Failed to load session";
      setError(message);
      setActiveSession(null);
      return null;
    } finally {
      setSessionLoading(false);
    }
  }, []);

  useEffect(() => {
    void refreshSessions();
  }, [refreshSessions]);

  useEffect(() => {
    if (!sessionId) {
      setActiveSession(null);
      setSelectedRunId(null);
      return;
    }
    void loadSession(sessionId);
  }, [loadSession, sessionId]);

  useEffect(() => {
    if (sessionId || sessionsLoading || sessions.length === 0) return;
    navigate(`/sessions/${sessions[0].id}`, { replace: true });
  }, [navigate, sessionId, sessions, sessionsLoading]);

  const liveRun = useMemo(() => {
    if (!activeSession) return null;
    return (
      activeSession.runs.find((run) => {
        const status = run.status.toLowerCase();
        return status === "queued" || status === "running";
      }) || null
    );
  }, [activeSession]);

  useEffect(() => {
    if (!liveRun || !activeSession) return;
    const currentSessionId = activeSession.session.id;
    const timer = window.setInterval(() => {
      void loadSession(currentSessionId);
      void refreshSessions();
    }, 1500);
    return () => window.clearInterval(timer);
  }, [activeSession, liveRun, loadSession, refreshSessions]);

  const handleCreateSession = useCallback(async () => {
    setActionBusy(true);
    try {
      const created = await createSession();
      await refreshSessions();
      navigate(`/sessions/${created.id}`);
      setNotice("New session created.");
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create session");
    } finally {
      setActionBusy(false);
    }
  }, [navigate, refreshSessions]);

  const handleDeleteSession = useCallback(async () => {
    if (!activeSession) return;
    setActionBusy(true);
    try {
      const currentId = activeSession.session.id;
      await deleteSession(currentId);
      const refreshed = await refreshSessions();
      const nextId = refreshed[0]?.id;
      if (nextId) {
        navigate(`/sessions/${nextId}`);
      } else {
        navigate("/");
      }
      setNotice("Session deleted.");
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to delete session");
    } finally {
      setActionBusy(false);
    }
  }, [activeSession, navigate, refreshSessions]);

  const handleSubmitPrompt = useCallback(
    async (prompt: string) => {
      setActionBusy(true);
      try {
        let targetId = activeSession?.session.id || sessionId || null;
        if (!targetId) {
          const created = await createSession();
          targetId = created.id;
          await refreshSessions();
          navigate(`/sessions/${targetId}`);
        }
        const queued = await createRun(targetId, prompt);
        await loadSession(targetId);
        await refreshSessions();
        setSelectedRunId(queued.run_id);
        setNotice("Run queued successfully.");
        setError(null);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to queue run");
        throw err;
      } finally {
        setActionBusy(false);
      }
    },
    [activeSession, loadSession, navigate, refreshSessions, sessionId],
  );

  const runs = activeSession?.runs || [];
  const isRunning = Boolean(liveRun) || actionBusy;

  return (
    <div className="min-h-screen bg-[var(--shell)] text-[var(--ink)]">
      <div className="mx-auto flex min-h-screen max-w-[1800px] flex-col px-4 py-4 md:px-6 md:py-6">
        <header className="rounded-[2rem] border border-[var(--line)] bg-[var(--paper)] px-6 py-5 shadow-[var(--panel-shadow)]">
          <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
            <div>
              <div className="text-[0.68rem] font-semibold uppercase tracking-[0.24em] text-[var(--muted-ink)]">
                Code2Workspace control plane
              </div>
              <h1 className="mt-1 font-[var(--font-display)] text-4xl leading-none text-[var(--ink)]">
                Agent sessions, one-shot runs, and raw logs in one workspace.
              </h1>
              <p className="mt-3 max-w-4xl text-[15px] leading-7 text-[var(--muted-ink)]">
                The frontend has been rebuilt on top of an assistant-ui-compatible
                React workspace so it can stay close to the current Python
                backend now and evolve toward richer deepagents state later.
              </p>
            </div>
            <div className="grid gap-3 sm:grid-cols-3">
              <HeaderCard
                icon={<PanelsTopLeft className="h-4 w-4" />}
                label="Sessions"
                value={String(sessions.length)}
                caption={sessionsLoading ? "Refreshing…" : "Tracked in SQLite"}
              />
              <HeaderCard
                icon={<Activity className="h-4 w-4" />}
                label="Latest state"
                value={activeSession?.session.status || "idle"}
                caption={
                  activeSession?.session.updated_at
                    ? `Updated ${formatTimestamp(activeSession.session.updated_at)}`
                    : "No session selected"
                }
              />
              <HeaderCard
                icon={<AlertTriangle className="h-4 w-4" />}
                label="Active run"
                value={liveRun?.status || "none"}
                caption={liveRun ? `Started ${formatTimestamp(liveRun.started_at || liveRun.created_at)}` : "No queued run"}
              />
            </div>
          </div>
        </header>

        <div className="mt-4 grid min-h-0 flex-1 gap-4 xl:grid-cols-[320px_minmax(0,1fr)_420px]">
          <SessionSidebar
            sessions={sessions}
            activeSessionId={activeSession?.session.id || null}
            loading={sessionsLoading || actionBusy}
            onCreateSession={handleCreateSession}
            onRefresh={refreshSessions}
            onSelectSession={(id) => navigate(`/sessions/${id}`)}
            onDeleteSession={handleDeleteSession}
          />

          <div className="grid min-h-0 grid-rows-[auto_minmax(0,1fr)] gap-4">
            {(notice || error) && (
              <div
                className={cn(
                  "rounded-[1.5rem] border px-4 py-3 text-sm",
                  error
                    ? "border-[color:rgba(203,70,53,0.3)] bg-[color:rgba(203,70,53,0.08)] text-[color:rgb(156,48,34)]"
                    : "border-[color:rgba(36,110,92,0.24)] bg-[color:rgba(36,110,92,0.08)] text-[color:rgb(36,110,92)]",
                )}
              >
                {error || notice}
              </div>
            )}
            <SessionRuntimeProvider
              sessionId={activeSession?.session.id || null}
              messages={activeSession?.messages || []}
              isRunning={isRunning}
              onSubmit={handleSubmitPrompt}
            >
              <WorkspaceThread
                sessionTitle={activeSession?.session.title || null}
                sessionStatus={liveRun?.status || activeSession?.session.status || null}
              />
            </SessionRuntimeProvider>
          </div>

          <RunInspector runs={runs} selectedRunId={selectedRunId} onSelectRun={setSelectedRunId} />
        </div>
      </div>
    </div>
  );
}

function HeaderCard({
  icon,
  label,
  value,
  caption,
}: {
  icon: ReactNode;
  label: string;
  value: string;
  caption: string;
}) {
  return (
    <div className="rounded-[1.4rem] border border-[var(--line)] bg-[var(--panel-soft)] px-4 py-4">
      <div className="flex items-center gap-2 text-[var(--muted-ink)]">
        {icon}
        <span className="text-[0.68rem] font-semibold uppercase tracking-[0.18em]">{label}</span>
      </div>
      <div className="mt-3 font-[var(--font-display)] text-2xl text-[var(--ink)]">{value}</div>
      <div className="mt-1 text-sm text-[var(--muted-ink)]">{caption}</div>
    </div>
  );
}
