import {
  AuiIf,
  ComposerPrimitive,
  MessagePrimitive,
  ThreadPrimitive,
  useAuiState,
} from "@assistant-ui/react";
import { ArrowUpRight, Bot, LoaderCircle, Sparkles, User } from "lucide-react";

import { MarkdownBlock } from "@/components/thread/MarkdownBlock";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

type WorkspaceThreadProps = {
  sessionTitle: string | null;
  sessionStatus: string | null;
};

export function WorkspaceThread({
  sessionTitle,
  sessionStatus,
}: WorkspaceThreadProps) {
  return (
    <ThreadPrimitive.Root className="flex h-full min-h-0 flex-col overflow-hidden rounded-[2rem] border border-[var(--line)] bg-[var(--panel)] shadow-[var(--panel-shadow)]">
      <div className="border-b border-[var(--line)] px-6 py-5">
        <div className="flex items-center justify-between gap-4">
          <div>
            <div className="text-[0.68rem] font-semibold uppercase tracking-[0.24em] text-[var(--muted-ink)]">
              Deep Work Surface
            </div>
            <h2 className="mt-1 font-[var(--font-display)] text-2xl text-[var(--ink)]">
              {sessionTitle || "No session selected"}
            </h2>
          </div>
          <div className={cn("status-chip", `status-chip-${sessionStatus || "idle"}`)}>
            {sessionStatus || "idle"}
          </div>
        </div>
      </div>

      <ThreadPrimitive.Viewport className="flex min-h-0 flex-1 flex-col overflow-y-auto px-6 py-5">
        <AuiIf condition={(s) => s.thread.isEmpty}>
          <ThreadWelcome />
        </AuiIf>

        <div className="flex flex-col gap-5">
          <ThreadPrimitive.Messages>
            {() => <ThreadMessage />}
          </ThreadPrimitive.Messages>
        </div>
      </ThreadPrimitive.Viewport>

      <div className="border-t border-[var(--line)] px-5 py-4">
        <ComposerPrimitive.Root className="flex flex-col gap-3">
          <div className="rounded-[1.6rem] border border-[var(--line)] bg-[var(--panel-soft)] p-3 shadow-[inset_0_1px_0_rgba(255,255,255,0.5)]">
            <ComposerPrimitive.Input
              rows={1}
              autoFocus
              placeholder="Describe the next repo task, debugging target, or experiment you want the agent to run..."
              className="min-h-14 w-full resize-none bg-transparent px-2 py-2 font-[var(--font-body)] text-[15px] leading-7 text-[var(--ink)] outline-none placeholder:text-[var(--muted-ink)]"
            />
          </div>
          <div className="flex items-center justify-between gap-4">
            <div className="text-xs tracking-[0.06em] text-[var(--muted-ink)] uppercase">
              One-shot agent run through the current Python backend
            </div>
            <ComposerSendButton />
          </div>
        </ComposerPrimitive.Root>
      </div>
    </ThreadPrimitive.Root>
  );
}

function ThreadWelcome() {
  return (
    <div className="flex min-h-[360px] flex-1 items-center justify-center">
      <div className="grid max-w-3xl gap-4 md:grid-cols-2">
        <div className="rounded-[1.8rem] border border-[var(--line)] bg-[var(--paper)] p-6 shadow-[var(--card-shadow)]">
          <div className="flex items-center gap-3 text-[var(--accent-strong)]">
            <Sparkles className="h-5 w-5" />
            <span className="text-xs font-semibold uppercase tracking-[0.2em]">
              What This Panel Does
            </span>
          </div>
          <h3 className="mt-4 font-[var(--font-display)] text-2xl text-[var(--ink)]">
            Turn a session into a reproducible agent run.
          </h3>
          <p className="mt-3 text-[15px] leading-7 text-[var(--muted-ink)]">
            This workspace sends one prompt into the existing `code2workspace`
            execution path, keeps the session transcript visible, and lets you
            inspect raw run logs without leaving the page.
          </p>
        </div>
        <div className="rounded-[1.8rem] border border-[var(--line)] bg-[var(--panel-soft)] p-6">
          <div className="text-xs font-semibold uppercase tracking-[0.2em] text-[var(--muted-ink)]">
            Suggested First Moves
          </div>
          <ul className="mt-4 grid gap-3 text-[15px] leading-7 text-[var(--ink)]">
            <li className="rounded-[1.2rem] border border-[var(--line)] bg-[var(--paper)] px-4 py-3">
              “Run the shortest real Docker validation path for this repository.”
            </li>
            <li className="rounded-[1.2rem] border border-[var(--line)] bg-[var(--paper)] px-4 py-3">
              “Inspect the last failure and propose the minimum harness change.”
            </li>
            <li className="rounded-[1.2rem] border border-[var(--line)] bg-[var(--paper)] px-4 py-3">
              “Summarize this repo and identify the fastest executable test.”
            </li>
          </ul>
        </div>
      </div>
    </div>
  );
}

function ThreadMessage() {
  const role = useAuiState((state) => state.message.role);
  return role === "user" ? <UserMessage /> : <AssistantMessage />;
}

function AssistantMessage() {
  return (
    <MessagePrimitive.Root className="grid grid-cols-[36px_minmax(0,1fr)] gap-4">
      <div className="mt-1 flex h-9 w-9 items-center justify-center rounded-full bg-[var(--accent-soft)] text-[var(--accent-strong)]">
        <Bot className="h-4 w-4" />
      </div>
      <div className="rounded-[1.5rem] rounded-tl-sm border border-[var(--line)] bg-[var(--paper)] px-5 py-4 shadow-[var(--card-shadow)]">
        <div className="mb-2 text-[0.68rem] font-semibold uppercase tracking-[0.2em] text-[var(--muted-ink)]">
          Assistant
        </div>
        <MessagePrimitive.Parts>
          {({ part }) => {
            if (part.type === "text") return <MarkdownBlock />;
            return (
              <pre className="overflow-x-auto rounded-2xl bg-[var(--panel-strong)] p-4 text-xs text-[var(--ink)]">
                {JSON.stringify(part, null, 2)}
              </pre>
            );
          }}
        </MessagePrimitive.Parts>
      </div>
    </MessagePrimitive.Root>
  );
}

function UserMessage() {
  return (
    <MessagePrimitive.Root className="grid grid-cols-[minmax(0,1fr)_36px] gap-4">
      <div className="rounded-[1.5rem] rounded-tr-sm border border-[var(--line)] bg-[var(--ink)] px-5 py-4 text-[var(--ink-inverse)] shadow-[var(--card-shadow)]">
        <div className="mb-2 text-[0.68rem] font-semibold uppercase tracking-[0.2em] text-[var(--ink-inverse-soft)]">
          User
        </div>
        <div className="text-[15px] leading-7">
          <MessagePrimitive.Parts>
            {({ part }) =>
              part.type === "text" ? (
                <span>{part.text}</span>
              ) : (
                <span>{JSON.stringify(part)}</span>
              )
            }
          </MessagePrimitive.Parts>
        </div>
      </div>
      <div className="mt-1 flex h-9 w-9 items-center justify-center rounded-full bg-[var(--ink)] text-[var(--paper)]">
        <User className="h-4 w-4" />
      </div>
    </MessagePrimitive.Root>
  );
}

function ComposerSendButton() {
  const isRunning = useAuiState((state) => state.thread.isRunning);
  const canSend = useAuiState((state) => state.composer.canSend);

  if (isRunning) {
    return (
      <div className="inline-flex items-center gap-2 rounded-full border border-[var(--line)] bg-[var(--paper)] px-4 py-2 text-sm text-[var(--muted-ink)]">
        <LoaderCircle className="h-4 w-4 animate-spin" />
        Run queued or executing
      </div>
    );
  }

  return (
    <ComposerPrimitive.Send asChild>
      <Button variant="primary" className="h-11 min-w-[154px] rounded-full px-5" disabled={!canSend}>
        Launch run
        <ArrowUpRight className="h-4 w-4" />
      </Button>
    </ComposerPrimitive.Send>
  );
}
