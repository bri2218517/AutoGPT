"use client";

import { createContext, useContext, useState, useEffect, ReactNode } from "react";

export type LayoutVariant = "classic" | "modern";

const STORAGE_KEY = "autogpt-layout-variant";

interface LayoutContextValue {
  layout: LayoutVariant;
  setLayout: (v: LayoutVariant) => void;
}

const LayoutContext = createContext<LayoutContextValue>({
  layout: "modern",
  setLayout: () => {},
});

export function LayoutProvider({ children }: { children: ReactNode }) {
  const [layout, setLayoutState] = useState<LayoutVariant>("modern");

  useEffect(() => {
    const stored = localStorage.getItem(STORAGE_KEY) as LayoutVariant | null;
    if (stored === "classic" || stored === "modern") {
      setLayoutState(stored);
    }
  }, []);

  function setLayout(v: LayoutVariant) {
    setLayoutState(v);
    localStorage.setItem(STORAGE_KEY, v);
  }

  return (
    <LayoutContext.Provider value={{ layout, setLayout }}>
      {children}
    </LayoutContext.Provider>
  );
}

export function useLayout() {
  return useContext(LayoutContext);
}
