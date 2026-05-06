"use client";

import { useEffect, useRef, useState } from "react";
import { CHANGELOG_MANIFEST, LATEST_ENTRY } from "./manifest";
import { localStorageAdapter, type SeenStateAdapter } from "./seen-state";

const PILL_DELAY_MS = 800;

export function useChangelog(opts?: {
  onOpen?: () => void;
  onEntryView?: (id: string) => void;
  hidden?: boolean;
  seenState?: SeenStateAdapter;
}) {
  const adapterRef = useRef<SeenStateAdapter>(
    opts?.seenState ?? localStorageAdapter,
  );
  const adapter = adapterRef.current;

  const [open, setOpenState] = useState(false);
  const [pillVisible, setPillVisible] = useState(false);
  const [activeId, setActiveIdState] = useState(LATEST_ENTRY.id);
  const [lastSeenId, setLastSeenId] = useState<string | null>(null);
  const [hydrated, setHydrated] = useState(false);

  useEffect(() => {
    let cancelled = false;
    adapter
      .read()
      .then((value) => {
        if (cancelled) return;
        setLastSeenId(value);
        setHydrated(true);
      })
      .catch(() => {
        if (!cancelled) setHydrated(true);
      });
    return () => {
      cancelled = true;
    };
  }, [adapter]);

  const hasUnread = hydrated && lastSeenId !== LATEST_ENTRY.id;

  useEffect(() => {
    if (!hydrated || opts?.hidden || !hasUnread) {
      setPillVisible(false);
      return;
    }
    const timer = setTimeout(() => setPillVisible(true), PILL_DELAY_MS);
    return () => clearTimeout(timer);
  }, [hydrated, opts?.hidden, hasUnread]);

  function markSeen() {
    setLastSeenId(LATEST_ENTRY.id);
    void adapter.write(LATEST_ENTRY.id);
  }

  function setOpen(next: boolean) {
    setOpenState(next);
    if (next) {
      setPillVisible(false);
      markSeen();
      opts?.onOpen?.();
    }
  }

  function dismissPill() {
    setPillVisible(false);
    markSeen();
  }

  function setActiveId(id: string) {
    setActiveIdState(id);
    opts?.onEntryView?.(id);
  }

  useEffect(() => {
    function handler(e: KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && e.key === "/") {
        e.preventDefault();
        setOpen(!open);
      }
    }
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [open]);

  return {
    open,
    setOpen,
    pillVisible,
    dismissPill,
    activeId,
    setActiveId,
    hasUnread,
  };
}

export { CHANGELOG_MANIFEST };
