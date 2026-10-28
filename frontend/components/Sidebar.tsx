"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useAuth } from "@/lib/auth";

const NAV = [
  { href: "/dashboard", label: "Dashboard", short: "Home", icon: "⌂" },
  { href: "/chat", label: "Knowledge Chat", short: "Chat", icon: "◉" },
  { href: "/library", label: "Document Library", short: "Library", icon: "▤" },
  { href: "/collections", label: "Collections", short: "Collections", icon: "▦" },
  { href: "/ingest", label: "Ingestion Queue", short: "Ingest", icon: "↑" },
  { href: "/search", label: "Search", short: "Search", icon: "⌕" },
  { href: "/models", label: "Model Status", short: "Models", icon: "◇" },
  { href: "/api-keys", label: "API Keys", short: "API Keys", icon: "⌘" },
  { href: "/settings", label: "Settings", short: "Settings", icon: "⚙" },
];

const MOBILE_MAIN = [NAV[0], NAV[1], NAV[2], NAV[5]];

export function Sidebar() {
  const pathname = usePathname();
  const { user, logout } = useAuth();
  const [moreOpen, setMoreOpen] = useState(false);

  useEffect(() => setMoreOpen(false), [pathname]);

  const isActive = (href: string) => pathname === href || pathname.startsWith(`${href}/`);
  const linkClass = (href: string) =>
    `flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm transition ${
      isActive(href)
        ? "bg-accent/10 text-accent shadow-[inset_2px_0_0_#38bdf8]"
        : "text-muted hover:bg-surface-2 hover:text-fg"
    }`;

  return (
    <>
      <aside className="hidden h-dvh w-64 shrink-0 flex-col border-r border-border/80 bg-surface/90 px-3 py-4 md:flex">
        <Link href="/dashboard" className="mb-7 flex items-center gap-3 px-3">
          <span className="flex h-10 w-10 items-center justify-center rounded-2xl border border-accent/20 bg-accent/10 text-lg text-accent">◆</span>
          <span>
            <span className="block text-sm font-semibold tracking-wide text-fg">SecBrain</span>
            <span className="block text-[11px] text-muted">Security knowledge hub</span>
          </span>
        </Link>

        <div className="mb-2 px-3 text-[10px] font-semibold uppercase tracking-[0.18em] text-muted/70">Workspace</div>
        <nav className="flex-1 space-y-1 overflow-y-auto">
          {NAV.map((item) => (
            <Link key={item.href} href={item.href} aria-current={isActive(item.href) ? "page" : undefined} className={linkClass(item.href)}>
              <span className="w-5 text-center text-base opacity-80">{item.icon}</span>
              <span>{item.label}</span>
            </Link>
          ))}
        </nav>

        <div className="mt-4 rounded-2xl border border-border/70 bg-bg/60 p-3">
          <div className="truncate text-xs font-medium text-fg">{user?.full_name || user?.email}</div>
          <div className="mt-0.5 truncate text-[11px] text-muted">{user?.role} · SecBrain</div>
          <button onClick={logout} className="mt-3 text-xs text-muted transition hover:text-danger">Sign out</button>
        </div>
      </aside>

      <nav aria-label="Mobile navigation" className="fixed inset-x-0 bottom-0 z-40 border-t border-border/80 bg-surface/95 px-2 pb-[max(env(safe-area-inset-bottom),0.5rem)] pt-2 shadow-[0_-12px_35px_rgba(0,0,0,0.25)] backdrop-blur-xl md:hidden">
        <div className="mx-auto grid max-w-lg grid-cols-5 gap-1">
          {MOBILE_MAIN.map((item) => (
            <Link key={item.href} href={item.href} aria-current={isActive(item.href) ? "page" : undefined}
              className={`flex min-h-12 flex-col items-center justify-center gap-0.5 rounded-xl text-[10px] transition ${isActive(item.href) ? "bg-accent/10 text-accent" : "text-muted"}`}>
              <span className="text-lg leading-5">{item.icon}</span>
              <span>{item.short}</span>
            </Link>
          ))}
          <button type="button" aria-expanded={moreOpen} onClick={() => setMoreOpen((open) => !open)}
            className={`flex min-h-12 flex-col items-center justify-center gap-0.5 rounded-xl text-[10px] transition ${moreOpen ? "bg-accent/10 text-accent" : "text-muted"}`}>
            <span className="text-lg leading-5">{moreOpen ? "×" : "•••"}</span>
            <span>More</span>
          </button>
        </div>
      </nav>

      {moreOpen && (
        <>
          <button aria-label="Close menu" className="fixed inset-0 z-30 bg-black/45 md:hidden" onClick={() => setMoreOpen(false)} />
          <div className="fixed inset-x-3 bottom-[calc(5rem+env(safe-area-inset-bottom))] z-40 rounded-2xl border border-border bg-surface p-2 shadow-2xl md:hidden">
            <div className="mb-2 px-3 pt-2 text-[10px] font-semibold uppercase tracking-[0.18em] text-muted/70">More workspace tools</div>
            {NAV.filter((item) => !MOBILE_MAIN.some((main) => main.href === item.href)).map((item) => (
              <Link key={item.href} href={item.href} className={linkClass(item.href)}>
                <span className="w-5 text-center text-base">{item.icon}</span>{item.label}
              </Link>
            ))}
            <div className="mt-2 border-t border-border px-3 pt-3">
              <div className="truncate text-xs text-muted">{user?.email}</div>
              <button onClick={logout} className="mt-2 rounded-lg px-2 py-2 text-sm text-danger">Sign out</button>
            </div>
          </div>
        </>
      )}
    </>
  );
}
