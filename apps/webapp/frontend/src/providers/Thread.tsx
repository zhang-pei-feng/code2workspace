import { getApiKey } from "@/lib/api-key";
import { Thread } from "@langchain/langgraph-sdk";
import { useQueryState } from "nuqs";
import {
  createContext,
  useContext,
  ReactNode,
  useCallback,
  useState,
  Dispatch,
  SetStateAction,
} from "react";
import { createClient } from "./client";
import { buildRenamedThreadMetadata } from "@/components/thread/history/thread-title";
import { buildThreadMetadataWithModel } from "@/components/thread/history/thread-model";

interface WebThreadSummary {
  thread_id: string;
  assistant_id: string;
  cwd: string | null;
  active_status: string;
  created_at: string | null;
  updated_at: string | null;
  message_count: number;
  initial_prompt: string | null;
  title: string | null;
  model_spec: string | null;
}

interface ThreadPageResult {
  threads: Thread[];
  total: number;
  page: number;
  pageSize: number;
}

interface ThreadContextType {
  getThreads: (page?: number, pageSize?: number) => Promise<ThreadPageResult>;
  createThread: () => Promise<Thread>;
  renameThread: (thread: Thread, title: string) => Promise<Thread>;
  deleteThread: (thread: Thread) => Promise<void>;
  setThreadModel: (thread: Thread, model: string | null) => Promise<Thread>;
  threads: Thread[];
  setThreads: Dispatch<SetStateAction<Thread[]>>;
  threadsLoading: boolean;
  setThreadsLoading: Dispatch<SetStateAction<boolean>>;
}

const ThreadContext = createContext<ThreadContextType | undefined>(undefined);

function adaptThread(summary: WebThreadSummary): Thread {
  return {
    thread_id: summary.thread_id,
    created_at: summary.created_at ?? undefined,
    updated_at: summary.updated_at ?? undefined,
    state_updated_at: summary.updated_at ?? undefined,
    interrupts: {},
    metadata: {
      title: summary.title ?? undefined,
      cwd: summary.cwd ?? undefined,
      active_status: summary.active_status,
      assistant_id: summary.assistant_id,
      epimindagent_model_spec: summary.model_spec ?? undefined,
    },
    values: summary.initial_prompt
      ? {
          messages: [
            {
              id: `${summary.thread_id}-initial`,
              type: "human",
              content: summary.initial_prompt,
            },
          ],
        }
      : {},
    status: summary.active_status,
  } as unknown as Thread;
}

export function ThreadProvider({ children }: { children: ReactNode }) {
  const envApiUrl: string | undefined =
    process.env.NEXT_PUBLIC_API_URL ?? "/langgraph";
  const envAssistantId: string | undefined =
    process.env.NEXT_PUBLIC_ASSISTANT_ID ?? "agent";
  const envAuthScheme: string | undefined = process.env.NEXT_PUBLIC_AUTH_SCHEME;

  const [apiUrl] = useQueryState("apiUrl", {
    defaultValue: envApiUrl || "",
  });
  const [assistantId] = useQueryState("assistantId", {
    defaultValue: envAssistantId || "",
  });
  const [authScheme] = useQueryState("authScheme", {
    defaultValue: envAuthScheme || "",
  });
  const [threads, setThreads] = useState<Thread[]>([]);
  const [threadsLoading, setThreadsLoading] = useState(false);

  const getThreads = useCallback(async (
    page = 1,
    pageSize = 20,
  ): Promise<ThreadPageResult> => {
    const query = new URLSearchParams({
      page: String(page),
      page_size: String(pageSize),
    });
    const response = await fetch(`/api/threads?${query.toString()}`);
    if (!response.ok) {
      throw new Error("Failed to load threads.");
    }
    const payload = (await response.json()) as {
      threads?: WebThreadSummary[];
      total?: number;
      page?: number;
      page_size?: number;
    };
    const pageThreads = (payload.threads ?? []).map(adaptThread);
    setThreads((current) => {
      const merged = [...current];
      for (const thread of pageThreads) {
        const existingIndex = merged.findIndex(
          (item) => item.thread_id === thread.thread_id,
        );
        if (existingIndex === -1) {
          merged.push(thread);
        } else {
          merged[existingIndex] = thread;
        }
      }
      return merged;
    });
    return {
      threads: pageThreads,
      total: payload.total ?? pageThreads.length,
      page: payload.page ?? page,
      pageSize: payload.page_size ?? pageSize,
    };
  }, []);

  const createThread = useCallback(async (): Promise<Thread> => {
    const resolvedAssistantId = assistantId || envAssistantId || "agent";
    const webThreadResponse = await fetch("/api/threads", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ assistant_id: resolvedAssistantId }),
    });
    if (!webThreadResponse.ok) {
      throw new Error("Failed to create thread.");
    }
    const payload = (await webThreadResponse.json()) as { thread: WebThreadSummary };
    const client = createClient(
      apiUrl || envApiUrl || "/langgraph",
      getApiKey() ?? undefined,
      authScheme || undefined,
    );
    await client.threads.create({
      threadId: payload.thread.thread_id,
      ifExists: "do_nothing",
      metadata: {
        assistant_id: resolvedAssistantId,
        cwd: payload.thread.cwd ?? undefined,
            title: payload.thread.title ?? undefined,
            model_spec: payload.thread.model_spec ?? undefined,
      },
    });
    const thread = adaptThread(payload.thread);
    setThreads((current) => [thread, ...current.filter((item) => item.thread_id !== thread.thread_id)]);
    return thread;
  }, [apiUrl, assistantId, authScheme, envApiUrl, envAssistantId]);

  const renameThread = useCallback(
    async (thread: Thread, title: string): Promise<Thread> => {
      const resolvedAssistantId = assistantId || envAssistantId;
      if (!apiUrl || !resolvedAssistantId) {
        throw new Error("Thread client is not configured.");
      }

      const client = createClient(
        apiUrl,
        getApiKey() ?? undefined,
        authScheme || undefined,
      );
      const metadata = buildRenamedThreadMetadata(thread.metadata, title);
      const updatedThread = {
        ...thread,
        metadata,
      } as Thread;
      setThreads((current) =>
        current.map((item) =>
          item.thread_id === updatedThread.thread_id ? updatedThread : item,
        ),
      );
      await fetch(`/api/threads/${thread.thread_id}`, {
        method: "PATCH",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ title: metadata.title ?? null }),
      }).catch(console.error);
      await client.threads.update(thread.thread_id, { metadata }).catch(console.error);
      return updatedThread;
    },
    [apiUrl, assistantId, authScheme, envAssistantId, setThreads],
  );

  const deleteThread = useCallback(
    async (thread: Thread): Promise<void> => {
      const resolvedAssistantId = assistantId || envAssistantId;
      if (!apiUrl || !resolvedAssistantId) {
        throw new Error("Thread client is not configured.");
      }

      await fetch(`/api/threads/${thread.thread_id}`, { method: "DELETE" });
      setThreads((current) =>
        current.filter((item) => item.thread_id !== thread.thread_id),
      );
    },
    [apiUrl, assistantId, envAssistantId, setThreads],
  );

  const setThreadModel = useCallback(
    async (thread: Thread, model: string | null): Promise<Thread> => {
      const resolvedAssistantId = assistantId || envAssistantId;
      if (!apiUrl || !resolvedAssistantId) {
        throw new Error("Thread client is not configured.");
      }
      const client = createClient(
        apiUrl,
        getApiKey() ?? undefined,
        authScheme || undefined,
      );
      const metadata = buildThreadMetadataWithModel(
        thread.metadata as Record<string, unknown> | null | undefined,
        model,
      );
      const updatedThread = {
        ...thread,
        metadata,
      } as Thread;
      setThreads((current) =>
        current.map((item) =>
          item.thread_id === updatedThread.thread_id ? updatedThread : item,
        ),
      );
      await fetch(`/api/threads/${thread.thread_id}`, {
        method: "PATCH",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ model_spec: model }),
      }).catch(console.error);
      await client.threads.update(thread.thread_id, { metadata }).catch(console.error);
      return updatedThread;
    },
    [apiUrl, assistantId, authScheme, envAssistantId, setThreads],
  );

  const value = {
    getThreads,
    createThread,
    renameThread,
    deleteThread,
    setThreadModel,
    threads,
    setThreads,
    threadsLoading,
    setThreadsLoading,
  };

  return (
    <ThreadContext.Provider value={value}>{children}</ThreadContext.Provider>
  );
}

export function useThreads() {
  const context = useContext(ThreadContext);
  if (context === undefined) {
    throw new Error("useThreads must be used within a ThreadProvider");
  }
  return context;
}
