import { expect, test, type Page } from "@playwright/test";

async function sendMessage(page: Page, message: string) {
  const input = page.getByPlaceholder("Type your message...");
  await input.fill(message);
  await page.getByRole("button", { name: "Send" }).click();
}

async function waitForThreadIdle(page: Page) {
  await expect(page.getByRole("button", { name: "Cancel" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Send" })).toBeVisible();
}

test("streams a simple response and restores the thread after refresh", async ({
  page,
}) => {
  await page.goto("/");

  await sendMessage(page, "Reply with OK only.");

  await expect(page).toHaveURL(/threadId=/);
  await expect(page.getByText(/^OK$/)).toBeVisible();
  await waitForThreadIdle(page);

  await page.reload();

  await waitForThreadIdle(page);
  await expect(page.getByText(/^OK$/)).toBeVisible();
});

test("shows tool activity and final answer without a manual refresh", async ({
  page,
}) => {
  await page.goto("/");

  await sendMessage(
    page,
    "Use the fetch_url tool to fetch https://example.com and reply with the page title only.",
  );

  await expect(page.getByText(/Tool Result/i)).toBeVisible();
  await expect(page.getByText(/Example Domain/i).first()).toBeVisible();
  await waitForThreadIdle(page);
});

test("renames a thread title from the left history panel", async ({ page }) => {
  await page.goto("/");

  await sendMessage(page, "Rename me please.");
  await expect(page).toHaveURL(/threadId=/);
  await waitForThreadIdle(page);
  const currentThreadId = new URL(page.url()).searchParams.get("threadId");
  expect(currentThreadId).toBeTruthy();

  const threadRow = page
    .getByRole("button", { name: currentThreadId!, exact: true })
    .first()
    .locator("xpath=..");
  const menuButton = threadRow.getByRole("button", {
    name: `会话操作 ${currentThreadId}`,
  });
  await menuButton.scrollIntoViewIfNeeded();
  await menuButton.evaluate((element: HTMLButtonElement) => element.click());
  await page
    .getByRole("button", { name: "重命名" })
    .evaluate((element: HTMLButtonElement) => element.click());

  const titleInput = page.locator('input[data-slot="input"]').first();
  await titleInput.fill("Renamed thread");
  await page
    .getByRole("button", { name: "Save thread title" })
    .evaluate((element: HTMLButtonElement) => element.click());

  await expect(
    page.getByRole("button", { name: "Renamed thread", exact: true }).first(),
  ).toBeVisible();
});

test("sends the selected draft model with the first message of a new thread", async ({
  page,
}) => {
  await page.goto("/");

  await page.getByRole("button", { name: /gpt-5.4/i }).click();
  await page.getByRole("button", { name: /claude-sonnet-4-6/i }).click();

  const requestPromise = page.waitForRequest((request) =>
    request.url().includes("/runs/stream"),
  );

  await sendMessage(page, "Reply with OK only.");

  const request = await requestPromise;
  const payload = request.postDataJSON();

  expect(payload.context.model).toBe("anthropic:claude-sonnet-4-6");
});

test("opens settings, adds a provider, and submits shared model settings", async ({
  page,
}) => {
  let savedPayload: unknown = null;

  await page.route("**/api/settings/models", async (route) => {
    const request = route.request();
    if (request.method() === "GET") {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
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
      });
      return;
    }

    savedPayload = request.postDataJSON();
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        default_model: "openai:gpt-5.4",
        providers: [
          {
            key: "openai",
            label: "OpenAI",
            enabled: true,
            provider_kind: "native",
            base_url: null,
            api_key_env: "EPIMINDAGENT_CLI_OPENAI_API_KEY",
            has_api_key: true,
            models: ["gpt-5.4"],
            test_model: "gpt-5.4",
            template_key: "openai",
          },
        ],
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
    });
  });

  await page.route("**/api/settings/appearance", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        theme_modes: ["light", "dark", "system"],
        storage: "browser",
        default_theme: "system",
      }),
    });
  });

  await page.goto("/settings?threadId=web-1");

  await page.getByRole("button", { name: "添加 OpenAI" }).click();
  await page.getByLabel("API Key", { exact: true }).fill("sk-openai");
  await page.getByLabel("模型列表").fill("gpt-5.4");
  await page.getByLabel("全局默认模型").selectOption("openai:gpt-5.4");
  await page.getByRole("button", { name: "保存更改" }).click();

  await expect
    .poll(() => savedPayload, {
      message: "wait for settings save request",
    })
    .toEqual({
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
