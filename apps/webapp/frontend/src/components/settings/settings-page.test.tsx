import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { SettingsPageContent } from "./settings-page";

function jsonResponse(payload: unknown) {
  return new Response(JSON.stringify(payload), {
    status: 200,
    headers: { "content-type": "application/json" },
  });
}

describe("SettingsPageContent", () => {
  const fetchMock = vi.fn();

  beforeEach(() => {
    fetchMock.mockReset();
    global.fetch = fetchMock as typeof fetch;
  });

  it("loads model settings, adds a provider, and saves the edited payload", async () => {
    fetchMock.mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url === "/api/settings/models" && !init) {
        return Promise.resolve(
          jsonResponse({
            default_model: null,
            providers: [],
            templates: [
              {
                key: "openai",
                provider_key: "openai",
                label: "OpenAI",
                provider_kind: "native",
                base_url: null,
                api_key_env: "EPIMINDAGENT_CLI_OPENAI_API_KEY",
              },
            ],
          }),
        );
      }
      if (url === "/api/settings/appearance" && !init) {
        return Promise.resolve(
          jsonResponse({
            theme_modes: ["light", "dark", "system"],
            storage: "browser",
            default_theme: "system",
          }),
        );
      }
      if (url === "/api/settings/models" && init?.method === "PUT") {
        return Promise.resolve(jsonResponse(JSON.parse(String(init.body))));
      }
      throw new Error(`Unhandled fetch: ${url}`);
    });

    const user = userEvent.setup();
    render(<SettingsPageContent backHref="/?threadId=web-1" />);

    await screen.findByRole("heading", { name: "模型配置" });
    await user.click(screen.getByRole("button", { name: "添加 OpenAI" }));

    await user.clear(screen.getByLabelText("API Key"));
    await user.type(screen.getByLabelText("API Key"), "sk-openai");
    await user.clear(screen.getByLabelText("模型列表"));
    await user.type(screen.getByLabelText("模型列表"), "gpt-5.4");
    await user.selectOptions(screen.getByLabelText("全局默认模型"), "openai:gpt-5.4");
    await user.click(screen.getByRole("button", { name: "保存更改" }));

    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/settings/models",
        expect.objectContaining({
          method: "PUT",
        }),
      ),
    );

    const saveCall = fetchMock.mock.calls.find(
      ([input, init]) =>
        String(input) === "/api/settings/models" && init?.method === "PUT",
    );
    expect(saveCall).toBeDefined();
    expect(JSON.parse(String(saveCall?.[1]?.body))).toEqual({
      default_model: "openai:gpt-5.4",
      providers: [
        {
          key: "openai",
          label: "OpenAI",
          enabled: true,
          provider_kind: "native",
          base_url: null,
          api_key_env: "EPIMINDAGENT_CLI_OPENAI_API_KEY",
          api_key: "sk-openai",
          models: ["gpt-5.4"],
          test_model: "gpt-5.4",
          template_key: "openai",
        },
      ],
    });
  });
});
