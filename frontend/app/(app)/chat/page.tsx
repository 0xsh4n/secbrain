"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { api } from "@/lib/api";
import type { CollectionOut, Evidence } from "@/lib/types";
import { Card, Button, Input, Badge, ErrorNote } from "@/components/ui";

interface ChatMsg {
  role: "user" | "assistant";
  content: string;
  citations: Evidence[];
}

export default function ChatPage() {
  const [collections, setCollections] = useState<CollectionOut[]>([]);
  const [selected, setSelected] = useState<string[]>([]);
  const [convId, setConvId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMsg[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    api<CollectionOut[]>("/collections").then(setCollections).catch(() => {});
  }, []);
  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  function toggle(id: string) {
    setSelected((s) => (s.includes(id) ? s.filter((x) => x !== id) : [...s, id]));
  }

  async function send(e: React.FormEvent) {
    e.preventDefault();
    const message = input.trim();
    if (!message) return;
    setError("");
    setBusy(true);
    setInput("");
    setMessages((m) => [...m, { role: "user", content: message, citations: [] }]);
    try {
      let id = convId;
      if (!id) {
        const conv = await api<{ id: string }>("/conversations", {
          method: "POST",
          body: { title: message.slice(0, 60), collection_ids: selected },
        });
        id = conv.id;
        setConvId(id);
      }
      const res = await api<{ content: string; citations: Evidence[] }>(
        `/conversations/${id}/messages`,
        { method: "POST", body: { message, collection_ids: selected, top_k: 8 } }
      );
      setMessages((m) => [...m, { role: "assistant", content: res.content, citations: res.citations }]);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex h-[calc(100vh-3rem)] flex-col space-y-3">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">Security Knowledge Chat</h1>
      </div>
      <div className="flex flex-wrap gap-2">
        {collections.map((c) => (
          <button
            key={c.id}
            onClick={() => toggle(c.id)}
            className={`rounded-full border px-3 py-1 text-xs ${
              selected.includes(c.id) ? "border-accent bg-accent-dim/20 text-accent" : "border-border text-muted"
            }`}
          >
            {c.name}
          </button>
        ))}
        <span className="self-center text-xs text-muted">
          {selected.length === 0 ? "(all accessible collections)" : `${selected.length} selected`}
        </span>
      </div>

      <div className="flex-1 space-y-4 overflow-y-auto rounded-lg border border-border bg-surface p-4">
        {messages.length === 0 && (
          <p className="py-8 text-center text-sm text-muted">
            Ask a question grounded in your indexed knowledge. Answers cite the evidence used.
          </p>
        )}
        {messages.map((m, i) => (
          <div key={i} className={m.role === "user" ? "text-right" : ""}>
            <div
              className={`inline-block max-w-[85%] whitespace-pre-wrap rounded-lg px-3 py-2 text-sm ${
                m.role === "user" ? "bg-accent-dim/20 text-fg" : "bg-surface-2 text-fg"
              }`}
            >
              {m.content}
            </div>
            {m.citations.length > 0 && (
              <div className="mt-2 space-y-1 text-left">
                <div className="text-xs uppercase tracking-wide text-muted">Evidence</div>
                {m.citations.map((ev, j) => (
                  <details key={ev.chunk_id} className="rounded border border-border bg-surface-2 px-2 py-1 text-xs">
                    <summary className="cursor-pointer text-accent">
                      [E{j + 1}] {ev.title}{" "}
                      <span className="text-muted">({ev.retrieval_method}, {ev.score.toFixed(2)})</span>
                    </summary>
                    <p className="mt-1 whitespace-pre-wrap text-muted">{ev.text}</p>
                    <Link href={`/documents/${ev.document_id}`} className="text-accent hover:underline">
                      open document →
                    </Link>
                  </details>
                ))}
              </div>
            )}
          </div>
        ))}
        {busy && <div className="text-sm text-muted">Retrieving evidence and generating…</div>}
        <div ref={endRef} />
      </div>

      {error && <ErrorNote message={error} />}
      <form onSubmit={send} className="flex gap-2">
        <Input
          placeholder="Ask about a vulnerability, technique, or your notes…"
          value={input}
          onChange={(e) => setInput(e.target.value)}
        />
        <Button type="submit" disabled={busy}>
          Send
        </Button>
      </form>
    </div>
  );
}
