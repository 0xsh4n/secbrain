"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth";
import { api } from "@/lib/api";
import { Sidebar } from "@/components/Sidebar";
import { Spinner } from "@/components/ui";

export default function AppLayout({ children }: { children: React.ReactNode }) {
  const { user, loading } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (!loading && !user) router.replace("/login");
  }, [loading, user, router]);

  useEffect(() => {
    if (!user) return;
    let active = true;
    let syncing = false;
    const sync = async () => {
      if (syncing) return;
      syncing = true;
      try {
        const state = await api<{ connected: boolean }>("/drive-sync/status");
        if (active && state.connected) await api("/drive-sync/sync", { method: "POST" });
      } catch { /* Sync is optional; Settings shows connection errors and manual controls. */ }
      finally { syncing = false; }
    };
    void sync();
    const timer = window.setInterval(() => void sync(), 60_000);
    return () => { active = false; window.clearInterval(timer); };
  }, [user?.id]);

  if (loading) return <Spinner />;
  if (!user) return null;

  return (
    <div className="flex min-h-dvh overflow-hidden md:h-dvh">
      <Sidebar />
      <main className="min-h-dvh min-w-0 flex-1 overflow-x-hidden overflow-y-auto md:h-dvh md:min-h-0">
        <div className="mx-auto min-h-full max-w-7xl px-3 pb-[calc(6.25rem+env(safe-area-inset-bottom))] pt-4 sm:px-5 md:px-7 md:py-7">
          {children}
        </div>
      </main>
    </div>
  );
}
