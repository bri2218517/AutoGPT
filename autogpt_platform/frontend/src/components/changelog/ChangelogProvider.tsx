"use client";

import { ChangelogPill } from "./ChangelogPill";
import { ChangelogModal } from "./ChangelogModal";
import { useChangelog } from "./use-changelog";
import type { ChangelogProviderProps } from "./types";

export function ChangelogProvider({
  hidden,
  onOpen,
  onEntryView,
  seenState,
}: ChangelogProviderProps = {}) {
  const cl = useChangelog({ onOpen, onEntryView, hidden, seenState });

  if (hidden) return null;

  return (
    <>
      <ChangelogPill
        visible={cl.pillVisible}
        onClick={() => cl.setOpen(true)}
        onDismiss={cl.dismissPill}
      />
      <ChangelogModal
        open={cl.open}
        onOpenChange={cl.setOpen}
        activeID={cl.activeId}
        onActiveIDChange={cl.setActiveId}
      />
    </>
  );
}
