import { afterEach, describe, expect, test, vi } from "vitest";

import {
  buildWorkspaceAbsolutePath,
  buildWorkspaceDownloadName,
  getWorkspacePreviewKind,
  getUploadTargetPath,
  isPreviewableWorkspaceEntry,
  parseDownloadFilename,
} from "./workspace";

describe("workspace helpers", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  test("uses selected directory as upload target", () => {
    expect(
      getUploadTargetPath({
        path: "inputs",
        type: "directory",
      }),
    ).toBe("inputs");
  });

  test("uses selected file parent directory as upload target", () => {
    expect(
      getUploadTargetPath({
        path: "inputs/sample.fastq",
        type: "file",
      }),
    ).toBe("inputs");
  });

  test("falls back to workspace root when nothing is selected", () => {
    expect(getUploadTargetPath(null)).toBe("");
  });

  test("builds absolute workspace path for copy path", () => {
    expect(
      buildWorkspaceAbsolutePath("/tmp/workspace/1", {
        path: "inputs/a.txt",
        type: "file",
      }),
    ).toBe("/tmp/workspace/1/inputs/a.txt");
  });

  test("extracts filename from content disposition", () => {
    expect(parseDownloadFilename('attachment; filename="bundle.zip"')).toBe(
      "bundle.zip",
    );
  });

  test("builds directory zip name from workspace path", () => {
    expect(buildWorkspaceDownloadName("inputs", "thread-1")).toBe("inputs.zip");
  });

  test("marks common small text files as previewable", () => {
    expect(
      isPreviewableWorkspaceEntry({
        name: "notes.txt",
        path: "notes.txt",
        type: "file",
        size: 128,
      }),
    ).toBe(true);
  });

  test("supports image, pdf, and docx previews for reasonable files", () => {
    expect(
      getWorkspacePreviewKind({
        name: "figure.png",
        path: "figure.png",
        type: "file",
        size: 2048,
      }),
    ).toBe("image");
    expect(
      getWorkspacePreviewKind({
        name: "paper.pdf",
        path: "paper.pdf",
        type: "file",
        size: 4096,
      }),
    ).toBe("pdf");
    expect(
      getWorkspacePreviewKind({
        name: "report.docx",
        path: "report.docx",
        type: "file",
        size: 4096,
      }),
    ).toBe("docx");
  });

  test("rejects large or uncommon files for preview", () => {
    expect(
      isPreviewableWorkspaceEntry({
        name: "reads.bam",
        path: "reads.bam",
        type: "file",
        size: 1024,
      }),
    ).toBe(false);
    expect(
      isPreviewableWorkspaceEntry({
        name: "huge.log",
        path: "huge.log",
        type: "file",
        size: 200_000,
      }),
    ).toBe(false);
  });
});
