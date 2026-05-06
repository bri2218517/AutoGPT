// src/components/changelog/types.ts

import type { SeenStateAdapter } from "./seen-state";

export interface ChangelogEntry {
  id: string;
  slug: string;
  dateLabel: string;
  title: string;
  versions: string[];
  isHighlighted?: boolean;
}

export interface ChangelogProviderProps {
  hidden?: boolean;
  onOpen?: () => void;
  onEntryView?: (entryId: string) => void;
  seenState?: SeenStateAdapter;
}

export type { SeenStateAdapter } from "./seen-state";
