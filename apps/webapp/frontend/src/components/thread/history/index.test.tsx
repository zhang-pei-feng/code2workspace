import React from "react";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, test, vi } from "vitest";

const getThreadsMock = vi.fn();

vi.mock("nuqs", () => ({
  useQueryState: (_key: string, options?: { defaultValue?: boolean | string }) => [
    options?.defaultValue ?? null,
    vi.fn(),
  ],
  parseAsBoolean: {
    withDefault: (value: boolean) => ({ defaultValue: value }),
  },
}));

vi.mock("@/hooks/useMediaQuery", () => ({
  useMediaQuery: () => true,
}));

vi.mock("@/providers/Thread", () => ({
  useThreads: () => ({
    getThreads: getThreadsMock,
    renameThread: vi.fn(),
    deleteThread: vi.fn(),
    threads: [],
    setThreads: vi.fn(),
    threadsLoading: false,
    setThreadsLoading: vi.fn(),
  }),
}));

import ThreadHistory from ".";

describe("ThreadHistory pagination", () => {
  test("loads the first page by default and requests the next page", async () => {
    getThreadsMock.mockImplementation(async (page = 1) => ({
      threads:
        page === 1
          ? [
              {
                thread_id: "thread-1",
                metadata: { title: "Thread 1" },
                values: {},
              },
            ]
          : [
              {
                thread_id: "thread-21",
                metadata: { title: "Thread 21" },
                values: {},
              },
            ],
      total: 25,
      page,
      pageSize: 20,
    }));

    const { unmount } = render(<ThreadHistory />);

    await waitFor(() => {
      expect(getThreadsMock).toHaveBeenCalledWith(1, 20);
    });
    expect(await screen.findByText("Thread 1")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "下一页" }));

    await waitFor(() => {
      expect(getThreadsMock).toHaveBeenCalledWith(2, 20);
    });
    expect(await screen.findByText("Thread 21")).toBeInTheDocument();

    unmount();
    await act(async () => {
      await Promise.resolve();
    });
  });
});
