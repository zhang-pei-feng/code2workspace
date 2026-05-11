import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { cn } from "@/lib/utils";
import { Button } from "../ui/button";
import { Check, ChevronDown, Cpu } from "lucide-react";

export type ModelOption = {
  spec: string;
  provider: string;
  model: string;
  label: string;
};

type ModelSelectorProps = {
  currentModel: string | null;
  defaultModel: string | null;
  models: ModelOption[];
  open: boolean;
  disabled?: boolean;
  onToggle: () => void;
  onSelect: (model: string | null) => void;
};

function groupModelsByProvider(models: ModelOption[]) {
  const groups = new Map<string, ModelOption[]>();
  for (const item of models) {
    const current = groups.get(item.provider) ?? [];
    current.push(item);
    groups.set(item.provider, current);
  }
  return Array.from(groups.entries());
}

function getButtonLabel(
  currentModel: string | null,
  defaultModel: string | null,
  models: ModelOption[],
) {
  const selected = models.find((item) => item.spec === currentModel);
  if (selected) return selected.label;
  if (currentModel) return currentModel;
  const fallback = models.find((item) => item.spec === defaultModel);
  return fallback?.label ?? "当前会话模型";
}

export function ModelSelector({
  currentModel,
  defaultModel,
  models,
  open,
  disabled,
  onToggle,
  onSelect,
}: ModelSelectorProps) {
  const triggerRef = useRef<HTMLButtonElement | null>(null);
  const [menuStyle, setMenuStyle] = useState<Record<string, string>>({});

  useEffect(() => {
    if (!open || !triggerRef.current || typeof window === "undefined") {
      return;
    }

    const updatePosition = () => {
      const rect = triggerRef.current?.getBoundingClientRect();
      if (!rect) return;
      setMenuStyle({
        position: "fixed",
        right: `${Math.max(window.innerWidth - rect.right, 16)}px`,
        bottom: `${Math.max(window.innerHeight - rect.top + 8, 16)}px`,
      });
    };

    updatePosition();
    window.addEventListener("resize", updatePosition);
    window.addEventListener("scroll", updatePosition, true);
    return () => {
      window.removeEventListener("resize", updatePosition);
      window.removeEventListener("scroll", updatePosition, true);
    };
  }, [open]);

  const menu = open ? (
    <div
      style={menuStyle}
      className="z-[100] w-80 rounded-xl border border-border bg-popover p-2 text-popover-foreground shadow-lg"
    >
      <div className="max-h-[min(24rem,calc(100vh-9rem))] overflow-y-auto overscroll-contain pr-1 [&::-webkit-scrollbar]:w-1.5 [&::-webkit-scrollbar-thumb]:rounded-full [&::-webkit-scrollbar-thumb]:bg-slate-300 [&::-webkit-scrollbar-track]:bg-transparent">
        <div className="px-2 py-1 text-xs font-medium tracking-wide text-muted-foreground uppercase whitespace-nowrap">
          当前会话模型
        </div>
        <button
          type="button"
          className={cn(
            "flex w-full items-center justify-between rounded-lg px-3 py-2 text-left text-sm hover:bg-accent",
            !currentModel && "bg-accent",
          )}
          onClick={() => onSelect(null)}
        >
          <span>默认模型</span>
          {!currentModel && <Check className="size-4 text-muted-foreground" />}
        </button>
        {groupModelsByProvider(models).map(([provider, providerModels]) => (
          <div
            key={provider}
            className="mt-2"
          >
            <div className="px-2 py-1 text-[11px] font-medium tracking-wide text-muted-foreground uppercase whitespace-nowrap">
              {provider}
            </div>
            {providerModels.map((item) => (
              <button
                key={item.spec}
                type="button"
                className={cn(
                  "flex w-full items-start justify-between rounded-lg px-3 py-2 text-left text-sm hover:bg-accent",
                  currentModel === item.spec && "bg-accent",
                )}
                onClick={() => onSelect(item.spec)}
              >
                <div className="min-w-0 pr-2">
                  <div className="break-all font-medium">{item.label}</div>
                  <div className="break-all text-xs text-muted-foreground">{item.spec}</div>
                </div>
                {currentModel === item.spec && (
                  <Check className="mt-0.5 ml-2 size-4 shrink-0 text-muted-foreground" />
                )}
              </button>
            ))}
          </div>
        ))}
      </div>
    </div>
  ) : null;

  return (
    <div className="relative">
      <Button
        ref={triggerRef}
        type="button"
        variant="outline"
        className="gap-2"
        disabled={disabled}
        onClick={onToggle}
      >
        <Cpu className="size-4" />
        {getButtonLabel(currentModel, defaultModel, models)}
        <ChevronDown className="size-4" />
      </Button>
      {open && typeof document !== "undefined" ? createPortal(menu, document.body) : null}
    </div>
  );
}
