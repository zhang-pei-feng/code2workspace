import { type ReactNode } from "react";
import { FileSearch, ScrollText, TerminalSquare } from "lucide-react";

import { cn, formatTimestamp, statusTone, truncate } from "@/lib/utils";
import type { RunRecord } from "@/types";

type RunInspectorProps = {
  runs: RunRecord[];
  selectedRunId: string | null;
  onSelectRun: (runId: string) => void;
};

export function RunInspector({
  runs,
  selectedRunId,
  onSelectRun,
}: RunInspectorProps) {
  const selectedRun =
    runs.find((run) => run.id === selectedRunId) || runs[0] || null;

  return (
    <aside className="grid min-h-0 grid-rows-[auto_minmax(0,1fr)] gap-4">
      <section className="rounded-[2rem] border border-[var(--line)] bg-[var(--paper)] shadow-[var(--panel-shadow)]">
        <div className="border-b border-[var(--line)] px-5 py-5">
          <div className="text-[0.68rem] font-semibold uppercase tracking-[0.22em] text-[var(--muted-ink)]">
            Run Ledger
          </div>
          <h2 className="mt-1 font-[var(--font-display)] text-2xl text-[var(--ink)]">
            Execution history
          </h2>
        </div>
        <div className="max-h-[320px] overflow-y-auto px-3 py-3">
          <div className="grid gap-2">
            {runs.length === 0 ? (
              <div className="rounded-[1.4rem] border border-dashed border-[var(--line)] bg-[var(--panel-soft)] px-4 py-6 text-sm text-[var(--muted-ink)]">
                No runs yet for this session.
              </div>
            ) : (
              runs.map((run, index) => {
                const active = run.id === selectedRun?.id;
                const tone = statusTone(run.status);
                return (
                  <button
                    key={run.id}
                    type="button"
                    onClick={() => onSelectRun(run.id)}
                    className={cn(
                      "rounded-[1.35rem] border px-4 py-4 text-left transition-all",
                      active
                        ? "border-[var(--accent-strong)] bg-[var(--accent-soft)] shadow-[var(--card-shadow)]"
                        : "border-[var(--line)] bg-[var(--paper)] hover:bg-[var(--panel-soft)]",
                    )}
                  >
                    <div className="flex items-center justify-between gap-3">
                      <span className="font-medium text-[var(--ink)]">
                        {index === 0 ? "Latest run" : `Run ${runs.length - index}`}
                      </span>
                      <div className={cn("status-chip", `status-chip-${tone}`)}>{run.status}</div>
                    </div>
                    <div className="mt-2 text-sm leading-6 text-[var(--muted-ink)]">
                      {truncate(run.prompt, 100)}
                    </div>
                    <div className="mt-3 text-[0.68rem] font-semibold uppercase tracking-[0.14em] text-[var(--muted-ink)]">
                      {formatTimestamp(run.created_at)}
                    </div>
                  </button>
                );
              })
            )}
          </div>
        </div>
      </section>

      <section className="grid min-h-0 grid-rows-[auto_auto_minmax(0,1fr)] gap-4 rounded-[2rem] border border-[var(--line)] bg-[var(--paper)] p-4 shadow-[var(--panel-shadow)]">
        <div className="grid gap-3 md:grid-cols-3">
          <MetricCard
            icon={<TerminalSquare className="h-4 w-4" />}
            label="Status"
            value={selectedRun?.status || "idle"}
            tone={statusTone(selectedRun?.status)}
          />
          <MetricCard
            icon={<FileSearch className="h-4 w-4" />}
            label="Exit code"
            value={selectedRun?.exit_code === null || selectedRun?.exit_code === undefined ? "pending" : String(selectedRun.exit_code)}
            tone={selectedRun?.exit_code === 0 ? "success" : selectedRun ? "danger" : "neutral"}
          />
          <MetricCard
            icon={<ScrollText className="h-4 w-4" />}
            label="Finished"
            value={selectedRun?.finished_at ? formatTimestamp(selectedRun.finished_at) : "in progress"}
            tone="neutral"
          />
        </div>

        <div className="rounded-[1.5rem] border border-[var(--line)] bg-[var(--panel-soft)] p-4">
          <div className="text-[0.68rem] font-semibold uppercase tracking-[0.18em] text-[var(--muted-ink)]">
            Prompt
          </div>
          <div className="mt-2 whitespace-pre-wrap text-sm leading-7 text-[var(--ink)]">
            {selectedRun?.prompt || "Select a run to inspect its prompt and log."}
          </div>
          {selectedRun?.started_at && (
            <div className="mt-4 text-[0.68rem] font-semibold uppercase tracking-[0.14em] text-[var(--muted-ink)]">
              Started {formatTimestamp(selectedRun.started_at)}
            </div>
          )}
        </div>

        <div className="min-h-0 overflow-hidden rounded-[1.5rem] border border-[var(--line)] bg-[var(--panel-strong)]">
          <div className="border-b border-[var(--line)] px-4 py-3 font-[var(--font-mono)] text-[0.72rem] uppercase tracking-[0.18em] text-[var(--muted-ink)]">
            Raw run output
          </div>
          <pre className="h-full min-h-[280px] overflow-auto px-4 py-4 font-[var(--font-mono)] text-[12px] leading-6 text-[var(--ink)]">
            {selectedRun?.output || "(no output captured yet)"}
          </pre>
        </div>
      </section>
    </aside>
  );
}

function MetricCard({
  icon,
  label,
  value,
  tone,
}: {
  icon: ReactNode;
  label: string;
  value: string;
  tone: string;
}) {
  return (
    <div className="rounded-[1.4rem] border border-[var(--line)] bg-[var(--panel-soft)] px-4 py-4">
      <div className="flex items-center gap-2 text-[var(--muted-ink)]">
        {icon}
        <span className="text-[0.68rem] font-semibold uppercase tracking-[0.18em]">
          {label}
        </span>
      </div>
      <div className="mt-3 flex items-center gap-3">
        <span className={cn("status-dot", `status-dot-${tone}`)} />
        <span className="font-[var(--font-display)] text-xl text-[var(--ink)]">
          {value}
        </span>
      </div>
    </div>
  );
}
