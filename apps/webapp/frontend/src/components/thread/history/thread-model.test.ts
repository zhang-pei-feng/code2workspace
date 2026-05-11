import { describe, expect, it } from "vitest";
import { buildThreadMetadataWithModel, getThreadModelSpec } from "./thread-model";

describe("thread model metadata helpers", () => {
  it("reads per-thread model spec from metadata", () => {
    const model = getThreadModelSpec({
      metadata: { code2workspace_model_spec: "openai:gpt-4.1" },
    } as never);
    expect(model).toBe("openai:gpt-4.1");
  });

  it("writes model spec into metadata", () => {
    const next = buildThreadMetadataWithModel(
      { title: "demo" },
      "anthropic:claude-sonnet-4-5",
    );
    expect(next).toEqual({
      title: "demo",
      code2workspace_model_spec: "anthropic:claude-sonnet-4-5",
    });
  });

  it("removes model spec when cleared", () => {
    const next = buildThreadMetadataWithModel(
      { code2workspace_model_spec: "openai:gpt-4.1", title: "demo" },
      null,
    );
    expect(next).toEqual({ title: "demo" });
  });
});

