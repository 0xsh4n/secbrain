"use client";

/**
 * Cyberpunk Hacker Girl Voice & Audio Synthesizer
 * Uses native Web Speech API and Web Audio API (zero extra dependencies).
 */

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
    // 2-tone frequency sweep: 880Hz -> 1760Hz in 80ms (sci-fi terminal chirp)
    osc.frequency.setValueAtTime(880, ctx.currentTime);
    osc.frequency.exponentialRampToValueAtTime(1760, ctx.currentTime + 0.08);

    gain.gain.setValueAtTime(0.08, ctx.currentTime);
    gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.08);

    osc.connect(gain);
    gain.connect(ctx.destination);

    osc.start();
    osc.stop(ctx.currentTime + 0.08);
  } catch {
    // AudioContext might be muted until user interaction
  }
}

export function playCallConnectSound() {
  const ctx = getAudioContext();
  if (!ctx) return;
  try {
    // Sci-fi uplink sound: 3 quick ascending tones
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
    // ignore
  }
}

export function playCallDisconnectSound() {
  const ctx = getAudioContext();
  if (!ctx) return;
  try {
    // 2 descending tones
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
    // ignore
  }
}

/**
 * Clean markdown and code blocks so speech is natural and pleasant
 */
export function cleanTextForSpeech(text: string): string {
  let cleaned = text;

  // Replace code blocks with a polite verbal notice
  cleaned = cleaned.replace(/```[\s\S]*?```/g, " Code is displayed in the chat. ");

  // Remove markdown headers, bold, italics, inline code, and URLs
  cleaned = cleaned
    .replace(/^#+\s+/gm, "")
    .replace(/\*\*(.*?)\*\*/g, "$1")
    .replace(/\*(.*?)\*/g, "$1")
    .replace(/`([^`]+)`/g, "$1")
    .replace(/\[E\d+\]/g, "")
    .replace(/https?:\/\/\S+/g, "link")
    .replace(/[-*]\s+/g, "")
    .replace(/\n+/g, " ")
    .trim();

  return cleaned;
}

/**
 * Speak using the female hacker voice profile
 */
export function speakHackerGirl(text: string, onEnd?: () => void) {
  if (typeof window === "undefined" || !("speechSynthesis" in window)) {
    if (onEnd) onEnd();
    return;
  }

  // Cancel any ongoing speech
  window.speechSynthesis.cancel();

  const spokenText = cleanTextForSpeech(text);
  if (!spokenText) {
    if (onEnd) onEnd();
    return;
  }

  const utterance = new SpeechSynthesisUtterance(spokenText);

  // Find best available female English voice
  const voices = window.speechSynthesis.getVoices();
  const femaleVoice =
    voices.find(
      (v) =>
        v.lang.startsWith("en") &&
        (v.name.includes("Zira") ||
          v.name.includes("Samantha") ||
          v.name.includes("Jenny") ||
          v.name.includes("Victoria") ||
          v.name.includes("Karen") ||
          v.name.includes("Female") ||
          v.name.includes("Google UK English Female") ||
          v.name.includes("Google US English"))
    ) ||
    voices.find((v) => v.lang.startsWith("en")) ||
    voices[0];

  if (femaleVoice) {
    utterance.voice = femaleVoice;
  }

  // Keep the voice close to normal conversational pacing.
  utterance.pitch = 1.08;
  utterance.rate = 0.98;

  if (onEnd) {
    utterance.onend = () => onEnd();
    utterance.onerror = () => onEnd();
  }

  window.speechSynthesis.speak(utterance);
}

/** Speaks complete sentences as they arrive from a streamed answer. */
export class StreamingSpeech {
  private buffer = "";
  private queue: string[] = [];
  private speaking = false;
  private finished = false;
  private cancelled = false;
  private suppressingCode = false;

  constructor(private readonly onEnd?: () => void) {}

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
      this.queue.push("Code is displayed in the chat.");
    }
    const codeStart = this.buffer.indexOf("```");
    if (codeStart >= 0) {
      const codeEnd = this.buffer.indexOf("```", codeStart + 3);
      if (codeEnd < 0) {
        const beforeCode = this.buffer.slice(0, codeStart).trim();
        if (beforeCode) this.queue.push(beforeCode);
        this.buffer = "";
        this.suppressingCode = true;
        this.pump();
        return;
      }
      this.buffer = `${this.buffer.slice(0, codeStart)} Code is displayed in the chat. ${this.buffer.slice(codeEnd + 3)}`;
    }
    const sentencePattern = /^([\s\S]*?[.!?](?:["')\]]*)\s+)/;
    let match: RegExpExecArray | null;
    while ((match = sentencePattern.exec(this.buffer))) {
      this.queue.push(match[1].trim());
      this.buffer = this.buffer.slice(match[0].length);
    }
    // Avoid waiting indefinitely when a long answer has no punctuation.
    if (this.buffer.length > 280) {
      const splitAt = this.buffer.lastIndexOf(" ", 240);
      if (splitAt > 0) {
        this.queue.push(this.buffer.slice(0, splitAt).trim());
        this.buffer = this.buffer.slice(splitAt + 1);
      }
    }
    this.pump();
  }

  finish() {
    if (this.cancelled) return;
    this.finished = true;
    if (this.suppressingCode) {
      this.queue.push("Code is displayed in the chat.");
      this.suppressingCode = false;
    }
    if (this.buffer.trim()) this.queue.push(this.buffer.trim());
    this.buffer = "";
    this.pump();
  }

  cancel() {
    this.cancelled = true;
    this.queue = [];
    this.buffer = "";
  }

  private pump() {
    if (this.cancelled || this.speaking) return;
    const next = this.queue.shift();
    if (!next) {
      if (this.finished) this.onEnd?.();
      return;
    }
    if (typeof window === "undefined" || !("speechSynthesis" in window)) {
      this.cancelled = true;
      this.onEnd?.();
      return;
    }
    this.speaking = true;
    const utterance = new SpeechSynthesisUtterance(cleanTextForSpeech(next));
    const voices = window.speechSynthesis.getVoices();
    utterance.voice = voices.find((voice) => voice.lang.startsWith("en") && /zira|samantha|jenny|victoria|karen|female|google us english/i.test(voice.name))
      || voices.find((voice) => voice.lang.startsWith("en"))
      || voices[0]
      || null;
    utterance.pitch = 1.08;
    utterance.rate = 0.98;
    utterance.onend = () => {
      this.speaking = false;
      this.pump();
    };
    utterance.onerror = () => {
      this.speaking = false;
      this.pump();
    };
    window.speechSynthesis.speak(utterance);
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
    // Some devices reject optional audio constraints; retry with browser defaults.
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
}
