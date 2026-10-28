"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { api, apiUrl, getToken } from "@/lib/api";
import type { CollectionOut, JobOut } from "@/lib/types";
import { Card, CardHeader, Button, Input, Textarea, Select, Badge, Empty, ErrorNote } from "@/components/ui";

type Mode = "text" | "url" | "file";

export default function IngestPage() {
  const [mode, setMode] = useState<Mode>("text");
  const [collections, setCollections] = useState<CollectionOut[]>([]);
  const [collectionId, setCollectionId] = useState("");
  const [title, setTitle] = useState("");
  const [text, setText] = useState("");
  const [url, setUrl] = useState("");
  const [jobs, setJobs] = useState<JobOut[]>([]);
  const [error, setError] = useState("");
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  const loadJobs = useCallback(() => {
    api<JobOut[]>("/dashboard/jobs").then(setJobs).catch(() => {});
  }, []);

  useEffect(() => {
    api<CollectionOut[]>("/collections").then(setCollections).catch(() => {});
    loadJobs();
    const t = setInterval(loadJobs, 3000);
    return () => clearInterval(t);
  }, [loadJobs]);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setMsg("");
    setBusy(true);
    try {
      const collection_ids = collectionId ? [collectionId] : [];
      if (mode === "text") {
        await api("/documents/text", { method: "POST", body: { title, text, collection_ids } });
      } else if (mode === "url") {
        await api("/documents/url", { method: "POST", body: { url, title, collection_ids } });
      } else {
        const file = fileRef.current?.files?.[0];
        if (!file) throw new Error("Choose a file");
        const form = new FormData();
        form.append("file", file);
        form.append("title", title);
        form.append("collection_ids", collection_ids.join(","));
        const res = await fetch(`${apiUrl}/api/v1/documents/upload`, {
          method: "POST",
          headers: { Authorization: `Bearer ${getToken()}` },
          body: form,
        });
        if (!res.ok) throw new Error((await res.json()).detail || "Upload failed");
      }
      setMsg("Document queued for ingestion.");
      setText("");
      setUrl("");
      setTitle("");
      if (fileRef.current) fileRef.current.value = "";
      setTimeout(loadJobs, 500);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-6">
      <h1 className="text-xl font-semibold">Ingestion Queue</h1>

      <Card className="p-4">
        <div className="mb-4 flex flex-wrap gap-2">
          {(["text", "url", "file"] as Mode[]).map((m) => (
            <button
              key={m}
              onClick={() => setMode(m)}
              className={`rounded-md px-3 py-1.5 text-sm ${mode === m ? "bg-accent-dim/20 text-accent" : "bg-surface-2 text-muted"}`}
            >
              {m === "text" ? "Paste text" : m === "url" ? "From URL" : "Upload file"}
            </button>
          ))}
        </div>
        <form onSubmit={submit} className="space-y-3">
          <Input placeholder="Title (optional)" value={title} onChange={(e) => setTitle(e.target.value)} />
          {mode === "text" && (
            <Textarea
              placeholder="Paste security notes, findings, article text…"
              rows={8}
              value={text}
              onChange={(e) => setText(e.target.value)}
              required
            />
          )}
          {mode === "url" && (
            <Input
              placeholder="https://example.com/security-article"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              required
            />
          )}
          {mode === "file" && (
            <input
              ref={fileRef}
              type="file"
              accept=".pdf,.txt,.md,.markdown,.html,.htm,.docx"
              className="block w-full text-sm text-muted file:mr-3 file:rounded-md file:border-0 file:bg-surface-2 file:px-3 file:py-2 file:text-fg"
            />
          )}
          <Select value={collectionId} onChange={(e) => setCollectionId(e.target.value)}>
            <option value="">(no collection)</option>
            {collections.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}
              </option>
            ))}
          </Select>
          {error && <ErrorNote message={error} />}
          {msg && <div className="text-sm text-success">{msg}</div>}
          <Button type="submit" disabled={busy}>
            {busy ? "Submitting…" : "Ingest"}
          </Button>
          {mode === "url" && (
            <p className="text-xs text-muted">
              URLs are fetched through an SSRF-protected client. Private/internal addresses are blocked.
              Paywalled or authentication-gated content is not bypassed — use paste text instead.
            </p>
          )}
        </form>
      </Card>

      <Card>
        <CardHeader title="Recent Jobs" action={<Button variant="ghost" onClick={loadJobs}>Refresh</Button>} />
        <div className="divide-y divide-border">
          {jobs.length === 0 && <Empty message="No ingestion jobs yet" />}
          {jobs.map((j) => (
            <div key={j.id} className="flex flex-col gap-2 px-4 py-3 text-sm sm:flex-row sm:items-center sm:justify-between">
              <a href={`/documents/${j.document_id}`} className="w-fit font-mono text-xs text-accent hover:underline">
                {j.document_id.slice(0, 12)}…
              </a>
              <span className="min-w-0 break-words text-xs text-muted sm:flex-1 sm:px-4 sm:text-sm">{j.detail || j.error}</span>
              <span className="w-fit"><Badge>{j.state}</Badge></span>
            </div>
          ))}
        </div>
      </Card>
    </div>
  );
}
