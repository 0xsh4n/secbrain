"use client";

import { useEffect, useRef, useState } from "react";
import { api, apiUrl, getToken } from "@/lib/api";
import type { CollectionOut, ConversationOut, MessageOut } from "@/lib/types";
import { Button, Input, ErrorNote, Spinner } from "@/components/ui";
import { MarkdownMessage } from "./MarkdownMessage";
import { speakHackerGirl, stopSpeaking, StreamingSpeech, getProcessedMicrophone } from "@/lib/voice";
import { VoiceCallOverlay } from "./VoiceCallOverlay";

interface ChatMsg {
  role: "user" | "assistant";
  content: string;
}

async function consumeVoiceStream(
  response: Response,
  onToken: (token: string) => void,
): Promise<string> {
  if (!response.ok) {
    const body = await response.text();
    let detail = body;
    try {
      const parsed = JSON.parse(body);
      detail = parsed.detail || body;
    } catch { /* Keep the plain-text response. */ }
    throw new Error(detail || `Request failed (${response.status})`);
  }
  const reader = response.body?.getReader();
  if (!reader) throw new Error("The backend did not open a streaming response.");
  const decoder = new TextDecoder();
  let buffer = "";
  let answer = "";
  let complete = false;
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const blocks = buffer.split("\n\n");
    buffer = blocks.pop() || "";
    for (const block of blocks) {
      let type = "";
      let data = "";
      for (const line of block.split("\n")) {
        if (line.startsWith("event: ")) type = line.slice(7).trim();
        else if (line.startsWith("data: ")) data = line.slice(6).trim();
      }
      if (!data && type !== "done") continue;
      if (type === "token") {
        const token = JSON.parse(data).text || "";
        answer += token;
        onToken(token);
      } else if (type === "error") {
        throw new Error(JSON.parse(data).detail || "The model stopped while generating.");
      } else if (type === "done") {
        complete = true;
      }
    }
  }
  if (!complete) throw new Error("The connection ended before the response finished. Retry your message.");
  return answer;
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
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [responseLength, setResponseLength] = useState<"balanced" | "detailed" | "extended">("extended");
  const [thinking, setThinking] = useState(false);
  const [webSearch, setWebSearch] = useState(false);
  const [streamStatus, setStreamStatus] = useState("");

  // --- Voice & Call State ---
  const [isCallOpen, setIsCallOpen] = useState(false);
  const [voiceEnabled, setVoiceEnabled] = useState(false);
  const [isListening, setIsListening] = useState(false);
  const [isSpeaking, setIsSpeaking] = useState(false);
  const recognitionRef = useRef<unknown>(null);
  const recognitionHandledRef = useRef(false);
  const streamingSpeechRef = useRef<StreamingSpeech | null>(null);
  const [transcriptPreview, setTranscriptPreview] = useState("");

  const endRef = useRef<HTMLDivElement>(null);

  // Load collections & conversation history on mount
  useEffect(() => {
    api<CollectionOut[]>("/collections").then(setCollections).catch(() => {});
    loadConversations();

    // Preload speech synthesis voices
    if (typeof window !== "undefined" && "speechSynthesis" in window) {
      window.speechSynthesis.getVoices();
      window.speechSynthesis.onvoiceschanged = () => {
        window.speechSynthesis.getVoices();
      };
    }

    return () => {
      if (recognitionRef.current) {
        (recognitionRef.current as { abort?: () => void }).abort?.();
        recognitionRef.current = null;
      }
      streamingSpeechRef.current?.cancel();
      stopSpeaking();
    };
  }, []);

  // Auto-scroll when new messages arrive or stream updates
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
    setSidebarOpen(false);
    if (conv.id === convId) return;
    stopSpeaking();
    streamingSpeechRef.current?.cancel();
    setIsSpeaking(false);
    setError("");
    setStreamStatus("");
    setConvId(conv.id);
    setSelected(conv.collection_ids || []);
    setLoadingMessages(true);
    try {
      const msgs = await api<MessageOut[]>(`/conversations/${conv.id}/messages`);
      setMessages(
        msgs.map((m) => ({
          role: m.role as "user" | "assistant",
          content: m.content,
        }))
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load messages");
    } finally {
      setLoadingMessages(false);
    }
  }

  function startNewChat() {
    stopSpeaking();
    streamingSpeechRef.current?.cancel();
    setIsSpeaking(false);
    setConvId(null);
    setMessages([]);
    setError("");
    setSidebarOpen(false);
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

  // --- Real-time SSE Streaming Send ---
  async function send(e?: React.FormEvent, customMsg?: string) {
    if (e) e.preventDefault();
    const message = (customMsg !== undefined ? customMsg : input).trim();
    if (!message || busy) return;

    stopSpeaking();
    streamingSpeechRef.current?.cancel();
    setIsSpeaking(false);
    setError("");
    setStreamStatus("");
    setBusy(true);
    setInput("");
    setTranscriptPreview("");
    const speechQueue = voiceEnabled
      ? new StreamingSpeech(() => setIsSpeaking(false))
      : null;
    streamingSpeechRef.current = speechQueue;
    if (speechQueue) setIsSpeaking(true);

    // Add user message
    setMessages((m) => [...m, { role: "user", content: message }]);

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

      // Prepare empty placeholder for incoming assistant stream
      setMessages((m) => [...m, { role: "assistant", content: "" }]);

      // Call streaming SSE endpoint
      let response: Response;
      try {
        response = await fetch(`${apiUrl}/api/v1/conversations/${id}/stream`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${getToken()}`,
          },
          body: JSON.stringify({ message, collection_ids: selected, top_k: 8, response_length: responseLength, thinking, web_search: webSearch }),
        });
      } catch (cause) {
        const detail = cause instanceof Error ? cause.message : "Network request failed";
        throw new Error(`Can't reach the SecBrain backend at ${apiUrl}. Check that it is running and that NEXT_PUBLIC_API_URL is correct. (${detail})`);
      }

      if (!response.ok) {
        const detail = await response.text();
        let message = detail;
        try {
          const parsed = JSON.parse(detail);
          message = parsed.detail || detail;
        } catch {
          // Response may be plain text.
        }
        throw new Error(message || `Generation failed (${response.status})`);
      }

      const reader = response.body?.getReader();
      const decoder = new TextDecoder();
      let streamedContent = "";
      let streamCompleted = false;

      if (!reader) {
        throw new Error("The backend did not open a streaming response. Check the API URL and backend logs.");
      }
      let buffer = "";
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n\n");
        buffer = lines.pop() || "";

        for (const block of lines) {
          const lineArr = block.split("\n");
          let eventType = "";
          let dataStr = "";

          for (const l of lineArr) {
            if (l.startsWith("event: ")) eventType = l.slice(7).trim();
            if (l.startsWith("data: ")) dataStr = l.slice(6).trim();
          }

          if (eventType === "token" && dataStr) {
            setStreamStatus("");
            try {
              const parsed = JSON.parse(dataStr);
              const token = parsed.text || "";
              streamedContent += token;
              speechQueue?.push(token);
              setMessages((prev) => {
                const updated = [...prev];
                const last = updated[updated.length - 1];
                if (last && last.role === "assistant") last.content = streamedContent;
                return updated;
              });
            } catch {
              // Ignore malformed token events and continue reading the stream.
            }
          } else if (eventType === "error" && dataStr) {
            let detail = "Stream encountered an error";
            try {
              const parsed = JSON.parse(dataStr);
              detail = parsed.detail || "Stream error";
            } catch {
              // Keep the fallback message.
            }
            setError(detail);
            throw new Error(detail);
          } else if (eventType === "status" && dataStr) {
            try { setStreamStatus(JSON.parse(dataStr).text || "Working…"); } catch { setStreamStatus("Working…"); }
          } else if (eventType === "notice" && dataStr) {
            try { setStreamStatus(JSON.parse(dataStr).text || "Continuing without web results."); } catch { setStreamStatus("Continuing without web results."); }
          } else if (eventType === "done") {
            streamCompleted = true;
          }
        }
      }
      if (!streamCompleted) throw new Error("The connection ended before the response finished. Retry your message.");
      speechQueue?.finish();
    } catch (err) {
      speechQueue?.cancel();
      stopSpeaking();
      setIsSpeaking(false);
      setError(err instanceof Error ? err.message : "Failed to generate answer");
      setMessages((prev) => {
        const last = prev[prev.length - 1];
        return last?.role === "assistant" && !last.content
          ? prev.slice(0, -1)
          : prev;
      });
    } finally {
      setBusy(false);
      setStreamStatus("");
    }
  }

  // --- Voice Call Handler (Used when in Live Call Modal) ---
  async function handleVoiceCallMessage(message: string, onToken?: (token: string) => void): Promise<string> {
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

    setMessages((m) => [...m, { role: "user", content: message }]);
    setMessages((m) => [...m, { role: "assistant", content: "" }]);
    let content = "";
    try {
      let response: Response;
      try {
        response = await fetch(`${apiUrl}/api/v1/conversations/${id}/stream`, {
          method: "POST",
          headers: { "Content-Type": "application/json", Authorization: `Bearer ${getToken()}` },
          body: JSON.stringify({ message, collection_ids: selected, top_k: 8, response_length: responseLength, thinking, web_search: webSearch }),
        });
      } catch {
        throw new Error(`Can't reach SecBrain at ${apiUrl}. Check the backend and NEXT_PUBLIC_API_URL.`);
      }
      content = await consumeVoiceStream(
        response,
        (token) => {
          onToken?.(token);
          content += token;
          setMessages((prev) => prev.map((item, index) => index === prev.length - 1
            ? { ...item, content }
            : item));
        }
      );
      return content;
    } catch (cause) {
      setMessages((prev) => prev[prev.length - 1]?.role === "assistant" && !prev[prev.length - 1].content
        ? prev.slice(0, -1)
        : prev);
      throw cause;
    }
  }

  // --- Voice Input (Speech to Text) ---
  async function toggleListening() {
    if (isListening) {
      if (recognitionRef.current) {
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        const recognition = recognitionRef.current as any;
        recognitionRef.current = null;
        recognition.stop();
      }
      setIsListening(false);
      return;
    }

    if (typeof window === "undefined") return;

    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const SpeechRecognition = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;

    if (!SpeechRecognition) {
      setError("Speech recognition is not supported in this browser. Try Chrome, Edge, or Safari.");
      return;
    }

    try {
      // Explicitly prompt for mic permission
      const permissionStream = await getProcessedMicrophone();
      permissionStream.getTracks().forEach((track) => track.stop());
    } catch {
      setError("Microphone permission denied. Please allow microphone access in your browser address bar.");
      return;
    }

    stopSpeaking();
    setIsSpeaking(false);
    setError("");

    try {
      const recognition = new SpeechRecognition();
      recognitionHandledRef.current = false;
      recognition.lang = "en-IN";
      recognition.interimResults = true;
      recognition.maxAlternatives = 1;

      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      recognition.onresult = (event: any) => {
        if (recognitionRef.current !== recognition) return;
        if (recognitionHandledRef.current) return;
        let finalTranscript = "";
        let interimTranscript = "";
        let hasNewFinal = false;
        for (let i = 0; i < event.results.length; i++) {
          const result = event.results[i];
          if (result.isFinal) {
            finalTranscript += `${result[0].transcript} `;
            if (i >= event.resultIndex) hasNewFinal = true;
          }
          else interimTranscript += result[0].transcript;
        }
        if (interimTranscript) setTranscriptPreview(interimTranscript);
        if (hasNewFinal && finalTranscript.trim()) {
          recognitionHandledRef.current = true;
          setTranscriptPreview(finalTranscript.trim());
          setIsListening(false);
          send(undefined, finalTranscript.trim());
        }
      };

      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      recognition.onerror = (e: any) => {
        if (recognitionRef.current !== recognition) return;
        setIsListening(false);
        if (e.error === "not-allowed") {
          setError("Microphone blocked. Please allow mic access in your browser settings.");
        } else if (e.error === "no-speech") {
          setTranscriptPreview("");
        } else if (e.error === "network") {
          setError("Your browser's speech recognition service is unavailable. Check your connection, or use Live Call's text input for now.");
        } else {
          setError(`Voice input note: ${e.error}. You can also use the "📞 Live Call" button.`);
        }
      };

      recognition.onend = () => {
        if (recognitionRef.current !== recognition) return;
        setIsListening(false);
        recognitionRef.current = null;
      };

      recognitionRef.current = recognition;
      recognition.start();
      setIsListening(true);
    } catch (cause) {
      setIsListening(false);
      setError(cause instanceof Error ? cause.message : "Could not start speech recognition. Check microphone permissions.");
    }
  }

  function handlePlayVoice(content: string) {
    if (isSpeaking) {
      streamingSpeechRef.current?.cancel();
      stopSpeaking();
      setIsSpeaking(false);
    } else {
      setIsSpeaking(true);
      speakHackerGirl(content, () => setIsSpeaking(false));
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
    <div className="flex h-[calc(100dvh-7rem)] min-h-[25rem] gap-3 md:h-[calc(100dvh-3.5rem)] md:min-h-0">
      {/* Live Voice Call Fullscreen Modal */}
      <VoiceCallOverlay
        isOpen={isCallOpen}
        onClose={() => setIsCallOpen(false)}
        onSendMessage={handleVoiceCallMessage}
      />

      {/* --- Chat History Sidebar --- */}
      {sidebarOpen && <button aria-label="Close chat history" onClick={() => setSidebarOpen(false)} className="fixed inset-0 z-40 bg-black/55 md:hidden" />}
      <div className={`${sidebarOpen
        ? "fixed inset-y-3 left-3 z-50 flex w-[min(20rem,calc(100vw-1.5rem))] flex-col shadow-2xl md:relative md:inset-auto md:z-auto md:w-72 md:shadow-none"
        : "hidden md:flex md:w-72"} shrink-0 flex-col rounded-2xl border border-border bg-surface transition-all`}>
        <div className="flex items-center justify-between gap-2 border-b border-border p-3">
          <span className="text-sm font-semibold text-fg">Chat History</span>
          <Button variant="ghost" className="whitespace-nowrap text-xs" onClick={startNewChat}>
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
      <div className="flex min-h-0 min-w-0 flex-1 flex-col gap-3">
        {/* Top bar with voice call, voice toggle & title */}
        <div className="flex min-h-10 items-center justify-between gap-2">
          <div className="flex min-w-0 items-center gap-2">
            <button
              onClick={() => setSidebarOpen((v) => !v)}
              aria-label="Open chat history"
              className="shrink-0 rounded-xl border border-border bg-surface px-2.5 py-2 text-xs text-muted hover:text-fg md:hidden"
            >
              ☰
            </button>
            <h1 className="truncate text-base font-semibold sm:text-lg">
              {activeConv ? activeConv.title : "Nyx · SecBrain"}
            </h1>
          </div>

          <div className="flex items-center gap-2">
            {/* Live Interactive Voice Call Button */}
            <button
              onClick={() => setIsCallOpen(true)}
              title="Launch Live Hands-Free Cyber Call"
              className="flex shrink-0 items-center gap-1.5 rounded-full border border-accent/40 bg-accent/10 px-2.5 py-2 text-[11px] font-semibold text-accent transition hover:bg-accent/20 sm:gap-2 sm:px-3.5 sm:py-1 sm:text-xs"
            >
              <span className="relative flex h-2 w-2">
                <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-accent opacity-75" />
                <span className="relative inline-flex h-2 w-2 rounded-full bg-accent" />
              </span>
              <span className="sm:hidden">Call</span><span className="hidden sm:inline">📞 Live Call</span>
            </button>

            {/* Cyber Voice Audio Toggle */}
            <button
              onClick={() => {
                const next = !voiceEnabled;
                setVoiceEnabled(next);
                if (!next) {
                  streamingSpeechRef.current?.cancel();
                  stopSpeaking();
                  setIsSpeaking(false);
                }
              }}
              title="Toggle Cyberpunk Hacker Voice for text replies"
              className={`hidden sm:flex items-center gap-1.5 rounded-full border px-3 py-1 text-xs transition-colors ${
                voiceEnabled
                  ? "border-accent bg-accent/15 text-accent font-medium shadow-[0_0_10px_rgba(34,211,238,0.25)]"
                  : "border-border text-muted hover:text-fg"
              }`}
            >
              <span className={`inline-block h-2 w-2 rounded-full ${voiceEnabled ? "bg-accent animate-pulse" : "bg-muted"}`} />
              <span>🔊 Voice: {voiceEnabled ? "ON" : "OFF"}</span>
            </button>

            <Button variant="ghost" className="shrink-0 px-2.5 text-xs md:hidden" onClick={startNewChat}>
              + New
            </Button>
          </div>
        </div>

        {/* Collection Pills */}
        <div className="flex min-w-0 items-center gap-2 overflow-x-auto pb-1">
          <span className="shrink-0 text-xs text-muted">Scope</span>
          {collections.map((c) => (
            <button key={c.id} onClick={() => toggleCollection(c.id)}
              className={`shrink-0 rounded-full border px-2.5 py-1 text-xs transition-colors ${selected.includes(c.id) ? "border-accent bg-accent-dim/20 text-accent" : "border-border text-muted hover:border-fg/40"}`}>
              {c.name}
            </button>
          ))}
          <span className="shrink-0 text-[11px] text-muted">{selected.length === 0 ? "All" : `${selected.length} selected`}</span>
        </div>

        <details className="group rounded-xl border border-border bg-surface px-3 py-2">
          <summary className="flex cursor-pointer list-none flex-wrap items-center justify-between gap-2 text-xs">
            <span className="font-medium text-fg">Advanced response controls</span>
            <span className="flex flex-wrap justify-end gap-1.5 text-[10px]">
              <span className="rounded-full bg-surface-2 px-2 py-1 text-muted">{responseLength}</span>
              <span className={`rounded-full px-2 py-1 ${thinking ? "bg-accent/15 text-accent" : "bg-surface-2 text-muted"}`}>Thinking {thinking ? "on" : "off"}</span>
              <span className={`rounded-full px-2 py-1 ${webSearch ? "bg-accent/15 text-accent" : "bg-surface-2 text-muted"}`}>Web {webSearch ? "on" : "off"}</span>
            </span>
          </summary>
          <div className="mt-3 grid gap-3 border-t border-border pt-3 sm:grid-cols-2 lg:grid-cols-3">
            <div>
              <p className="mb-1.5 text-[11px] font-medium text-muted">Answer length</p>
              <div className="flex flex-wrap gap-1">
                {(["balanced", "detailed", "extended"] as const).map((level) => (
                  <button key={level} type="button" onClick={() => setResponseLength(level)} aria-pressed={responseLength === level}
                    className={`rounded-md border px-2 py-1 text-[11px] capitalize ${responseLength === level ? "border-accent bg-accent/10 text-accent" : "border-border text-muted hover:text-fg"}`}>
                    {level}
                  </button>
                ))}
              </div>
              <p className="mt-1 text-[10px] text-muted">Extended gives numbered lists more room.</p>
            </div>
            <div>
              <p className="mb-1.5 text-[11px] font-medium text-muted">Reasoning</p>
              <button type="button" onClick={() => setThinking((value) => !value)} aria-pressed={thinking}
                title="Thinking support depends on the selected model."
                className={`rounded-md border px-2.5 py-1 text-xs ${thinking ? "border-accent bg-accent/10 text-accent" : "border-border text-muted hover:text-fg"}`}>
                {thinking ? "Thinking on" : "Thinking off"}
              </button>
              <p className="mt-1 text-[10px] text-muted">Uses native Thinking when supported; otherwise it falls back to reasoning-focused instructions.</p>
            </div>
            <div>
              <p className="mb-1.5 text-[11px] font-medium text-muted">Live web sources</p>
              <button type="button" onClick={() => setWebSearch((value) => !value)} aria-pressed={webSearch}
                className={`rounded-md border px-2.5 py-1 text-xs ${webSearch ? "border-accent bg-accent/10 text-accent" : "border-border text-muted hover:text-fg"}`}>
                {webSearch ? "Web search on" : "Web search off"}
              </button>
              <p className="mt-1 text-[10px] text-muted">When on, the question is sent to DuckDuckGo.</p>
            </div>
          </div>
        </details>

        {/* Messages Container */}
        <div className="min-h-0 flex-1 space-y-4 overflow-y-auto overscroll-contain rounded-2xl border border-border/80 bg-surface/75 p-3 sm:p-4">
          {loadingMessages ? (
            <Spinner />
          ) : messages.length === 0 ? (
            <div className="flex h-full flex-col items-center justify-center text-center text-muted space-y-3">
              <div className="p-3 rounded-full bg-accent/10 border border-accent/20">
                <span className="text-2xl">👩‍💻</span>
              </div>
              <div>
                <p className="text-sm font-medium text-fg">SecBrain Cyber Copilot</p>
                <p className="mt-1 text-xs text-muted max-w-md">
                  Click <strong>&quot;📞 Live Call&quot;</strong> above to talk with your AI hacker operator, or type technical questions and requests below.
                </p>
              </div>
            </div>
          ) : (
            messages.map((m, i) => (
              <div key={i} className={m.role === "user" ? "text-right" : "text-left"}>
                <div
                  className={`relative inline-block max-w-[95%] break-words rounded-2xl px-3.5 py-3 text-sm sm:max-w-[88%] sm:px-4 ${
                    m.role === "user"
                      ? "bg-accent-dim/25 text-fg text-left whitespace-pre-wrap"
                      : "w-full bg-surface-2/80 text-left text-fg"
                  }`}
                >
                  {m.role === "user" ? (
                    m.content
                  ) : (
                    <>
                      <div className="flex items-center justify-between border-b border-border/40 pb-1.5 mb-2 text-xs text-muted">
                        <span className="flex items-center gap-1 font-mono text-[11px] text-accent">
                          ⚡ Nyx · SecBrain
                        </span>
                        {m.content && (
                          <div className="flex items-center gap-1">
                            <button onClick={() => void navigator.clipboard.writeText(m.content)} className="rounded px-2 py-0.5 text-[11px] text-muted hover:text-accent transition" title="Copy response">Copy</button>
                            <button onClick={() => handlePlayVoice(m.content)} className="rounded px-2 py-0.5 text-[11px] text-muted hover:text-accent transition" title="Read response aloud">
                              {isSpeaking ? "⏹ Stop" : "🔊 Listen"}
                            </button>
                          </div>
                        )}
                      </div>
                      <MarkdownMessage content={m.content} />
                    </>
                  )}
                </div>

              </div>
            ))
          )}

          {busy && (
            <div className="flex items-center gap-2 text-xs text-muted">
              <div className="h-3 w-3 animate-spin rounded-full border-2 border-border border-t-accent" />
              <span>{streamStatus || (thinking ? "Thinking through your request…" : "Generating response…")}</span>
            </div>
          )}
          <div ref={endRef} />
        </div>

        {/* Error notification */}
        {error && <ErrorNote message={error} />}

        {/* Input Bar with Mic & Send */}
        <form onSubmit={(e) => send(e)} className="flex items-end gap-2 rounded-2xl border border-border bg-surface p-2 shadow-lg shadow-black/10">
          {/* Microphone button */}
          <button
            type="button"
            onClick={toggleListening}
            disabled={busy}
            title={isListening ? "Listening... click to stop" : "Click to speak with microphone"}
            className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-xl border text-sm transition-all ${
              isListening
                ? "border-danger bg-danger/20 text-danger animate-pulse shadow-[0_0_12px_rgba(239,68,68,0.5)]"
                : "border-border bg-surface-2 text-muted hover:text-fg hover:border-accent"
            }`}
          >
            {isListening ? "🔴" : "🎙️"}
          </button>

          <Input
            placeholder={
              isListening
                ? transcriptPreview || "Listening... speak now into your microphone"
                : "Type or click 🎙️ / 📞 Live Call to talk..."
            }
            value={input}
            onChange={(e) => setInput(e.target.value)}
            disabled={busy || isListening}
          />
          <Button type="submit" disabled={busy || !input.trim()} className="h-10 shrink-0 rounded-xl px-3">
            Send
          </Button>
        </form>
      </div>
    </div>
  );
}
