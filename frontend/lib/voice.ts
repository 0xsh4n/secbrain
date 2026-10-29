"use client";

/**
 * Nyx voice & audio.
 *
 * Primary TTS is the backend **Piper** neural voice (warm, human-like, runs on
 * the server CPU, offline). If the backend voice is unavailable, we fall back to
 * the browser's built-in speech synthesis so voice still works everywhere.
 */

import { apiBase, getToken } from "./api";

function getAudioContext(): AudioContext | null {
  if (typeof window === "undefined") return null;
  try {
    const AudioContextClass =
      window.AudioContext ||
      (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext;
    if (!AudioContextClass) return null;
    return new AudioContextClass();
  } catch {
    return null;
  }
}

export function playCyberBeep() {
  const ctx = getAudioContext();
  if (!ctx) return;
  try {
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.type = "sine";
    osc.frequency.setValueAtTime(880, ctx.currentTime);
    osc.frequency.exponentialRampToValueAtTime(1760, ctx.currentTime + 0.08);
    gain.gain.setValueAtTime(0.08, ctx.currentTime);
    gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.08);
    osc.connect(gain);
    gain.connect(ctx.destination);
    osc.start();
    osc.stop(ctx.currentTime + 0.08);
  } catch {
    /* AudioContext might be muted until user interaction */
  }
}

export function playCallConnectSound() {
  const ctx = getAudioContext();
  if (!ctx) return;
  try {
    const now = ctx.currentTime;
    [520, 660, 880].forEach((freq, i) => {
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.type = "triangle";
      osc.frequency.setValueAtTime(freq, now + i * 0.07);
      gain.gain.setValueAtTime(0.08, now + i * 0.07);
      gain.gain.exponentialRampToValueAtTime(0.001, now + i * 0.07 + 0.06);
      osc.connect(gain);
      gain.connect(ctx.destination);
      osc.start(now + i * 0.07);
      osc.stop(now + i * 0.07 + 0.06);
    });
  } catch {
    /* ignore */
  }
}

export function playCallDisconnectSound() {
  const ctx = getAudioContext();
  if (!ctx) return;
  try {
    const now = ctx.currentTime;
    [880, 440].forEach((freq, i) => {
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.type = "sine";
      osc.frequency.setValueAtTime(freq, now + i * 0.08);
      gain.gain.setValueAtTime(0.08, now + i * 0.08);
      gain.gain.exponentialRampToValueAtTime(0.001, now + i * 0.08 + 0.07);
      osc.connect(gain);
      gain.connect(ctx.destination);
      osc.start(now + i * 0.08);
      osc.stop(now + i * 0.08 + 0.07);
    });
  } catch {
    /* ignore */
  }
}

/** Clean markdown and code blocks so speech is natural and pleasant. */
export function cleanTextForSpeech(text: string): string {
  return text
    .replace(/```[\s\S]*?```/g, " Code is shown in the chat. ")
    .replace(/^#+\s+/gm, "")
    .replace(/\*\*(.*?)\*\*/g, "$1")
    .replace(/\*(.*?)\*/g, "$1")
    .replace(/`([^`]+)`/g, "$1")
    .replace(/\[E\d+\]/g, "")
    .replace(/https?:\/\/\S+/g, "link")
    .replace(/[-*]\s+/g, "")
    .replace(/\n+/g, " ")
    .trim();
}

// --- Backend (Piper) TTS ----------------------------------------------------
let backendTtsAvailable: boolean | null = null; // null = unknown, re-probe
let currentAudio: HTMLAudioElement | null = null;

async function fetchNyxAudio(text: string): Promise<Blob | null> {
  if (backendTtsAvailable === false) return null;
  const clean = cleanTextForSpeech(text);
  if (!clean) return null;
  const token = getToken();
  if (!token) return null;
  try {
    const res = await fetch(`${apiBase()}/api/v1/voice/tts`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
      body: JSON.stringify({ text: clean }),
    });
    if (res.status === 503) {
      backendTtsAvailable = false; // voice not installed; stop probing this session
      return null;
    }
    if (!res.ok) return null;
    backendTtsAvailable = true;
    return await res.blob();
  } catch {
    return null;
  }
}

function playBlob(blob: Blob): Promise<void> {
  return new Promise((resolve) => {
    const url = URL.createObjectURL(blob);
    const audio = new Audio(url);
    currentAudio = audio;
    const done = () => {
      URL.revokeObjectURL(url);
      if (currentAudio === audio) currentAudio = null;
      resolve();
    };
    audio.onended = done;
    audio.onerror = done;
    audio.play().catch(done);
  });
}

function speakBrowser(text: string): Promise<void> {
  return new Promise((resolve) => {
    if (typeof window === "undefined" || !("speechSynthesis" in window)) {
      resolve();
      return;
    }
    const spoken = cleanTextForSpeech(text);
    if (!spoken) {
      resolve();
      return;
    }
    const utterance = new SpeechSynthesisUtterance(spoken);
    const voices = window.speechSynthesis.getVoices();
    utterance.voice =
      voices.find(
        (v) => v.lang.startsWith("en") && /jenny|aria|samantha|female|google us english/i.test(v.name)
      ) ||
      voices.find((v) => v.lang.startsWith("en")) ||
      voices[0] ||
      null;
    utterance.pitch = 1.05;
    utterance.rate = 1.0;
    utterance.onend = () => resolve();
    utterance.onerror = () => resolve();
    window.speechSynthesis.speak(utterance);
  });
}

/** Speak one piece of text as Nyx (Piper, with browser fallback). */
export async function speakNyx(text: string, onEnd?: () => void) {
  stopSpeaking();
  const blob = await fetchNyxAudio(text);
  if (blob) await playBlob(blob);
  else await speakBrowser(text);
  onEnd?.();
}

/** Backwards-compatible alias. */
export const speakHackerGirl = speakNyx;

/** Speaks complete sentences as they stream in, as Nyx. Synthesis of the next
 *  sentence overlaps playback of the current one to reduce gaps. */
export class StreamingSpeech {
  private buffer = "";
  private queue: { text: string; audio: Promise<Blob | null> }[] = [];
  private playing = false;
  private finished = false;
  private cancelled = false;
  private suppressingCode = false;

  constructor(private readonly onEnd?: () => void) {}

  private enqueue(sentence: string) {
    const text = sentence.trim();
    if (!text) return;
    // Start synthesis immediately so it overlaps playback of earlier sentences.
    this.queue.push({ text, audio: fetchNyxAudio(text).catch(() => null) });
    this.pump();
  }

  push(text: string) {
    if (this.cancelled || this.finished) return;
    this.buffer += text;
    if (this.suppressingCode) {
      const codeEnd = this.buffer.indexOf("```");
      if (codeEnd < 0) {
        this.buffer = "";
        return;
      }
      this.buffer = this.buffer.slice(codeEnd + 3);
      this.suppressingCode = false;
      this.enqueue("Code is shown in the chat.");
    }
    const codeStart = this.buffer.indexOf("```");
    if (codeStart >= 0) {
      const codeEnd = this.buffer.indexOf("```", codeStart + 3);
      if (codeEnd < 0) {
        const beforeCode = this.buffer.slice(0, codeStart).trim();
        if (beforeCode) this.enqueue(beforeCode);
        this.buffer = "";
        this.suppressingCode = true;
        return;
      }
      this.buffer = `${this.buffer.slice(0, codeStart)} Code is shown in the chat. ${this.buffer.slice(codeEnd + 3)}`;
    }
    const sentencePattern = /^([\s\S]*?[.!?](?:["')\]]*)\s+)/;
    let match: RegExpExecArray | null;
    while ((match = sentencePattern.exec(this.buffer))) {
      this.enqueue(match[1]);
      this.buffer = this.buffer.slice(match[0].length);
    }
    if (this.buffer.length > 280) {
      const splitAt = this.buffer.lastIndexOf(" ", 240);
      if (splitAt > 0) {
        this.enqueue(this.buffer.slice(0, splitAt));
        this.buffer = this.buffer.slice(splitAt + 1);
      }
    }
  }

  finish() {
    if (this.cancelled) return;
    this.finished = true;
    if (this.suppressingCode) {
      this.enqueue("Code is shown in the chat.");
      this.suppressingCode = false;
    }
    if (this.buffer.trim()) this.enqueue(this.buffer);
    this.buffer = "";
    this.pump();
  }

  cancel() {
    this.cancelled = true;
    this.queue = [];
    this.buffer = "";
    stopSpeaking();
  }

  private async pump() {
    if (this.cancelled || this.playing) return;
    const next = this.queue.shift();
    if (!next) {
      if (this.finished) this.onEnd?.();
      return;
    }
    this.playing = true;
    const blob = await next.audio;
    if (this.cancelled) return;
    if (blob) await playBlob(blob);
    else await speakBrowser(next.text);
    this.playing = false;
    this.pump();
  }
}

export async function getProcessedMicrophone(): Promise<MediaStream> {
  if (!navigator.mediaDevices?.getUserMedia) {
    throw new Error("Microphone access is unavailable. Use HTTPS or localhost and allow microphone access.");
  }
  try {
    return await navigator.mediaDevices.getUserMedia({
      audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === "OverconstrainedError") {
      return navigator.mediaDevices.getUserMedia({ audio: true });
    }
    throw error;
  }
}

export function stopSpeaking() {
  if (typeof window !== "undefined" && "speechSynthesis" in window) {
    window.speechSynthesis.cancel();
  }
  if (currentAudio) {
    try {
      currentAudio.pause();
    } catch {
      /* ignore */
    }
    currentAudio = null;
  }
}
