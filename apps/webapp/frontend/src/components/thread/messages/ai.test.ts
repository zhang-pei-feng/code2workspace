import React from "react";
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

const streamContext = {
  values: { ui: [] },
  messages: [{ id: "human-1", type: "human", content: "hello" }],
  getMessagesMetadata: () => undefined,
  interrupt: { when: "breakpoint" },
};

vi.mock("@/providers/Stream", () => ({
  useStreamContext: () => streamContext,
}));

vi.mock("../utils", () => ({
  getContentString: () => "",
}));

vi.mock("./shared", () => ({
  BranchSwitcher: () => null,
  CommandBar: () => null,
}));

vi.mock("../markdown-text", () => ({
  MarkdownText: ({ children }: { children: React.ReactNode }) =>
    React.createElement(React.Fragment, null, children),
}));

vi.mock("@langchain/langgraph-sdk/react-ui", () => ({
  LoadExternalComponent: () => null,
}));

vi.mock("./tool-calls", () => ({
  ToolCalls: () => null,
  ToolResult: () => null,
}));

vi.mock("@/lib/agent-inbox-interrupt", () => ({
  isAgentInboxInterruptSchema: () => false,
}));

vi.mock("../agent-inbox", () => ({
  ThreadView: () => null,
}));

vi.mock("nuqs", () => ({
  useQueryState: () => [false, vi.fn()],
  parseAsBoolean: {
    withDefault: () => ({}),
  },
}));

vi.mock("./generic-interrupt", () => ({
  GenericInterruptView: () => React.createElement("div", null, "Human Interrupt"),
}));

vi.mock("../artifact", () => ({
  useArtifact: () => ({}),
}));

import { AssistantMessage, isBreakpointInterrupt } from "./ai";

describe("isBreakpointInterrupt", () => {
  it("detects single breakpoint interrupts", () => {
    expect(isBreakpointInterrupt({ when: "breakpoint" })).toBe(true);
    expect(isBreakpointInterrupt({ when: "during" })).toBe(false);
  });

  it("detects arrays containing only breakpoint interrupts", () => {
    expect(
      isBreakpointInterrupt([
        { when: "breakpoint" },
        { when: "breakpoint" },
      ]),
    ).toBe(true);
    expect(
      isBreakpointInterrupt([
        { when: "breakpoint" },
        { when: "during" },
      ]),
    ).toBe(false);
  });

  it("does not render the generic interrupt card for breakpoint-only interrupts", () => {
    render(
      React.createElement(AssistantMessage, {
        message: undefined,
        isLoading: true,
        handleRegenerate: () => {},
      }),
    );

    expect(screen.queryByText("Human Interrupt")).not.toBeInTheDocument();
  });
});
