"use client";

import { useSearchParams } from "next/navigation";

import { buildChatHref } from "@/lib/settings";

import { SettingsPageContent } from "./settings-page";

export function SettingsPageRoute() {
  const searchParams = useSearchParams();

  return <SettingsPageContent backHref={buildChatHref(searchParams.toString())} />;
}
