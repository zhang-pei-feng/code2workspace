import React from "react";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, test, vi } from "vitest";

const refreshSpy = vi.fn();

vi.mock("@/hooks/use-workspace-tree", () => ({
  useWorkspaceTree: () => ({
    cwd: "/tmp/workspace/20260427",
    entriesByPath: {
      "": [
        { name: "inputs", path: "inputs", type: "directory", size: null },
        { name: "notes.txt", path: "notes.txt", type: "file", size: 12 },
        { name: "figure.png", path: "figure.png", type: "file", size: 1024 },
        { name: "paper.pdf", path: "paper.pdf", type: "file", size: 2048 },
        { name: "report.docx", path: "report.docx", type: "file", size: 4096 },
      ],
    },
    expandedPaths: [],
    selectedEntry: null,
    loadingPaths: [],
    error: null,
    uploading: false,
    refresh: refreshSpy,
    toggleDirectory: vi.fn(),
    selectEntry: vi.fn(),
    uploadFiles: vi.fn(),
  }),
}));

import { WorkspacePanel } from "./workspace-panel";

describe("WorkspacePanel", () => {
  test("renders the workspace tree and triggers refresh", () => {
    render(<WorkspacePanel threadId="thread-1" />);

    expect(screen.getByText("20260427")).toBeInTheDocument();
    expect(screen.getByText("inputs")).toBeInTheDocument();
    expect(screen.getByText("notes.txt")).toBeInTheDocument();
    expect(screen.queryByLabelText("Workspace actions")).not.toBeInTheDocument();
    expect(
      screen.getByLabelText("Workspace actions for workspace"),
    ).toBeInTheDocument();
    expect(
      screen.getByLabelText("Workspace actions for inputs"),
    ).toBeInTheDocument();
    expect(
      screen.getByLabelText("Workspace actions for notes.txt"),
    ).toBeInTheDocument();

    fireEvent.click(screen.getByLabelText("Refresh workspace tree"));
    expect(refreshSpy).toHaveBeenCalled();
  });

  test("shows delete action in item menu", () => {
    render(<WorkspacePanel threadId="thread-1" />);

    fireEvent.click(screen.getAllByLabelText("Workspace actions for notes.txt")[0]);

    expect(screen.getByText("删除")).toBeInTheDocument();
  });

  test("shows empty state when there is no active thread", () => {
    render(<WorkspacePanel threadId={null} />);

    expect(
      screen.getByText("先创建或选择一个对话，右侧才会显示该对话的工作目录。"),
    ).toBeInTheDocument();
  });
});
