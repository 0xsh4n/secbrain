"use client";

import { useState } from "react";

interface MarkdownMessageProps {
  content: string;
}

export function MarkdownMessage({ content }: MarkdownMessageProps) {
  // Split into code blocks vs text blocks
  // Regex matches ```language\ncode``` or ```code```
  const parts = content.split(/(```[\s\S]*?```)/g);

  return (
    <div className="space-y-2 text-sm leading-relaxed">
      {parts.map((part, index) => {
        if (part.startsWith("```") && part.endsWith("```")) {
          // It's a code block
          const firstLineEnd = part.indexOf("\n");
          let language = "text";
          let code = "";

          if (firstLineEnd !== -1) {
            language = part.slice(3, firstLineEnd).trim() || "code";
            code = part.slice(firstLineEnd + 1, -3);
          } else {
            code = part.slice(3, -3);
          }

          return <CodeBlock key={index} code={code} language={language} />;
        } else {
          // Regular text: parse headers, lists, bold, inline code
          return <TextBlock key={index} text={part} />;
        }
      })}
    </div>
  );
}

function CodeBlock({ code, language }: { code: string; language: string }) {
  const [copied, setCopied] = useState(false);

  function copyToClipboard() {
    navigator.clipboard.writeText(code);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  return (
    <div className="my-2.5 overflow-hidden rounded-md border border-border bg-[#0d1117] font-mono text-xs shadow-sm">
      <div className="flex items-center justify-between border-b border-border/60 bg-surface-2/60 px-3 py-1.5 text-muted">
        <span className="font-semibold uppercase tracking-wider text-[11px] text-fg/80">
          {language}
        </span>
        <button
          onClick={copyToClipboard}
          className="rounded px-2 py-0.5 text-[11px] text-muted transition hover:bg-surface hover:text-accent"
        >
          {copied ? "✓ Copied!" : "Copy code"}
        </button>
      </div>
      <pre className="overflow-x-auto p-3.5 text-[#e6edf3] leading-normal">
        <code>{code}</code>
      </pre>
    </div>
  );
}

function TextBlock({ text }: { text: string }) {
  const lines = text.split("\n");
  const renderedElements: React.ReactNode[] = [];

  let currentList: React.ReactNode[] = [];
  let isNumberedList = false;

  function flushList() {
    if (currentList.length > 0) {
      if (isNumberedList) {
        renderedElements.push(
          <ol key={`list-${renderedElements.length}`} className="my-2 list-decimal space-y-1 pl-5">
            {currentList}
          </ol>
        );
      } else {
        renderedElements.push(
          <ul key={`list-${renderedElements.length}`} className="my-2 list-disc space-y-1 pl-5">
            {currentList}
          </ul>
        );
      }
      currentList = [];
    }
  }

  lines.forEach((line, i) => {
    const trimmed = line.trim();

    // Headers
    if (trimmed.startsWith("### ")) {
      flushList();
      renderedElements.push(
        <h4 key={i} className="mt-3 mb-1 font-semibold text-fg text-sm">
          {formatInline(trimmed.slice(4))}
        </h4>
      );
      return;
    }
    if (trimmed.startsWith("## ")) {
      flushList();
      renderedElements.push(
        <h3 key={i} className="mt-4 mb-1 font-bold text-fg text-base border-b border-border/40 pb-1">
          {formatInline(trimmed.slice(3))}
        </h3>
      );
      return;
    }
    if (trimmed.startsWith("# ")) {
      flushList();
      renderedElements.push(
        <h2 key={i} className="mt-4 mb-1.5 font-bold text-fg text-lg">
          {formatInline(trimmed.slice(2))}
        </h2>
      );
      return;
    }

    // Bullet lists
    if (trimmed.startsWith("- ") || trimmed.startsWith("* ")) {
      if (isNumberedList) flushList();
      isNumberedList = false;
      currentList.push(
        <li key={i} className="text-fg/90">
          {formatInline(trimmed.slice(2))}
        </li>
      );
      return;
    }

    // Numbered lists
    const matchNumber = trimmed.match(/^(\d+)\.\s+(.*)$/);
    if (matchNumber) {
      if (!isNumberedList) flushList();
      isNumberedList = true;
      currentList.push(
        <li key={i} className="text-fg/90">
          {formatInline(matchNumber[2])}
        </li>
      );
      return;
    }

    // Empty lines
    if (!trimmed) {
      flushList();
      return;
    }

    // Regular paragraph
    flushList();
    renderedElements.push(
      <p key={i} className="my-1.5 text-fg/90 leading-relaxed">
        {formatInline(line)}
      </p>
    );
  });

  flushList();

  return <>{renderedElements}</>;
}

// Inline formatting for Markdown text and code blocks.
function formatInline(text: string): React.ReactNode {
  // Match `inline_code`, **bold**, [E1]
  const tokens = text.split(/(`[^`]+`|\*\*[^*]+\*\*|\[E\d+\])/g);

  return tokens.map((token, i) => {
    if (token.startsWith("`") && token.endsWith("`")) {
      return (
        <code
          key={i}
          className="rounded bg-surface-2 px-1.5 py-0.5 font-mono text-xs text-accent border border-border/40"
        >
          {token.slice(1, -1)}
        </code>
      );
    }
    if (token.startsWith("**") && token.endsWith("**")) {
      return (
        <strong key={i} className="font-semibold text-fg">
          {token.slice(2, -2)}
        </strong>
      );
    }
    if (/^\[E\d+\]$/.test(token)) {
      return (
        <span
          key={i}
          className="inline-block rounded bg-accent-dim/20 px-1 py-0.2 text-[11px] font-mono text-accent font-semibold ml-0.5 mr-0.5"
        >
          {token}
        </span>
      );
    }
    return token;
  });
}
