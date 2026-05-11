import { describe, expect, it } from "vitest";

import {
  buildPlaywrightExecutableCandidates,
  resolvePlaywrightExecutablePath,
} from "./playwright-browser";

describe("buildPlaywrightExecutableCandidates", () => {
  it("prefers the cached full chromium binary before headless shell fallbacks", () => {
    expect(
      buildPlaywrightExecutableCandidates("/home/tester"),
    ).toEqual([
      "/home/tester/.cache/ms-playwright/chromium-1208/chrome-linux64/chrome",
      "/home/tester/.cache/ms-playwright/chromium_headless_shell-1208/chrome-headless-shell-linux64/chrome-headless-shell",
      "/home/tester/.cache/ms-playwright/chromium-1181/chrome-linux/chrome",
    ]);
  });
});

describe("resolvePlaywrightExecutablePath", () => {
  it("uses PLAYWRIGHT_EXECUTABLE_PATH when it exists", () => {
    const result = resolvePlaywrightExecutablePath({
      env: {
        PLAYWRIGHT_EXECUTABLE_PATH: "/custom/chrome",
      },
      homeDir: "/home/tester",
      pathExists: (candidate) => candidate === "/custom/chrome",
    });

    expect(result).toBe("/custom/chrome");
  });

  it("falls back to the first cached chromium candidate that exists", () => {
    const result = resolvePlaywrightExecutablePath({
      env: {},
      homeDir: "/home/tester",
      pathExists: (candidate) =>
        candidate ===
        "/home/tester/.cache/ms-playwright/chromium-1208/chrome-linux64/chrome",
    });

    expect(result).toBe(
      "/home/tester/.cache/ms-playwright/chromium-1208/chrome-linux64/chrome",
    );
  });

  it("throws a clear error when no configured or cached browser exists", () => {
    expect(() =>
      resolvePlaywrightExecutablePath({
        env: {},
        homeDir: "/home/tester",
        pathExists: () => false,
      }),
    ).toThrowError(/PLAYWRIGHT_EXECUTABLE_PATH/);
  });
});
