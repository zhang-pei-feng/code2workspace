import { render } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { ThreadHeaderActions } from "./header-actions";

describe("ThreadHeaderActions", () => {
  it("renders the settings action before new conversation", () => {
    const onNewThread = vi.fn();
    const { container } = render(
      <ThreadHeaderActions
        settingsHref="/settings?threadId=web-1"
        onNewThread={onNewThread}
      />,
    );

    const actions = Array.from(
      container.querySelectorAll("[data-header-action]"),
    ).map((node) => node.textContent?.replace(/\s+/g, " ").trim());

    expect(actions).toEqual(["设置", "新建对话"]);
    expect(container.querySelector('a[href="/settings?threadId=web-1"]')).not.toBeNull();
  });
});
