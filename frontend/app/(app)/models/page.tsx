"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { ModelStatus } from "@/lib/types";
import { Card, CardHeader, Badge, Spinner, ErrorNote } from "@/components/ui";

export default function ModelsPage() {
  const [status, setStatus] = useState<ModelStatus | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  function load() {
    setLoading(true);
    api<ModelStatus>("/models/status")
      .then(setStatus)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }
  useEffect(load, []);

  if (loading) return <Spinner />;
  if (error) return <ErrorNote message={error} />;
  if (!status) return null;

  const g = status.generation;
  return (
    <div className="space-y-4">
      <h1 className="text-xl font-semibold">Model Status</h1>
      <p className="text-sm text-muted">
        Models are configured entirely via environment variables — no source changes required.
        The knowledge base works for search and document management even when no generation model is available.
      </p>

      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        <Card className="p-4">
          <CardHeader title="Generation" />
          <dl className="space-y-2 pt-3 text-sm">
            <Row k="Provider" v={g.provider} />
            <Row k="Model" v={g.model} />
            <Row k="Status" v={<Badge>{g.available ? "COMPLETED" : "FAILED"}</Badge>} />
            <Row k="Detail" v={g.detail} />
            <Row k="Context tokens" v={String(g.context_tokens)} />
            <Row k="Max output" v={String(g.max_output_tokens)} />
            <Row k="Outbound disabled" v={g.outbound_disabled ? "yes" : "no"} />
            <Row k="Last checked" v={new Date(g.last_checked).toLocaleString()} />
          </dl>
        </Card>
        <Card className="p-4">
          <CardHeader title="Embedding" />
          <dl className="space-y-2 pt-3 text-sm">
            <Row k="Provider" v={status.embedding.provider} />
            <Row k="Model" v={status.embedding.model} />
            <Row k="Version" v={status.embedding.version} />
            <Row k="Dimensions" v={String(status.embedding.dim)} />
            <Row k="Vector store" v={status.vector_store} />
          </dl>
          <p className="mt-3 text-xs text-muted">
            Embedding versions are tracked per document so incompatible vector spaces are never mixed.
          </p>
        </Card>
      </div>
    </div>
  );
}

function Row({ k, v }: { k: string; v: React.ReactNode }) {
  return (
    <div className="flex items-start justify-between gap-3">
      <dt className="shrink-0 text-muted">{k}</dt>
      <dd className="min-w-0 break-words text-right text-fg">{v}</dd>
    </div>
  );
}
