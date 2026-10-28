"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { ApiKeyOut, CollectionOut } from "@/lib/types";
import { Card, CardHeader, Button, Input, Badge, Spinner, Empty, ErrorNote } from "@/components/ui";

export default function ApiKeysPage() {
  const [keys, setKeys] = useState<ApiKeyOut[]>([]);
  const [collections, setCollections] = useState<CollectionOut[]>([]);
  const [name, setName] = useState("");
  const [scoped, setScoped] = useState<string[]>([]);
  const [rate, setRate] = useState(60);
  const [newKey, setNewKey] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  function load() {
    api<ApiKeyOut[]>("/apikeys")
      .then(setKeys)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }
  useEffect(() => {
    load();
    api<CollectionOut[]>("/collections").then(setCollections).catch(() => {});
  }, []);

  async function create(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    try {
      const res = await api<ApiKeyOut>("/apikeys", {
        method: "POST",
        body: { name, scoped_collection_ids: scoped, rate_limit_per_minute: rate },
      });
      setNewKey(res.api_key || null);
      setName("");
      setScoped([]);
      load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed");
    }
  }

  async function revoke(id: string) {
    if (!confirm("Revoke this API key? Clients using it will immediately lose access.")) return;
    await api(`/apikeys/${id}`, { method: "DELETE" });
    load();
  }

  async function rotate(id: string) {
    const res = await api<ApiKeyOut>(`/apikeys/${id}/rotate`, { method: "POST" });
    setNewKey(res.api_key || null);
    load();
  }

  return (
    <div className="space-y-4">
      <h1 className="text-xl font-semibold">API Keys</h1>
      <p className="text-sm text-muted">
        Keys authenticate external AI applications and the MCP adapter. The raw key is shown once —
        store it securely. Only a hash is kept server-side.
      </p>
      {error && <ErrorNote message={error} />}

      {newKey && (
        <Card className="border-success/40 bg-success/10 p-4">
          <div className="text-sm font-medium text-success">New API key (copy now — shown once):</div>
          <code className="mt-2 block break-all rounded bg-bg p-2 font-mono text-xs">{newKey}</code>
          <button className="mt-2 text-xs text-muted hover:text-fg" onClick={() => setNewKey(null)}>
            dismiss
          </button>
        </Card>
      )}

      <Card className="p-4">
        <CardHeader title="Create key" />
        <form onSubmit={create} className="space-y-3 pt-3">
          <Input placeholder="Key name" value={name} onChange={(e) => setName(e.target.value)} />
          <div>
            <div className="mb-1 text-xs text-muted">Scope to collections (empty = all accessible):</div>
            <div className="flex flex-wrap gap-2">
              {collections.map((c) => (
                <button
                  type="button"
                  key={c.id}
                  onClick={() => setScoped((s) => (s.includes(c.id) ? s.filter((x) => x !== c.id) : [...s, c.id]))}
                  className={`rounded-full border px-3 py-1 text-xs ${
                    scoped.includes(c.id) ? "border-accent bg-accent-dim/20 text-accent" : "border-border text-muted"
                  }`}
                >
                  {c.name}
                </button>
              ))}
            </div>
          </div>
          <div className="flex items-center gap-2">
            <label className="text-sm text-muted">Rate limit / min</label>
            <Input
              type="number"
              value={rate}
              onChange={(e) => setRate(Number(e.target.value))}
              className="max-w-[120px]"
            />
          </div>
          <Button type="submit">Create key</Button>
        </form>
      </Card>

      {loading ? (
        <Spinner />
      ) : keys.length === 0 ? (
        <Empty message="No API keys yet." />
      ) : (
        <Card className="overflow-hidden">
          <div className="overflow-x-auto">
          <table className="w-full min-w-[42rem] text-sm">
            <thead className="border-b border-border text-left text-xs uppercase tracking-wide text-muted">
              <tr>
                <th className="px-4 py-2">Name</th>
                <th className="px-4 py-2">Prefix</th>
                <th className="px-4 py-2">Status</th>
                <th className="px-4 py-2">Uses</th>
                <th className="px-4 py-2">Scope</th>
                <th className="px-4 py-2" />
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {keys.map((k) => (
                <tr key={k.id}>
                  <td className="px-4 py-2">{k.name || "—"}</td>
                  <td className="px-4 py-2 font-mono text-xs">{k.prefix}…</td>
                  <td className="px-4 py-2">
                    <Badge>{k.is_active ? "indexed" : "CANCELLED"}</Badge>
                  </td>
                  <td className="px-4 py-2 text-muted">{k.usage_count}</td>
                  <td className="px-4 py-2 text-muted">
                    {k.scoped_collection_ids.length === 0 ? "all" : `${k.scoped_collection_ids.length} coll.`}
                  </td>
                  <td className="px-4 py-2 text-right">
                    {k.is_active && (
                      <>
                        <button className="mr-3 text-xs text-accent hover:underline" onClick={() => rotate(k.id)}>
                          rotate
                        </button>
                        <button className="text-xs text-danger hover:underline" onClick={() => revoke(k.id)}>
                          revoke
                        </button>
                      </>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          </div>
        </Card>
      )}
    </div>
  );
}
