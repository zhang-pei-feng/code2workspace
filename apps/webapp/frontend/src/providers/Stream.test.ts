import { describe, expect, it } from "vitest";
import { withThreadModelContext } from "./Stream";

describe("withThreadModelContext", () => {
  it("adds model when no context is present", () => {
    expect(withThreadModelContext(undefined, "openai:gpt-4.1")).toEqual({
      context: { model: "openai:gpt-4.1" },
    });
  });

  it("preserves existing model in context", () => {
    expect(
      withThreadModelContext(
        { context: { model: "anthropic:claude-sonnet-4-5", foo: 1 } },
        "openai:gpt-4.1",
      ),
    ).toEqual({
      context: { model: "anthropic:claude-sonnet-4-5", foo: 1 },
    });
  });

  it("merges model into existing context without model", () => {
    expect(
      withThreadModelContext({ context: { artifact_id: "a1" } }, "openai:gpt-4.1"),
    ).toEqual({
      context: { artifact_id: "a1", model: "openai:gpt-4.1" },
    });
  });
});

