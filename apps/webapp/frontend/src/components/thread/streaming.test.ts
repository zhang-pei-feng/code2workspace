import { describe, expect, it } from "vitest";

import {
  buildThreadStreamSubmitOptions,
  isAssistantActivityMessage,
} from "./streaming";

describe("buildThreadStreamSubmitOptions", () => {
  it("uses streaming-compatible modes for chat submissions", () => {
    expect(
      buildThreadStreamSubmitOptions({
        checkpoint: "cp-1",
      }),
    ).toMatchObject({
      checkpoint: "cp-1",
      streamMode: ["messages", "updates", "values"],
      streamSubgraphs: true,
      streamResumable: true,
    });
  });
});

describe("isAssistantActivityMessage", () => {
  it("treats ai and tool messages as visible response activity", () => {
    expect(isAssistantActivityMessage({ type: "ai" } as never)).toBe(true);
    expect(isAssistantActivityMessage({ type: "tool" } as never)).toBe(true);
    expect(isAssistantActivityMessage({ type: "human" } as never)).toBe(false);
  });
});
