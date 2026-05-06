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
      <header className="pb-8 border-b border-border">
        <div className="flex items-center gap-2 mb-3">
          {entry.isHighlighted && (
            <>
              <span className="text-xs uppercase tracking-[0.18em] font-medium text-emerald-700">
                Latest
              </span>
              <span className="text-muted-foreground/50">·</span>
            </>
          )}
          <span className="text-sm text-muted-foreground italic font-serif">
            {entry.dateLabel}
          </span>
        </div>
        <h1
          className="text-[42px] leading-[1.05] font-medium tracking-tight mb-4"
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
              className="font-mono text-[12px] px-2 py-0.5 bg-muted text-muted-foreground rounded"
            >
              {v}
            </span>
          ))}
        </div>
      </header>

      <div>
        {markdown === null && error === null && (
          <div className="flex items-center gap-2 text-muted-foreground py-12">
            <SpinnerGap className="w-4 h-4 animate-spin" />
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
              Read it on agpt.co <ArrowSquareOut className="w-3 h-3" />
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
    <h2 className="text-2xl font-medium mt-12 mb-4 tracking-tight">
      {children}
    </h2>
  ),
  h3: ({ children }) => (
    <h3 className="text-lg font-medium mt-8 mb-3">{children}</h3>
  ),
  p: ({ children }) => (
    <p className="text-muted-foreground leading-[1.7] text-[15px] mb-4">
      {children}
    </p>
  ),
  a: ({ children, href }) => (
    <a
      href={resolveLink(href)}
      target="_blank"
      rel="noreferrer"
      className="text-foreground underline decoration-border underline-offset-2 hover:decoration-foreground transition-colors"
    >
      {children}
    </a>
  ),
  ul: ({ children }) => (
    <ul className="my-4 space-y-2 list-none pl-0">{children}</ul>
  ),
  li: ({ children }) => (
    <li className="text-[14px] text-muted-foreground leading-relaxed pl-4 relative">
      <span className="absolute left-0 top-2.5 w-1 h-1 rounded-full bg-muted-foreground/40" />
      {children}
    </li>
  ),
  strong: ({ children }) => (
    <strong className="font-medium text-foreground">{children}</strong>
  ),
  code: ({ children }) => (
    <code className="font-mono text-[12px] bg-muted text-foreground px-1.5 py-0.5 rounded">
      {children}
    </code>
  ),
  hr: () => <hr className="my-10 border-border" />,
  figure: ({ children }) => <figure className="my-8">{children}</figure>,
  figcaption: ({ children }) => (
    <figcaption className="mt-3 text-sm text-muted-foreground italic font-serif">
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
        "[&>*:not(summary)]:mt-3 [&>*:not(summary)]:ml-6",
      )}
    >
      {children}
    </details>
  ),
  summary: ({ children }) => (
    <summary
      className={cn(
        "flex items-center gap-2 cursor-pointer select-none",
        "list-none [&::-webkit-details-marker]:hidden [&::marker]:hidden",
        "hover:opacity-80 transition-opacity",
      )}
    >
      <CaretRight
        className="w-4 h-4 text-muted-foreground shrink-0 transition-transform group-open:rotate-90"
        aria-hidden
      />
      <span className="font-medium text-[15px] text-foreground">
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
