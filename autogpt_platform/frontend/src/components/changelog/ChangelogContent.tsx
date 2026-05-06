"use client";

import { useEffect, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import rehypeRaw from "rehype-raw";
import { ArrowSquareOut, CaretRight, SpinnerGap } from "@phosphor-icons/react";
import type { ChangelogEntry } from "./types";
import { cn } from "@/lib/utils";

const DOCS_ORIGIN = "https://agpt.co";

interface Props {
  entry: ChangelogEntry;
}

export function ChangelogContent({ entry }: Props) {
  const [markdown, setMarkdown] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setMarkdown(null);
    setError(null);

    fetch(`/api/changelog/${entry.slug}`)
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.text();
      })
      .then((text) => {
        if (!cancelled) setMarkdown(text);
      })
      .catch((e) => {
        if (!cancelled) setError(e.message);
      });

    return () => {
      cancelled = true;
    };
  }, [entry.slug]);

  return (
    <article>
      <header className="border-b border-border pb-8">
        <div className="mb-3 flex items-center gap-2">
          {entry.isHighlighted && (
            <>
              <span className="text-xs font-medium uppercase tracking-[0.18em] text-emerald-700">
                Latest
              </span>
              <span className="text-muted-foreground/50">·</span>
            </>
          )}
          <span className="font-serif text-sm italic text-muted-foreground">
            {entry.dateLabel}
          </span>
        </div>
        <h1
          className="mb-4 text-[42px] font-medium leading-[1.05] tracking-tight"
          style={{
            fontFamily:
              "var(--font-changelog-display, ui-serif, Georgia, serif)",
          }}
        >
          {entry.title}
        </h1>
        <div className="flex flex-wrap gap-1.5">
          {entry.versions.map((v) => (
            <span
              key={v}
              className="rounded bg-muted px-2 py-0.5 font-mono text-[12px] text-muted-foreground"
            >
              {v}
            </span>
          ))}
        </div>
      </header>

      <div>
        {markdown === null && error === null && (
          <div className="flex items-center gap-2 py-12 text-muted-foreground">
            <SpinnerGap className="h-4 w-4 animate-spin" />
            <span className="text-sm">Loading…</span>
          </div>
        )}

        {error && (
          <div className="py-12 text-sm text-muted-foreground">
            <p className="mb-2">Couldn&apos;t load this entry.</p>
            <a
              href={`${DOCS_ORIGIN}/docs/platform/changelog/changelog/${entry.slug}.md`}
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center gap-1 text-foreground hover:underline"
            >
              Read it on agpt.co <ArrowSquareOut className="h-3 w-3" />
            </a>
          </div>
        )}

        {markdown && (
          <ReactMarkdown
            remarkPlugins={[remarkGfm]}
            rehypePlugins={[rehypeRaw]}
            components={markdownComponents}
          >
            {stripLeadingH1(markdown)}
          </ReactMarkdown>
        )}
      </div>
    </article>
  );
}

const markdownComponents: import("react-markdown").Components = {
  h2: ({ children }) => (
    <h2 className="mb-4 mt-12 text-2xl font-medium tracking-tight">
      {children}
    </h2>
  ),
  h3: ({ children }) => (
    <h3 className="mb-3 mt-8 text-lg font-medium">{children}</h3>
  ),
  p: ({ children }) => (
    <p className="mb-4 text-[15px] leading-[1.7] text-muted-foreground">
      {children}
    </p>
  ),
  a: ({ children, href }) => (
    <a
      href={resolveLink(href)}
      target="_blank"
      rel="noreferrer"
      className="text-foreground underline decoration-border underline-offset-2 transition-colors hover:decoration-foreground"
    >
      {children}
    </a>
  ),
  ul: ({ children }) => (
    <ul className="my-4 list-none space-y-2 pl-0">{children}</ul>
  ),
  li: ({ children }) => (
    <li className="relative pl-4 text-[14px] leading-relaxed text-muted-foreground">
      <span className="absolute left-0 top-2.5 h-1 w-1 rounded-full bg-muted-foreground/40" />
      {children}
    </li>
  ),
  strong: ({ children }) => (
    <strong className="font-medium text-foreground">{children}</strong>
  ),
  code: ({ children }) => (
    <code className="rounded bg-muted px-1.5 py-0.5 font-mono text-[12px] text-foreground">
      {children}
    </code>
  ),
  hr: () => <hr className="my-10 border-border" />,
  figure: ({ children }) => <figure className="my-8">{children}</figure>,
  figcaption: ({ children }) => (
    <figcaption className="mt-3 font-serif text-sm italic text-muted-foreground">
      {children}
    </figcaption>
  ),
  img: ({ src, alt }) => (
    // eslint-disable-next-line @next/next/no-img-element
    <img
      src={resolveImageSrc(src)}
      alt={alt ?? ""}
      className="w-full rounded-xl border border-border shadow-sm"
      loading="lazy"
    />
  ),
  details: ({ children }) => (
    <details
      className={cn(
        "group border-t border-border py-4",
        "[&>*:not(summary)]:ml-6 [&>*:not(summary)]:mt-3",
      )}
    >
      {children}
    </details>
  ),
  summary: ({ children }) => (
    <summary
      className={cn(
        "flex cursor-pointer select-none items-center gap-2",
        "list-none [&::-webkit-details-marker]:hidden [&::marker]:hidden",
        "transition-opacity hover:opacity-80",
      )}
    >
      <CaretRight
        className="h-4 w-4 shrink-0 text-muted-foreground transition-transform group-open:rotate-90"
        aria-hidden
      />
      <span className="text-[15px] font-medium text-foreground">
        {children}
      </span>
    </summary>
  ),
};

function resolveImageSrc(src?: string): string {
  if (!src) return "";
  if (src.startsWith("http")) return src;
  if (src.startsWith("/")) return `${DOCS_ORIGIN}${src}`;
  return src;
}

function resolveLink(href?: string): string {
  if (!href) return "#";
  if (href.startsWith("http")) return href;
  if (href.startsWith("/")) return `${DOCS_ORIGIN}${href}`;
  return href;
}

function stripLeadingH1(md: string): string {
  return md.replace(/^\s*#\s+.+?\n/, "");
}
