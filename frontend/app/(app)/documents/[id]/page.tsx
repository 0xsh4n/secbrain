"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { api } from "@/lib/api";
import type { DocumentOut, JobOut } from "@/lib/types";
import { Card, CardHeader, Badge, Button, Spinner, ErrorNote } from "@/components/ui";

export default function DocumentDetailPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const [doc, setDoc] = useState<DocumentOut | null>(null);
  const [job, setJob] = useState<JobOut | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);

  function load() {
    Promise.all([
      api<DocumentOut>(`/documents/${id}`),
      api<JobOut>(`/documents/${id}/job`).catch(() => null),
    ])
      .then(([d, j]) => {
        setDoc(d);
        setJob(j);
      })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }
  useEffect(load, [id]);

  async function reprocess() {
    setBusy(true);
    try {
      await api(`/documents/${id}/reprocess`, { method: "POST" });
      load();
    } finally {
      setBusy(false);
    }
  }

  async function remove() {
    if (!confirm("Delete this document and all its chunks/vectors?")) return;
    setBusy(true);
    try {
      await api(`/documents/${id}`, { method: "DELETE" });
      router.push("/library");
    } finally {
      setBusy(false);
    }
  }

  if (loading) return <Spinner />;
  if (error) return <ErrorNote message={error} />;
  if (!doc) return null;

  return (
    <div className="space-y-4">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-xl font-semibold">{doc.title}</h1>
          <div className="mt-1 flex items-center gap-2 text-sm text-muted">
            <Badge>{doc.status}</Badge>
            <span className="font-mono">{doc.source_type}</span>
            {doc.is_duplicate && <span className="text-warn">duplicate of {doc.duplicate_of_id}</span>}
          </div>
        </div>
        <div className="flex gap-2">
          <Button variant="ghost" onClick={reprocess} disabled={busy}>
            Reprocess
          </Button>
          <Button variant="danger" onClick={remove} disabled={busy}>
            Delete
          </Button>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        <Card className="p-4 text-sm">
          <dl className="space-y-2">
            <Row k="Chunks" v={String(doc.chunk_count)} />
            <Row k="Bytes" v={String(doc.byte_size)} />
            <Row k="Author" v={doc.author || "—"} />
            <Row k="Source URL" v={doc.source_url || "—"} />
            <Row k="Embedding" v={doc.embedding_version || "—"} />
            <Row k="Content hash" v={doc.content_hash ? doc.content_hash.slice(0, 16) + "…" : "—"} />
            <Row k="Tags" v={doc.tags.join(", ") || "—"} />
          </dl>
        </Card>
        <Card className="p-4 text-sm">
          <CardHeader title="Ingestion Job" />
          {job ? (
            <dl className="space-y-2 pt-3">
              <Row k="State" v={job.state} />
              <Row k="Progress" v={`${Math.round(job.progress * 100)}%`} />
              <Row k="Detail" v={job.detail || "—"} />
              <Row k="Attempts" v={String(job.attempts)} />
              {job.error && <div className="text-danger">{job.error}</div>}
            </dl>
          ) : (
            <p className="pt-3 text-muted">No job record.</p>
          )}
        </Card>
      </div>

      {doc.extraction_error && <ErrorNote message={doc.extraction_error} />}

      {doc.summary && (
        <Card className="p-4">
          <CardHeader title="Summary / Metadata" />
          <p className="whitespace-pre-wrap pt-3 text-sm text-muted">{doc.summary}</p>
        </Card>
      )}
    </div>
  );
}

function Row({ k, v }: { k: string; v: string }) {
  return (
    <div className="flex justify-between gap-4">
      <dt className="text-muted">{k}</dt>
      <dd className="break-all text-right text-fg">{v}</dd>
    </div>
  );
}
