import React from "react";
import { act, renderHook } from "@testing-library/react";
import { afterEach, describe, expect, test, vi } from "vitest";

const createClientSpy = vi.fn();
const threadsCreateSpy = vi.fn();
const threadsUpdateSpy = vi.fn();

vi.mock("nuqs", () => ({
  useQueryState: (_key: string, options?: { defaultValue?: string }) => [
    options?.defaultValue ?? "",
    vi.fn(),
  ],
}));

vi.mock("@/lib/api-key", () => ({
  getApiKey: () => null,
}));

vi.mock("./client", () => ({
  createClient: (...args: unknown[]) => {
    createClientSpy(...args);
    return {
      threads: {
        create: threadsCreateSpy,
        update: threadsUpdateSpy,
        delete: vi.fn(),
      },
    };
  },
}));

import { ThreadProvider, useThreads } from "./Thread";

describe("ThreadProvider", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    createClientSpy.mockReset();
    threadsCreateSpy.mockReset();
    threadsUpdateSpy.mockReset();
  });

  test("creates matching LangGraph and web threads for new conversations", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({
          thread: {
            thread_id: "thread-1",
            assistant_id: "agent",
            cwd: "/tmp/workspace/1",
            active_status: "idle",
            created_at: "2026-04-27T00:00:00+00:00",
            updated_at: "2026-04-27T00:00:00+00:00",
            message_count: 0,
            initial_prompt: null,
            title: null,
          },
        }),
      }),
    );
    threadsCreateSpy.mockResolvedValue({ thread_id: "thread-1" });

    const wrapper = ({ children }: { children: React.ReactNode }) => (
      <ThreadProvider>{children}</ThreadProvider>
    );

    const { result } = renderHook(() => useThreads(), { wrapper });

    await act(async () => {
      await result.current.createThread();
    });

    expect(createClientSpy).toHaveBeenCalled();
    expect(threadsCreateSpy).toHaveBeenCalledWith(
      expect.objectContaining({
        threadId: "thread-1",
        ifExists: "do_nothing",
      }),
    );

    vi.unstubAllGlobals();
  });

  test("restores persisted model spec from the web thread list", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({
          threads: [
            {
              thread_id: "thread-1",
              assistant_id: "agent",
              cwd: "/tmp/workspace/1",
              active_status: "idle",
              created_at: "2026-04-27T00:00:00+00:00",
              updated_at: "2026-04-27T00:00:00+00:00",
              message_count: 0,
              initial_prompt: null,
              title: null,
              model_spec: "anthropic:claude-sonnet-4-6",
            },
          ],
          total: 1,
          page: 1,
          page_size: 20,
        }),
      }),
    );

    const wrapper = ({ children }: { children: React.ReactNode }) => (
      <ThreadProvider>{children}</ThreadProvider>
    );
    const { result } = renderHook(() => useThreads(), { wrapper });

    let payload;
    await act(async () => {
      payload = await result.current.getThreads();
    });

    expect(payload?.threads[0].metadata).toEqual(
      expect.objectContaining({
        epimindagent_model_spec: "anthropic:claude-sonnet-4-6",
      }),
    );

    vi.unstubAllGlobals();
  });
});
