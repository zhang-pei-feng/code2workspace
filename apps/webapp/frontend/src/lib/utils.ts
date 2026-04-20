import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function formatTimestamp(value: string | null | undefined): string {
  if (!value) return "n/a";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

export function statusTone(status: string | null | undefined): string {
  const normalized = String(status || "idle").toLowerCase();
  if (normalized === "running" || normalized === "queued") return "warning";
  if (normalized === "succeeded" || normalized === "completed") return "success";
  if (normalized === "failed" || normalized === "interrupted" || normalized === "timed_out") {
    return "danger";
  }
  return "neutral";
}

export function truncate(value: string | null | undefined, max = 96): string {
  if (!value) return "";
  return value.length <= max ? value : `${value.slice(0, max - 1)}…`;
}
