"use client";

import { Button } from "@/components/ui/button";
import { useTheme } from "next-themes";

const LABELS: Record<string, string> = {
  light: "浅色",
  dark: "深色",
  system: "跟随系统",
};

export function AppearanceSettingsSection({
  themeModes = ["light", "dark", "system"],
}: {
  themeModes?: string[];
}) {
  const { theme = "system", setTheme } = useTheme();

  return (
    <div className="space-y-4">
      <div>
        <h2 className="text-2xl font-semibold tracking-tight">外观</h2>
        <p className="text-sm text-muted-foreground">
          主题切换保存在当前浏览器，不会改动 CLI/TUI 配置。
        </p>
      </div>
      <div className="flex flex-wrap gap-3">
        {themeModes.map((mode) => (
          <Button
            key={mode}
            type="button"
            variant={theme === mode ? "default" : "outline"}
            onClick={() => setTheme(mode)}
          >
            {LABELS[mode] ?? mode}
          </Button>
        ))}
      </div>
    </div>
  );
}
