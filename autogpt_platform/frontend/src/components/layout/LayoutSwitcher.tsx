"use client";

import { useLayout, LayoutVariant } from "./LayoutContext";

const OPTIONS: { value: LayoutVariant; label: string }[] = [
  { value: "classic", label: "Classic" },
  { value: "modern", label: "Modern" },
];

export function LayoutSwitcher() {
  const { layout, setLayout } = useLayout();

  return (
    <div className="fixed bottom-4 left-1/2 z-50 flex -translate-x-1/2 items-center gap-2 rounded-lg border border-zinc-200 bg-white px-3 py-2 shadow-lg">
      <span className="text-xs font-medium text-zinc-500">Layout</span>
      <select
        value={layout}
        onChange={(e) => setLayout(e.target.value as LayoutVariant)}
        className="cursor-pointer rounded-md border border-zinc-200 bg-zinc-50 px-2 py-1 text-sm font-medium text-zinc-700 outline-none transition-colors hover:bg-zinc-100"
      >
        {OPTIONS.map((opt) => (
          <option key={opt.value} value={opt.value}>
            {opt.label}
          </option>
        ))}
      </select>
    </div>
  );
}
