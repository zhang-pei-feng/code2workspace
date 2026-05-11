import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { AppearanceSettingsSection } from "./appearance-settings";

const setTheme = vi.fn();

vi.mock("next-themes", () => ({
  useTheme: () => ({
    theme: "system",
    setTheme,
  }),
}));

describe("AppearanceSettingsSection", () => {
  it("switches to the selected theme mode", async () => {
    const user = userEvent.setup();
    render(<AppearanceSettingsSection />);

    await user.click(screen.getByRole("button", { name: "深色" }));

    expect(setTheme).toHaveBeenCalledWith("dark");
  });
});
