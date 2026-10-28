"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useAuth } from "@/lib/auth";

const NAV = [
  { href: "/dashboard", label: "Dashboard" },
  { href: "/library", label: "Document Library" },
  { href: "/collections", label: "Collections" },
  { href: "/ingest", label: "Ingestion Queue" },
  { href: "/search", label: "Search" },
  { href: "/chat", label: "Knowledge Chat" },
  { href: "/models", label: "Model Status" },
  { href: "/api-keys", label: "API Keys" },
  { href: "/settings", label: "Settings" },
];

export function Sidebar() {
  const pathname = usePathname();
  const { user, logout } = useAuth();
  return (
    <aside className="flex h-screen w-60 flex-col border-r border-border bg-surface">
      <div className="flex items-center gap-2 border-b border-border px-4 py-4">
        <span className="text-lg font-bold text-accent">◆ SecBrain</span>
      </div>
      <nav className="flex-1 overflow-y-auto p-2">
        {NAV.map((item) => {
          const active = pathname === item.href || pathname.startsWith(item.href + "/");
          return (
            <Link
              key={item.href}
              href={item.href}
              className={`mb-1 block rounded-md px-3 py-2 text-sm transition-colors ${
                active ? "bg-accent-dim/15 text-accent" : "text-muted hover:bg-surface-2 hover:text-fg"
              }`}
            >
              {item.label}
            </Link>
          );
        })}
      </nav>
      <div className="border-t border-border p-3 text-xs text-muted">
        <div className="truncate">{user?.email}</div>
        <div className="mb-2 uppercase tracking-wide opacity-70">{user?.role}</div>
        <button onClick={logout} className="text-danger hover:underline">
          Sign out
        </button>
      </div>
    </aside>
  );
}
