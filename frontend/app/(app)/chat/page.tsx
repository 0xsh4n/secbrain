"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { api } from "@/lib/api";
import type { CollectionOut, ConversationOut, Evidence, MessageOut } from "@/lib/types";
import { Button, Input, ErrorNote, Spinner } from "@/components/ui";

interface ChatMsg {
  role: "user" | "assistant";
  content: string;
  citations: Evidence[];
}

export default function ChatPage() {
  const [collections, setCollections] = useState<CollectionOut[]>([]);
  const [selected, setSelected] = useState<string[]>([]);
  const [conversations, setConversations] = useState<ConversationOut[]>([]);
  const [convId, setConvId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMsg[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [loadingMessages, setLoadingMessages] = useState(false);
  const [error, setError] = useState("");
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const endRef = useRef<HTMLDivElement>(null);

  // Load collections & conversation history on mount
  useEffect(() => {
    api<CollectionOut[]>("/collections").then(setCollections).catch(() => {});
    loadConversations();
  }, []);

  // Auto-scroll when new messages arrive
  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, busy]);

  async function loadConversations() {
    try {
      const list = await api<ConversationOut[]>("/conversations");
      setConversations(list);
    } catch {
      // Ignore if unavailable
    }
  }

  function toggleCollection(id: string) {
    setSelected((s) => (s.includes(id) ? s.filter((x) => x !== id) : [...s, id]));
  }

  async function selectConversation(conv: ConversationOut) {
    if (conv.id === convId) return;
    setError("");
    setConvId(conv.id);
    setSelected(conv.collection_ids || []);
    setLoadingMessages(true);
    try {
      const msgs = await api<MessageOut[]>(`/conversations/${conv.id}/messages`);
      setMessages(
        msgs.map((m) => ({
          role: m.role as "user" | "assistant",
          content: m.content,
          citations: m.citations || [],
        }))
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load messages");
    } finally {
      setLoadingMessages(false);
    }
  }

  function startNewChat() {
    setConvId(null);
    setMessages([]);
    setError("");
  }

  async function deleteConversation(e: React.MouseEvent, id: string) {
    e.stopPropagation();
    try {
      await api(`/conversations/${id}`, { method: "DELETE" });
      setConversations((prev) => prev.filter((c) => c.id !== id));
      if (convId === id) {
        startNewChat();
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to delete conversation");
    }
  }

  async function send(e: React.FormEvent) {
    e.preventDefault();
    const message = input.trim();
    if (!message || busy) return;
    setError("");
    setBusy(true);
    setInput("");
    setMessages((m) => [...m, { role: "user", content: message, citations: [] }]);

    try {
      let id = convId;
      if (!id) {
        const title = message.length > 50 ? `${message.slice(0, 47)}…` : message;
        const newConv = await api<ConversationOut>("/conversations", {
          method: "POST",
          body: { title, collection_ids: selected },
        });
        id = newConv.id;
        setConvId(id);
        setConversations((prev) => [newConv, ...prev]);
      }

      const res = await api<{ content: string; citations: Evidence[] }>(
        `/conversations/${id}/messages`,
        { method: "POST", body: { message, collection_ids: selected, top_k: 4 } }
      );
      setMessages((m) => [
        ...m,
        { role: "assistant", content: res.content, citations: res.citations || [] },
      ]);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to generate answer");
    } finally {
      setBusy(false);
    }
  }

  function formatDate(iso: string | null) {
    if (!iso) return "";
    try {
      const d = new Date(iso);
      return d.toLocaleDateString(undefined, {
        month: "short",
        day: "numeric",
        hour: "2-digit",
        minute: "2-digit",
      });
    } catch {
      return "";
    }
  }

  const activeConv = conversations.find((c) => c.id === convId);

  return (
    <div className="flex h-[calc(100vh-3rem)] gap-3">
      {/* --- Chat History Sidebar --- */}
      <div
        className={`${
          sidebarOpen ? "flex" : "hidden"
        } w-72 flex-col rounded-lg border border-border bg-surface transition-all md:flex`}
      >
        <div className="flex items-center justify-between border-b border-border p-3">
          <span className="text-sm font-semibold text-fg">Chat History</span>
          <Button variant="ghost" className="text-xs" onClick={startNewChat}>
            + New Chat
          </Button>
        </div>

        <div className="flex-1 overflow-y-auto p-2 space-y-1">
          {conversations.length === 0 ? (
            <p className="p-4 text-center text-xs text-muted">No past conversations yet.</p>
          ) : (
            conversations.map((c) => {
              const active = c.id === convId;
              return (
                <div
                  key={c.id}
                  onClick={() => selectConversation(c)}
                  className={`group flex cursor-pointer items-center justify-between rounded-md px-3 py-2 text-xs transition-colors ${
                    active
                      ? "bg-accent-dim/20 text-accent font-medium"
                      : "text-muted hover:bg-surface-2 hover:text-fg"
                  }`}
                >
                  <div className="min-w-0 flex-1 pr-2">
                    <div className="truncate">{c.title || "Untitled conversation"}</div>
                    <div className="text-[10px] text-muted opacity-70">
                      {formatDate(c.updated_at || c.created_at)}
                    </div>
                  </div>
                  <button
                    onClick={(e) => deleteConversation(e, c.id)}
                    title="Delete conversation"
                    className="opacity-0 transition-opacity group-hover:opacity-100 text-muted hover:text-danger px-1"
                  >
                    ✕
                  </button>
                </div>
              );
            })
          )}
        </div>
      </div>

      {/* --- Main Chat Pane --- */}
      <div className="flex flex-1 flex-col space-y-3">
        {/* Top bar with collection filters & title */}
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <button
              onClick={() => setSidebarOpen((v) => !v)}
              className="rounded border border-border p-1.5 text-xs text-muted hover:text-fg md:hidden"
            >
              ☰ History
            </button>
            <h1 className="text-lg font-semibold truncate">
              {activeConv ? activeConv.title : "Security Knowledge Chat"}
            </h1>
          </div>
          <Button variant="ghost" className="text-xs md:hidden" onClick={startNewChat}>
            + New
          </Button>
        </div>

        {/* Collection Pills */}
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-xs text-muted">Collections:</span>
          {collections.map((c) => (
            <button
              key={c.id}
              onClick={() => toggleCollection(c.id)}
              className={`rounded-full border px-2.5 py-0.5 text-xs transition-colors ${
                selected.includes(c.id)
                  ? "border-accent bg-accent-dim/20 text-accent"
                  : "border-border text-muted hover:border-fg/40"
              }`}
            >
              {c.name}
            </button>
          ))}
          <span className="text-[11px] text-muted">
            {selected.length === 0 ? "(all accessible)" : `${selected.length} selected`}
          </span>
        </div>

        {/* Messages Container */}
        <div className="flex-1 space-y-4 overflow-y-auto rounded-lg border border-border bg-surface p-4">
          {loadingMessages ? (
            <Spinner />
          ) : messages.length === 0 ? (
            <div className="flex h-full flex-col items-center justify-center text-center text-muted">
              <p className="text-sm">
                Ask a security question grounded in your indexed documents and collections.
              </p>
              <p className="mt-1 text-xs opacity-70">
                Responses are synthesized with citations directly referencing your knowledge base.
              </p>
            </div>
          ) : (
            messages.map((m, i) => (
              <div key={i} className={m.role === "user" ? "text-right" : "text-left"}>
                <div
                  className={`inline-block max-w-[85%] whitespace-pre-wrap rounded-lg px-3.5 py-2.5 text-sm ${
                    m.role === "user"
                      ? "bg-accent-dim/25 text-fg text-left"
                      : "bg-surface-2 text-fg"
                  }`}
                >
                  {m.content}
                </div>

                {/* Evidence citations */}
                {m.citations && m.citations.length > 0 && (
                  <div className="mt-2 space-y-1.5 text-left max-w-[90%]">
                    <div className="text-[11px] uppercase tracking-wider text-muted font-semibold">
                      Cited Evidence ({m.citations.length})
                    </div>
                    {m.citations.map((ev, j) => (
                      <details
                        key={ev.chunk_id || j}
                        className="rounded border border-border bg-surface-2/80 px-2.5 py-1.5 text-xs"
                      >
                        <summary className="cursor-pointer text-accent hover:underline">
                          [E{j + 1}] {ev.title}{" "}
                          <span className="text-muted text-[10px]">
                            ({ev.retrieval_method}, score: {ev.score?.toFixed(2) ?? "0.00"})
                          </span>
                        </summary>
                        <p className="mt-1.5 whitespace-pre-wrap text-muted font-mono text-[11px] bg-surface p-2 rounded border border-border/50">
                          {ev.text}
                        </p>
                        {ev.document_id && (
                          <div className="mt-1">
                            <Link
                              href={`/documents/${ev.document_id}`}
                              className="text-accent text-[11px] hover:underline"
                            >
                              Open source document →
                            </Link>
                          </div>
                        )}
                      </details>
                    ))}
                  </div>
                )}
              </div>
            ))
          )}

          {busy && (
            <div className="flex items-center gap-2 text-xs text-muted">
              <div className="h-3 w-3 animate-spin rounded-full border-2 border-border border-t-accent" />
              <span>Retrieving evidence passages and synthesizing answer…</span>
            </div>
          )}
          <div ref={endRef} />
        </div>

        {/* Error notification */}
        {error && <ErrorNote message={error} />}

        {/* Input Bar */}
        <form onSubmit={send} className="flex gap-2">
          <Input
            placeholder="Ask about a CVE, vulnerability, security guideline, or note…"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            disabled={busy}
          />
          <Button type="submit" disabled={busy || !input.trim()}>
            Send
          </Button>
        </form>
      </div>
    </div>
  );
}
