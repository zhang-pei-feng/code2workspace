import React from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ToolResult } from "./tool-calls";

describe("ToolResult", () => {
  it("collapses long string fields to a short preview and expands on demand", async () => {
    const message = {
      type: "tool",
      name: "fetch_url",
      tool_call_id: "call_1",
      content: JSON.stringify({
        markdown_content:
          "Line one preview\nLine two hidden by default\nLine three also hidden",
        status_code: 200,
      }),
    };

    render(<ToolResult message={message as never} />);

    expect(screen.getByText(/Line one preview/)).toBeInTheDocument();
    expect(screen.getByText(/Line two hidden by default/)).toBeInTheDocument();
    expect(
      screen.queryByText(/Line three also hidden/),
    ).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button"));

    await waitFor(() => {
      expect(screen.getByText(/Line three also hidden/)).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("button"));

    await waitFor(() => {
      expect(
        screen.queryByText(/Line three also hidden/),
      ).not.toBeInTheDocument();
    });
  });
});
