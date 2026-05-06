"use client";

import { Sparkle, X } from "@phosphor-icons/react";
import { LATEST_ENTRY } from "./manifest";
import { cn } from "@/lib/utils";

interface Props {
  onClick: () => void;
  onDismiss: () => void;
  visible: boolean;
}

export function ChangelogPill({ onClick, onDismiss, visible }: Props) {
  return (
    <div
      className={cn(
        "fixed bottom-6 left-6 z-40 transition-all duration-500",
        visible
          ? "translate-y-0 opacity-100 pointer-events-auto"
          : "translate-y-6 opacity-0 pointer-events-none",
      )}
      style={{
        transitionTimingFunction: "cubic-bezier(0.34, 1.56, 0.64, 1)",
      }}
    >
      <button
        onClick={onClick}
        className={cn(
          "group flex items-center gap-3 rounded-xl pl-3 pr-4 py-3 w-[320px] text-left",
          "bg-background border border-border/80",
          "hover:border-border hover:shadow-lg transition-all",
          "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
        )}
        style={{
          boxShadow:
            "0 1px 0 rgba(0,0,0,0.02), 0 4px 16px rgba(0,0,0,0.06), 0 12px 32px rgba(0,0,0,0.04)",
        }}
        aria-label={`What's new: ${LATEST_ENTRY.title}`}
      >
        <div
          className="relative shrink-0 w-10 h-10 rounded-lg flex items-center justify-center overflow-hidden"
          style={{
            background:
              "linear-gradient(135deg, #fef3c7 0%, #fde68a 50%, #f59e0b 100%)",
          }}
        >
          <Sparkle className="w-4 h-4 text-stone-800/70" weight="fill" />
          <span
            className="absolute top-1 right-1 w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse"
            aria-hidden
          />
        </div>

        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-1.5 mb-0.5">
            <span className="text-[10px] uppercase tracking-[0.12em] font-semibold text-emerald-600">
              New
            </span>
            <span className="text-[11px] text-muted-foreground">·</span>
            <span className="text-[11px] text-muted-foreground italic font-serif">
              {LATEST_ENTRY.dateLabel.split("–")[1]?.trim() ??
                LATEST_ENTRY.dateLabel}
            </span>
          </div>
          <div className="text-[13px] text-foreground font-medium truncate leading-tight">
            {LATEST_ENTRY.title}
          </div>
        </div>

        <span
          role="button"
          tabIndex={0}
          aria-label="Dismiss"
          className="shrink-0 opacity-0 group-hover:opacity-100 transition-opacity p-1 -m-1 rounded hover:bg-muted cursor-pointer"
          onClick={(e) => {
            e.stopPropagation();
            onDismiss();
          }}
          onKeyDown={(e) => {
            if (e.key === "Enter" || e.key === " ") {
              e.stopPropagation();
              onDismiss();
            }
          }}
        >
          <X className="w-3.5 h-3.5 text-muted-foreground" />
        </span>
      </button>
    </div>
  );
}
