import { describe, expect, it } from "vitest";

import {
  extractMessagesFromUpdateEvent,
  mergeMessagesById,
} from "./stream-state";

describe("extractMessagesFromUpdateEvent", () => {
  it("extracts direct messages arrays from update nodes", () => {
    expect(
      extractMessagesFromUpdateEvent({
        model: {
          messages: [{ id: "ai-1", type: "ai", content: "hello" }],
        },
      }),
    ).toEqual([{ id: "ai-1", type: "ai", content: "hello" }]);
  });

  it("extracts LangGraph channel update values from messages.value", () => {
    expect(
      extractMessagesFromUpdateEvent({
        tools: {
          messages: {
            value: [
              {
                id: "tool-1",
                type: "tool",
                name: "fetch_url",
                tool_call_id: "call-1",
                content: "{\"status_code\": 200}",
              },
            ],
          },
        },
      }),
    ).toEqual([
      {
        id: "tool-1",
        type: "tool",
        name: "fetch_url",
        tool_call_id: "call-1",
        content: "{\"status_code\": 200}",
      },
    ]);
  });
});

describe("mergeMessagesById", () => {
  it("replaces messages with the same id and appends new messages", () => {
    expect(
      mergeMessagesById(
        [
          { id: "human-1", type: "human", content: "hi" },
          { id: "ai-1", type: "ai", content: "" },
        ] as never,
        [
          { id: "ai-1", type: "ai", content: "thinking", tool_calls: [] },
          { id: "tool-1", type: "tool", content: "done", tool_call_id: "call-1" },
        ] as never,
      ),
    ).toEqual([
      { id: "human-1", type: "human", content: "hi" },
      { id: "ai-1", type: "ai", content: "thinking", tool_calls: [] },
      { id: "tool-1", type: "tool", content: "done", tool_call_id: "call-1" },
    ]);
  });

  it("preserves existing tool calls when later chunks with the same id omit them", () => {
    expect(
      mergeMessagesById(
        [
          {
            id: "ai-1",
            type: "ai",
            content: "",
            tool_calls: [{ id: "call-1", name: "read_file", args: { path: "SKILL.md" } }],
          },
        ] as never,
        [
          {
            id: "ai-1",
            type: "ai",
            content: "done",
          },
        ] as never,
      ),
    ).toEqual([
      {
        id: "ai-1",
        type: "ai",
        content: "done",
        tool_calls: [{ id: "call-1", name: "read_file", args: { path: "SKILL.md" } }],
      },
    ]);
  });
});
