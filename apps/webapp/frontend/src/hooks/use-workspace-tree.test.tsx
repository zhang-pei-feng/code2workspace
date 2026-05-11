import { act, renderHook, waitFor } from "@testing-library/react";
import { describe, expect, test, vi } from "vitest";

const fetchWorkspaceTreeMock = vi.fn();

vi.mock("@/lib/workspace", () => ({
  fetchWorkspaceTree: (...args: unknown[]) => fetchWorkspaceTreeMock(...args),
  uploadWorkspaceFiles: vi.fn(),
  getUploadTargetPath: vi.fn(() => ""),
}));

import { useWorkspaceTree } from "./use-workspace-tree";

describe("useWorkspaceTree", () => {
  test("loads the root directory once per thread instead of reloading forever", async () => {
    fetchWorkspaceTreeMock.mockResolvedValue({
      cwd: "/tmp/workspace/20260427",
      path: "",
      entries: [{ name: "src", path: "src", type: "directory", size: null }],
    });

    const { result } = renderHook(() => useWorkspaceTree("thread-1"));

    await waitFor(() => {
      expect(result.current.cwd).toBe("/tmp/workspace/20260427");
    });

    await act(async () => {
      await Promise.resolve();
    });

    expect(fetchWorkspaceTreeMock).toHaveBeenCalledTimes(1);
    expect(result.current.loadingPaths).toEqual([]);
    expect(result.current.entriesByPath[""]).toHaveLength(1);
  });
});
