"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api } from "@/lib/api";
import type { DashboardStats, ModelStatus } from "@/lib/types";
import { Card, CardHeader, Stat, Spinner, ErrorNote, Badge, Empty } from "@/components/ui";

export default function DashboardPage() {
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [model, setModel] = useState<ModelStatus | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([api<DashboardStats>("/dashboard/stats"), api<ModelStatus>("/models/status")])
      .then(([s, m]) => {
        setStats(s);
        setModel(m);
      })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <Spinner />;
  if (error) return <ErrorNote message={error} />;
  if (!stats || !model) return null;

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-4 rounded-2xl border border-accent/15 bg-gradient-to-br from-accent/10 via-surface/90 to-surface/70 p-4 sm:flex-row sm:items-center sm:justify-between sm:p-6">
        <div>
          <p className="text-[10px] font-semibold uppercase tracking-[0.18em] text-accent">Your workspace</p>
          <h1 className="mt-1 text-xl font-semibold sm:text-2xl">Knowledge Dashboard</h1>
          <p className="mt-1 max-w-xl text-sm text-muted">Your indexed security knowledge, model health, and recent activity in one place.</p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Link href="/chat" className="rounded-xl border border-border bg-surface px-4 py-2.5 text-sm text-fg transition hover:border-accent/40 hover:text-accent">Open chat</Link>
          <Link href="/ingest" className="rounded-xl bg-accent-dim px-4 py-2.5 text-sm font-medium text-black transition hover:bg-accent">Add knowledge</Link>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
        <Stat label="Indexed Documents" value={stats.total_documents} />
        <Stat label="Chunks" value={stats.total_chunks} />
        <Stat label="Collections" value={stats.collections} />
        <Stat
          label="Generation Model"
          value={
            <span className={model.generation.available ? "text-success" : "text-danger"}>
              {model.generation.available ? "Online" : "Offline"}
            </span>
          }
        />
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader title="Recent Documents" />
          <div className="divide-y divide-border">
            {stats.recent_documents.length === 0 && <Empty message="No documents yet" />}
            {stats.recent_documents.map((d) => (
              <Link
                key={d.id}
                href={`/documents/${d.id}`}
                className="flex items-center justify-between px-4 py-3 hover:bg-surface-2"
              >
                <span className="truncate pr-4 text-sm">{d.title}</span>
                <Badge>{d.status}</Badge>
              </Link>
            ))}
          </div>
        </Card>

        <Card>
          <CardHeader title="Ingestion Jobs by State" />
          <div className="p-4">
            {Object.keys(stats.jobs_by_state).length === 0 ? (
              <Empty message="No ingestion jobs yet" />
            ) : (
              <div className="flex flex-wrap gap-3">
                {Object.entries(stats.jobs_by_state).map(([state, count]) => (
                  <div
                    key={state}
                    className="flex items-center gap-2 rounded-md border border-border bg-surface-2 px-3 py-2"
                  >
                    <Badge>{state}</Badge>
                    <span className="text-sm font-semibold">{count}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        </Card>

        <Card>
          <CardHeader title="Failed Jobs" />
          <div className="divide-y divide-border">
            {stats.failed_jobs.length === 0 && <Empty message="No failures" />}
            {stats.failed_jobs.map((j) => (
              <div key={j.document_id} className="px-4 py-3 text-sm">
                <Link href={`/documents/${j.document_id}`} className="text-accent hover:underline">
                  {j.document_id.slice(0, 12)}…
                </Link>
                <div className="mt-1 text-xs text-danger">{j.error}</div>
              </div>
            ))}
          </div>
        </Card>

        <Card>
          <CardHeader title="Recent Search Activity" />
          <div className="divide-y divide-border">
            {stats.recent_searches.length === 0 && <Empty message="No recent searches" />}
            {stats.recent_searches.map((a, i) => (
              <div key={i} className="px-4 py-3 text-sm text-muted">
                <span className="text-fg">{a.action}</span> — {a.detail}
              </div>
            ))}
          </div>
        </Card>
      </div>
    </div>
  );
}
