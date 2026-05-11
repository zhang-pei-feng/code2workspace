import { describe, expect, it } from "vitest";

import {
  buildRenamedThreadMetadata,
  getThreadDisplayTitle,
} from "./thread-title";

describe("getThreadDisplayTitle", () => {
  it("prefers metadata.title over the first message text", () => {
    const thread = {
      thread_id: "thread-1",
      metadata: { title: "Custom title" },
      values: {
        messages: [{ content: [{ type: "text", text: "First prompt" }] }],
      },
    };

    expect(getThreadDisplayTitle(thread as never)).toBe("Custom title");
  });

  it("falls back to the first message text and then thread id", () => {
    expect(
      getThreadDisplayTitle({
        thread_id: "thread-1",
        metadata: {},
        values: {
          messages: [{ content: [{ type: "text", text: "First prompt" }] }],
        },
      } as never),
    ).toBe("First prompt");

    expect(
      getThreadDisplayTitle({
        thread_id: "thread-2",
        metadata: {},
        values: {},
      } as never),
    ).toBe("thread-2");
  });
});

describe("buildRenamedThreadMetadata", () => {
  it("preserves existing metadata and writes a trimmed title", () => {
    expect(
      buildRenamedThreadMetadata(
        {
          assistant_id: "agent",
          graph_id: "agent",
        },
        "  Renamed thread  ",
      ),
    ).toEqual({
      assistant_id: "agent",
      graph_id: "agent",
      title: "Renamed thread",
    });
  });
});
