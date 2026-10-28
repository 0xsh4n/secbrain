"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { api } from "@/lib/api";
import type { DocumentOut, CollectionOut } from "@/lib/types";
import { Card, Badge, Input, Select, Spinner, Empty, ErrorNote, Button } from "@/components/ui";

interface Page {
  items: DocumentOut[];
  total: number;
  limit: number;
  offset: number;
}

export default function LibraryPage() {
  const [page, setPage] = useState<Page | null>(null);
  const [collections, setCollections] = useState<CollectionOut[]>([]);
  const [q, setQ] = useState("");
  const [status, setStatus] = useState("");
  const [sort, setSort] = useState("created_desc");
  const [offset, setOffset] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const limit = 20;

  const load = useCallback(() => {
    setLoading(true);
    const params = new URLSearchParams({ limit: String(limit), offset: String(offset), sort });
    if (q) params.set("q", q);
    if (status) params.set("status", status);
    api<Page>(`/documents?${params.toString()}`)
      .then(setPage)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, [q, status, sort, offset]);

  useEffect(() => {
    api<CollectionOut[]>("/collections").then(setCollections).catch(() => {});
  }, []);
  useEffect(() => {
    load();
  }, [load]);

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">Document Library</h1>
        <Link href="/ingest">
          <Button>+ Ingest</Button>
        </Link>
      </div>

      <div className="flex flex-wrap gap-2">
        <Input
          placeholder="Search titles…"
          value={q}
          onChange={(e) => {
            setOffset(0);
            setQ(e.target.value);
          }}
          className="max-w-xs"
        />
        <Select value={status} onChange={(e) => { setOffset(0); setStatus(e.target.value); }} className="max-w-[160px]">
          <option value="">All statuses</option>
          <option value="indexed">Indexed</option>
          <option value="processing">Processing</option>
          <option value="pending">Pending</option>
          <option value="failed">Failed</option>
        </Select>
        <Select value={sort} onChange={(e) => setSort(e.target.value)} className="max-w-[180px]">
          <option value="created_desc">Newest first</option>
          <option value="created_asc">Oldest first</option>
          <option value="title_asc">Title A–Z</option>
          <option value="title_desc">Title Z–A</option>
        </Select>
      </div>

      {error && <ErrorNote message={error} />}
      {loading ? (
        <Spinner />
      ) : !page || page.items.length === 0 ? (
        <Empty message="No documents match. Ingest some knowledge to get started." />
      ) : (
        <Card>
          <table className="w-full text-sm">
            <thead className="border-b border-border text-left text-xs uppercase tracking-wide text-muted">
              <tr>
                <th className="px-4 py-2">Title</th>
                <th className="px-4 py-2">Type</th>
                <th className="px-4 py-2">Status</th>
                <th className="px-4 py-2">Chunks</th>
                <th className="px-4 py-2">Collections</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {page.items.map((d) => (
                <tr key={d.id} className="hover:bg-surface-2">
                  <td className="px-4 py-2">
                    <Link href={`/documents/${d.id}`} className="text-accent hover:underline">
                      {d.title}
                    </Link>
                    {d.is_duplicate && <span className="ml-2 text-xs text-warn">(duplicate)</span>}
                  </td>
                  <td className="px-4 py-2 font-mono text-xs text-muted">{d.source_type}</td>
                  <td className="px-4 py-2"><Badge>{d.status}</Badge></td>
                  <td className="px-4 py-2 text-muted">{d.chunk_count}</td>
                  <td className="px-4 py-2 text-muted">{d.collection_ids.length}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}

      {page && page.total > limit && (
        <div className="flex items-center justify-between text-sm text-muted">
          <span>
            {offset + 1}–{Math.min(offset + limit, page.total)} of {page.total}
          </span>
          <div className="flex gap-2">
            <Button variant="ghost" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - limit))}>
              Prev
            </Button>
            <Button variant="ghost" disabled={offset + limit >= page.total} onClick={() => setOffset(offset + limit)}>
              Next
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
