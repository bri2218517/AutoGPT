"use client";

import { useEffect, useRef } from "react";
import * as DialogPrimitive from "@radix-ui/react-dialog";
import { CHANGELOG_MANIFEST } from "./manifest";
import { ChangelogContent } from "./ChangelogContent";
import { cn } from "@/lib/utils";

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  activeID: string;
  onActiveIDChange: (id: string) => void;
}

export function ChangelogModal({
  open,
  onOpenChange,
  activeID,
  onActiveIDChange,
}: Props) {
  const contentRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (contentRef.current) contentRef.current.scrollTop = 0;
  }, [activeID]);

  const activeEntry =
    CHANGELOG_MANIFEST.find((e) => e.id === activeID) ?? CHANGELOG_MANIFEST[0];

  return (
    <DialogPrimitive.Root open={open} onOpenChange={onOpenChange}>
      <DialogPrimitive.Portal>
        <DialogPrimitive.Overlay className="fixed inset-0 z-50 bg-black/60 data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0" />
        <DialogPrimitive.Content
          className={cn(
            "fixed left-[50%] top-[50%] z-50 translate-x-[-50%] translate-y-[-50%]",
            "p-0 gap-0 overflow-hidden",
            "max-w-[1080px] w-[92vw] h-[78vh] max-h-[820px]",
            "flex flex-row",
            "bg-background rounded-lg shadow-xl border border-border",
            "data-[state=open]:animate-in data-[state=closed]:animate-out",
            "data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0",
            "data-[state=closed]:zoom-out-95 data-[state=open]:zoom-in-95",
            "data-[state=closed]:slide-out-to-left-1/2 data-[state=closed]:slide-out-to-top-[48%]",
            "data-[state=open]:slide-in-from-left-1/2 data-[state=open]:slide-in-from-top-[48%]",
          )}
        >
          <span className="sr-only">
            <DialogPrimitive.Title>
              What&apos;s new in AutoGPT
            </DialogPrimitive.Title>
          </span>

          {/* Sidebar */}
          <aside className="w-[280px] shrink-0 border-r border-border bg-muted/30 flex flex-col">
            <div className="px-6 pt-6 pb-4">
              <div className="flex items-center gap-2 mb-1">
                <div
                  className="w-2 h-2 rounded-full"
                  style={{
                    background: "linear-gradient(135deg, #f59e0b, #ef4444)",
                  }}
                />
                <span className="text-[11px] uppercase tracking-[0.18em] text-muted-foreground font-semibold">
                  AutoGPT
                </span>
              </div>
              <h2
                className="text-[22px] leading-tight"
                style={{
                  fontFamily:
                    "var(--font-changelog-display, ui-serif, Georgia, serif)",
                }}
              >
                What&apos;s new
              </h2>
            </div>

            <nav
              className="flex-1 overflow-y-auto px-3 pb-3"
              aria-label="Changelog entries"
            >
              {CHANGELOG_MANIFEST.map((entry) => {
                const isActive = entry.id === activeID;
                return (
                  <button
                    key={entry.id}
                    onClick={() => onActiveIDChange(entry.id)}
                    className={cn(
                      "w-full text-left px-3 py-2.5 rounded-lg mb-0.5 transition-all relative group border",
                      isActive
                        ? "bg-background shadow-sm border-border/80"
                        : "hover:bg-background/60 border-transparent",
                    )}
                    aria-current={isActive ? "page" : undefined}
                  >
                    {isActive && entry.isHighlighted && (
                      <span
                        className="absolute left-0 top-2 bottom-2 w-[2px] rounded-full"
                        style={{
                          background:
                            "linear-gradient(to bottom, #f59e0b, #ef4444)",
                        }}
                        aria-hidden
                      />
                    )}
                    <div className="flex items-center gap-1.5 mb-1">
                      <span className="text-[10px] italic font-serif text-muted-foreground">
                        {entry.dateLabel}
                      </span>
                      {entry.isHighlighted && (
                        <span className="text-[9px] uppercase tracking-wider font-semibold text-emerald-700 bg-emerald-50 px-1.5 py-0.5 rounded">
                          New
                        </span>
                      )}
                    </div>
                    <div
                      className={cn(
                        "text-[13px] leading-snug line-clamp-2 transition-colors",
                        isActive
                          ? "text-foreground font-medium"
                          : "text-muted-foreground group-hover:text-foreground",
                      )}
                    >
                      {entry.title}
                    </div>
                  </button>
                );
              })}
            </nav>

            <div className="px-6 py-4 border-t border-border text-[11px] text-muted-foreground">
              Press{" "}
              <kbd className="font-mono bg-muted text-foreground/80 px-1.5 py-0.5 rounded text-[10px]">
                esc
              </kbd>{" "}
              to close
            </div>
          </aside>

          {/* Content */}
          <main className="flex-1 relative">
            <div
              ref={contentRef}
              className="absolute inset-0 overflow-y-auto px-14 py-12"
            >
              <div className="max-w-[640px] mx-auto">
                <ChangelogContent entry={activeEntry} />
              </div>
            </div>
          </main>
        </DialogPrimitive.Content>
      </DialogPrimitive.Portal>
    </DialogPrimitive.Root>
  );
}
