"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api } from "@/lib/api";
import type { CollectionOut, SearchResponse, Evidence } from "@/lib/types";
import { Card, Button, Input, Spinner, Empty, ErrorNote, Badge } from "@/components/ui";

export default function SearchPage() {
  const [query, setQuery] = useState("");
  const [collections, setCollections] = useState<CollectionOut[]>([]);
  const [selected, setSelected] = useState<string[]>([]);
  const [res, setRes] = useState<SearchResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    api<CollectionOut[]>("/collections").then(setCollections).catch(() => {});
  }, []);

  function toggle(id: string) {
    setSelected((s) => (s.includes(id) ? s.filter((x) => x !== id) : [...s, id]));
  }

  async function run(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      const r = await api<SearchResponse>("/knowledge/search", {
        method: "POST",
        body: { query, collection_ids: selected, top_k: 10 },
      });
      setRes(r);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="space-y-4">
      <h1 className="text-xl font-semibold">Search Knowledge</h1>
      <form onSubmit={run} className="space-y-3">
        <div className="flex gap-2">
          <Input
            placeholder="e.g. How to prevent BOLA? CVE-2021-44228 fixed version?"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            required
          />
          <Button type="submit" disabled={loading}>
            Search
          </Button>
        </div>
        {collections.length > 0 && (
          <div className="flex flex-wrap gap-2">
            {collections.map((c) => (
              <button
                type="button"
                key={c.id}
                onClick={() => toggle(c.id)}
                className={`rounded-full border px-3 py-1 text-xs ${
                  selected.includes(c.id)
                    ? "border-accent bg-accent-dim/20 text-accent"
                    : "border-border text-muted"
                }`}
              >
                {c.name}
              </button>
            ))}
            <span className="self-center text-xs text-muted">
              {selected.length === 0 ? "(all accessible collections)" : `${selected.length} selected`}
            </span>
          </div>
        )}
      </form>

      {error && <ErrorNote message={error} />}
      {loading ? (
        <Spinner />
      ) : res ? (
        res.count === 0 ? (
          <Empty message="No matching evidence. The knowledge base has nothing relevant to this query." />
        ) : (
          <div className="space-y-3">
            <div className="text-sm text-muted">{res.count} evidence passages</div>
            {res.results.map((ev, i) => (
              <EvidenceCard key={ev.chunk_id} ev={ev} index={i + 1} />
            ))}
          </div>
        )
      ) : null}
    </div>
  );
}

function EvidenceCard({ ev, index }: { ev: Evidence; index: number }) {
  const [open, setOpen] = useState(false);
  return (
    <Card className="p-4">
      <div className="flex items-start justify-between gap-4">
        <div>
          <Link href={`/documents/${ev.document_id}`} className="font-medium text-accent hover:underline">
            [{index}] {ev.title}
          </Link>
          <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-muted">
            <Badge>{ev.retrieval_method}</Badge>
            <span>score {ev.score.toFixed(3)}</span>
            {ev.page_number && <span>p.{ev.page_number}</span>}
            {ev.section_heading && <span>§ {ev.section_heading}</span>}
            {ev.source_url && (
              <a href={ev.source_url} target="_blank" rel="noreferrer" className="text-accent hover:underline">
                source
              </a>
            )}
          </div>
        </div>
        <Button variant="ghost" onClick={() => setOpen(!open)}>
          {open ? "Hide" : "Show"}
        </Button>
      </div>
      <p className={`mt-3 whitespace-pre-wrap text-sm text-muted ${open ? "" : "line-clamp-3 max-h-20 overflow-hidden"}`}>
        {ev.text}
      </p>
    </Card>
  );
}
