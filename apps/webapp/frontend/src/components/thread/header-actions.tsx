"use client";

import Link from "next/link";
import { Settings2, SquarePen } from "lucide-react";

import { Button } from "@/components/ui/button";

export function ThreadHeaderActions({
  settingsHref,
  onNewThread,
}: {
  settingsHref: string;
  onNewThread: () => void;
}) {
  return (
    <div className="flex items-center gap-3">
      <Button
        asChild
        variant="ghost"
        className="gap-2 px-3"
        data-header-action="settings"
      >
        <Link href={settingsHref}>
          <Settings2 className="size-5" />
          设置
        </Link>
      </Button>
      <Button
        type="button"
        variant="ghost"
        className="gap-2 px-3"
        data-header-action="new-thread"
        onClick={onNewThread}
      >
        <SquarePen className="size-5" />
        新建对话
      </Button>
    </div>
  );
}
