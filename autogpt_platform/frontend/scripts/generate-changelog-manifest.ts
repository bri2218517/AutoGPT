// scripts/generate-changelog-manifest.ts
//
// Scrapes the docs index + each individual page to produce
// src/components/changelog/manifest.ts.
//
//   pnpm tsx scripts/generate-changelog-manifest.ts
//
// Wire into your build via package.json:
//
//   "scripts": {
//     "changelog:generate": "tsx scripts/generate-changelog-manifest.ts",
//     "prebuild": "pnpm changelog:generate"
//   }
//
// Failure modes:
//   - Docs site down → exits non-zero, build fails. Intentional.
//   - One entry's page is malformed → that entry is skipped with a warning,
//     other entries still emitted. Intentional — one bad page shouldn't
//     block the whole frontend deploy.

import { writeFile, mkdir } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const DOCS_INDEX_URL = "https://agpt.co/docs/platform/changelog/changelog";
const DOCS_ENTRY_BASE = "https://agpt.co/docs/platform/changelog/changelog";

const __dirname = dirname(fileURLToPath(import.meta.url));
const OUT_PATH = resolve(__dirname, "../src/components/changelog/manifest.ts");

const MONTHS: Record<string, number> = {
  january: 1, february: 2, march: 3, april: 4,
  may: 5, june: 6, july: 7, august: 8,
  september: 9, october: 10, november: 11, december: 12,
};

interface RawEntry {
  slug: string;
  dateLabel: string; // e.g. "April 10 – May 1"
  highlights: string;
  yearHint: number;
}

interface EnrichedEntry extends RawEntry {
  id: string;          // YYYY-MM-DD of the end of the range
  title: string;       // canonical title from the entry's own H1
  versions: string[];
  isHighlighted?: boolean;
}

// ─── main ─────────────────────────────────────────────────────────────────

async function main() {
  console.log("⤓  Fetching changelog index…");
  const indexMd = await fetchText(DOCS_INDEX_URL);
  const raw = parseIndex(indexMd);
  if (raw.length === 0) {
    throw new Error("No entries parsed from index — has the docs format changed?");
  }
  console.log(`   ${raw.length} entries found`);

  console.log("⤓  Fetching each entry…");
  const enriched: EnrichedEntry[] = [];
  for (const entry of raw) {
    try {
      const detail = await fetchText(`${DOCS_ENTRY_BASE}/${entry.slug}.md`);
      const { title, versions } = parseEntry(detail);
      const id = computeId(entry);
      enriched.push({ ...entry, id, title, versions });
      console.log(`   ✓ ${entry.slug}`);
    } catch (err) {
      console.warn(`   ✗ ${entry.slug}: ${(err as Error).message}`);
    }
  }

  // Sort newest first by id (lexicographic works because ids are YYYY-MM-DD)
  enriched.sort((a, b) => (a.id < b.id ? 1 : -1));

  // Mark the most recent as highlighted
  if (enriched.length > 0) enriched[0].isHighlighted = true;

  await mkdir(dirname(OUT_PATH), { recursive: true });
  await writeFile(OUT_PATH, renderManifest(enriched), "utf8");
  console.log(`\n✓  Wrote ${enriched.length} entries → ${OUT_PATH}`);
}

// ─── fetching ─────────────────────────────────────────────────────────────

async function fetchText(url: string): Promise<string> {
  const res = await fetch(url, {
    headers: { Accept: "text/markdown, text/plain, */*" },
  });
  if (!res.ok) throw new Error(`HTTP ${res.status} for ${url}`);
  return res.text();
}

// ─── parsing ──────────────────────────────────────────────────────────────

function parseIndex(md: string): RawEntry[] {
  // Find year-section headers ("## 2026"). Year associates with each row
  // until the next year header.
  const out: RawEntry[] = [];
  const yearRe = /^##\s+(\d{4})\s*$/gm;
  const yearMatches: { year: number; offset: number }[] = [];
  let m: RegExpExecArray | null;
  while ((m = yearRe.exec(md)) !== null) {
    yearMatches.push({ year: Number(m[1]), offset: m.index + m[0].length });
  }

  // No explicit year header? Fall back to current year and parse the whole doc.
  if (yearMatches.length === 0) {
    yearMatches.push({ year: new Date().getFullYear(), offset: 0 });
  }

  for (let i = 0; i < yearMatches.length; i++) {
    const { year, offset } = yearMatches[i];
    const end = i + 1 < yearMatches.length ? yearMatches[i + 1].offset : md.length;
    const section = md.slice(offset, end);

    // Match: | [date label](slug-url) | highlights |
    const rowRe = /^\|\s*\[([^\]]+)\]\(([^)]+)\)\s*\|\s*([^|]+?)\s*\|/gm;
    let row: RegExpExecArray | null;
    while ((row = rowRe.exec(section)) !== null) {
      const [, dateLabel, link, highlights] = row;
      const slugMatch = link.match(/\/changelog\/([^/]+?)(?:\.md)?$/);
      if (!slugMatch) continue;
      out.push({
        slug: slugMatch[1],
        dateLabel: dateLabel.trim(),
        highlights: highlights.trim(),
        yearHint: year,
      });
    }
  }
  return out;
}

function parseEntry(md: string): { title: string; versions: string[] } {
  const titleMatch = md.match(/^#\s+(.+?)$/m);
  const title = titleMatch?.[1].trim() ?? "Untitled release";

  // Handles both "Platform version:" (singular) and "Platform versions:"
  const versionsLine = md.match(/\*\*Platform versions?:\*\*\s*(.+)/);
  const versions: string[] = [];
  if (versionsLine) {
    const verRe = /`(v[\d.]+)`/g;
    let v: RegExpExecArray | null;
    while ((v = verRe.exec(versionsLine[1])) !== null) {
      versions.push(v[1]);
    }
  }

  return { title, versions };
}

/**
 * Computes a sortable YYYY-MM-DD id from the date label + year hint.
 * Examples:
 *   ("April 10 – May 1",        2026) → "2026-05-01"
 *   ("March 13 – March 20",     2026) → "2026-03-20"
 *   ("February 11 – 26",        2026) → "2026-02-26"   (re-uses start month)
 *   ("January 29 – February 11",2026) → "2026-02-11"
 */
function computeId(entry: RawEntry): string {
  const parts = entry.dateLabel.split(/\s*[–-]\s*/);
  const startStr = (parts[0] ?? "").trim();
  const endStr = (parts[1] ?? startStr).trim();

  const startMonth = MONTHS[startStr.match(/^([A-Za-z]+)/)?.[1].toLowerCase() ?? ""] ?? null;

  let endMonth: number | null = startMonth;
  let endDay = 1;
  const twoPart = endStr.match(/^([A-Za-z]+)\s+(\d+)/);
  if (twoPart) {
    endMonth = MONTHS[twoPart[1].toLowerCase()] ?? startMonth;
    endDay = Number(twoPart[2]);
  } else {
    endDay = Number(endStr.match(/\d+/)?.[0] ?? "1");
  }

  const mm = String(endMonth ?? 1).padStart(2, "0");
  const dd = String(endDay).padStart(2, "0");
  return `${entry.yearHint}-${mm}-${dd}`;
}

// ─── rendering ────────────────────────────────────────────────────────────

function renderManifest(entries: EnrichedEntry[]): string {
  const body = entries
    .map((e) => {
      const props: string[] = [
        `    id: ${JSON.stringify(e.id)},`,
        `    slug: ${JSON.stringify(e.slug)},`,
        `    dateLabel: ${JSON.stringify(`${e.dateLabel}, ${e.yearHint}`)},`,
        `    title: ${JSON.stringify(e.title)},`,
        `    versions: ${JSON.stringify(e.versions)},`,
      ];
      if (e.isHighlighted) props.push(`    isHighlighted: true,`);
      return `  {\n${props.join("\n")}\n  },`;
    })
    .join("\n");

  return [
    `// src/components/changelog/manifest.ts`,
    `// ─────────────────────────────────────────────────────────────────────────`,
    `// AUTO-GENERATED — do not edit by hand.`,
    `// Run \`pnpm changelog:generate\` to regenerate.`,
    `// ─────────────────────────────────────────────────────────────────────────`,
    ``,
    `import type { ChangelogEntry } from "./types";`,
    ``,
    `export const CHANGELOG_MANIFEST: ChangelogEntry[] = [`,
    body,
    `];`,
    ``,
    `export const LATEST_ENTRY = CHANGELOG_MANIFEST[0];`,
    ``,
  ].join("\n");
}

// ─── go ───────────────────────────────────────────────────────────────────

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
