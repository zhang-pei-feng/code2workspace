import { existsSync } from "node:fs";
import os from "node:os";
import path from "node:path";

const PLAYWRIGHT_EXECUTABLE_ENV = "PLAYWRIGHT_EXECUTABLE_PATH";

type ResolverOptions = {
  env?: Record<string, string | undefined>;
  homeDir?: string;
  pathExists?: (candidate: string) => boolean;
};

export function buildPlaywrightExecutableCandidates(homeDir: string): string[] {
  return [
    path.join(
      homeDir,
      ".cache/ms-playwright/chromium-1208/chrome-linux64/chrome",
    ),
    path.join(
      homeDir,
      ".cache/ms-playwright/chromium_headless_shell-1208/chrome-headless-shell-linux64/chrome-headless-shell",
    ),
    path.join(
      homeDir,
      ".cache/ms-playwright/chromium-1181/chrome-linux/chrome",
    ),
  ];
}

export function resolvePlaywrightExecutablePath(
  options: ResolverOptions = {},
): string {
  const env = options.env ?? process.env;
  const homeDir = options.homeDir ?? os.homedir();
  const pathExists = options.pathExists ?? existsSync;
  const override = env[PLAYWRIGHT_EXECUTABLE_ENV];

  if (override) {
    if (pathExists(override)) {
      return override;
    }
    throw new Error(
      `Configured ${PLAYWRIGHT_EXECUTABLE_ENV} does not exist: ${override}`,
    );
  }

  const candidates = buildPlaywrightExecutableCandidates(homeDir);
  const resolved = candidates.find((candidate) => pathExists(candidate));
  if (resolved) {
    return resolved;
  }

  throw new Error(
    `Unable to find a local Playwright browser. Set ${PLAYWRIGHT_EXECUTABLE_ENV} or provide one of the cached Chromium binaries.`,
  );
}

export { PLAYWRIGHT_EXECUTABLE_ENV };
