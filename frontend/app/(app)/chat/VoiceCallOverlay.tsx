"use client";

import { useEffect, useRef, useState } from "react";
import { getProcessedMicrophone, playCallConnectSound, playCallDisconnectSound, speakNyx, stopSpeaking, StreamingSpeech } from "@/lib/voice";

interface VoiceCallOverlayProps {
  isOpen: boolean;
  onClose: () => void;
  onSendMessage: (text: string, onToken?: (token: string) => void) => Promise<string>;
}

type CallState = "connecting" | "listening" | "thinking" | "speaking";

export function VoiceCallOverlay({ isOpen, onClose, onSendMessage }: VoiceCallOverlayProps) {
  const [callState, setCallState] = useState<CallState>("connecting");
  const [callDuration, setCallDuration] = useState(0);
  const [userTranscript, setUserTranscript] = useState("");
  const [aiTranscript, setAiTranscript] = useState("");
  const [errorMessage, setErrorMessage] = useState("");
  const [isMuted, setIsMuted] = useState(false);
  const [manualText, setManualText] = useState("");

  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const audioContextRef = useRef<AudioContext | null>(null);
  const analyserRef = useRef<AnalyserNode | null>(null);
  const mediaStreamRef = useRef<MediaStream | null>(null);
  const recognitionRef = useRef<unknown>(null);
  const animationFrameRef = useRef<number | null>(null);
  const isCallActiveRef = useRef(false);
  const callStateRef = useRef<CallState>("connecting");
  const mutedRef = useRef(false);
  const recognitionRestartRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const handlingSpeechRef = useRef(false);
  const speechQueueRef = useRef<StreamingSpeech | null>(null);

  function updateCallState(next: CallState) {
    callStateRef.current = next;
    setCallState(next);
  }

  // Call duration counter
  useEffect(() => {
    if (!isOpen) return;
    const interval = setInterval(() => {
      setCallDuration((prev) => prev + 1);
    }, 1000);
    return () => clearInterval(interval);
  }, [isOpen]);

  // Main call initialization
  useEffect(() => {
    if (!isOpen) {
      cleanupCall();
      return;
    }

    isCallActiveRef.current = true;
    updateCallState("connecting");
    setIsMuted(false);
    mutedRef.current = false;
    setCallDuration(0);
    setUserTranscript("");
    setAiTranscript("Connecting to Nyx…");
    setErrorMessage("");

    playCallConnectSound();

    // Start audio visualizer and speech recognition
    startCallSession();

    return () => {
      cleanupCall();
    };
  }, [isOpen]);

  async function startCallSession() {
    try {
      // 1. Request microphone access for real-time visualizer
      const stream = await getProcessedMicrophone();
      if (!isCallActiveRef.current) {
        stream.getTracks().forEach((track) => track.stop());
        return;
      }
      mediaStreamRef.current = stream;

      const AudioContextClass =
        window.AudioContext ||
        (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext;
      const audioCtx = new AudioContextClass();
      audioContextRef.current = audioCtx;

      const analyser = audioCtx.createAnalyser();
      analyser.fftSize = 64;
      analyserRef.current = analyser;

      const source = audioCtx.createMediaStreamSource(stream);
      source.connect(analyser);

      // Start drawing real-time sound waves
      drawVisualizer();

      if (!isCallActiveRef.current) return;
      updateCallState("speaking");
      const greeting = "Hey, I'm Nyx. I'm listening — what can I help you with?";
      setAiTranscript(greeting);

      // Initial greeting voice
      speakNyx(greeting, () => {
        if (isCallActiveRef.current) {
          startListeningLoop();
        }
      });
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : "Could not access the microphone.");
      startListeningLoop();
    }
  }

  function startListeningLoop() {
    if (!isCallActiveRef.current) return;
    if (recognitionRef.current && callStateRef.current === "listening") return;
    updateCallState("listening");
    setUserTranscript("");

    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const SpeechRecognition = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;

    if (!SpeechRecognition) {
      setErrorMessage("Speech recognition not supported in this browser. Try Chrome, Edge, or Safari.");
      return;
    }

    try {
      if (recognitionRestartRef.current) {
        clearTimeout(recognitionRestartRef.current);
        recognitionRestartRef.current = null;
      }
      if (recognitionRef.current) {
        const previous = recognitionRef.current as { abort: () => void };
        recognitionRef.current = null;
        previous.abort();
      }

      const recognition = new SpeechRecognition();
      recognition.lang = "en-IN";
      recognition.interimResults = true;
      recognition.continuous = false;
      recognition.maxAlternatives = 1;

      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      recognition.onresult = (event: any) => {
        let finalText = "";
        let interimText = "";
        let hasNewFinal = false;
        for (let i = 0; i < event.results.length; i++) {
          const result = event.results[i];
          if (result.isFinal) {
            finalText += `${result[0].transcript} `;
            if (i >= event.resultIndex) hasNewFinal = true;
          }
          else if (i >= event.resultIndex) interimText += `${result[0].transcript} `;
        }
        setUserTranscript((finalText || interimText).trim());

        if (hasNewFinal && finalText.trim()) {
          handleUserSpeech(finalText.trim());
        }
      };

      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      recognition.onerror = (e: any) => {
        if (e.error === "not-allowed" || e.error === "service-not-allowed") {
          setErrorMessage("Microphone blocked. Please grant permission.");
          recognitionRef.current = null;
        } else if (e.error === "network") {
          setErrorMessage("Browser speech recognition lost its network service. Check your connection, or use the text box below. Chrome or Edge usually works best.");
          recognitionRef.current = null;
        }
      };

      recognition.onend = () => {
        if (recognitionRef.current !== recognition) return;
        recognitionRef.current = null;
        if (isCallActiveRef.current && callStateRef.current === "listening" && !mutedRef.current) {
          if (recognitionRestartRef.current) clearTimeout(recognitionRestartRef.current);
          recognitionRestartRef.current = setTimeout(() => {
            if (isCallActiveRef.current && callStateRef.current === "listening" && !mutedRef.current) {
              startListeningLoop();
            }
          }, 350);
        }
      };

      recognitionRef.current = recognition;
      recognition.start();
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : "Could not start speech recognition.");
    }
  }

  async function handleUserSpeech(text: string) {
    const trimmed = text.trim();
    if (!trimmed || !isCallActiveRef.current || handlingSpeechRef.current) return;
    handlingSpeechRef.current = true;

    if (recognitionRef.current) {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      (recognitionRef.current as any).stop();
    }

    updateCallState("thinking");
    setAiTranscript("Thinking…");

    try {
      let streamedResponse = "";
      const speechQueue = new StreamingSpeech(() => {
        if (isCallActiveRef.current) startListeningLoop();
      });
      speechQueueRef.current = speechQueue;
      const response = await onSendMessage(trimmed, (token) => {
        streamedResponse += token;
        setAiTranscript(streamedResponse);
        if (token.trim()) updateCallState("speaking");
        speechQueue.push(token);
      });
      if (!isCallActiveRef.current) return;

      handlingSpeechRef.current = false;
      updateCallState("speaking");
      setAiTranscript(response);
      speechQueue.finish();
    } catch (cause) {
      speechQueueRef.current?.cancel();
      setErrorMessage(cause instanceof Error ? cause.message : "Could not get a reply from SecBrain.");
      updateCallState("listening");
      handlingSpeechRef.current = false;
      if (!mutedRef.current && isCallActiveRef.current) startListeningLoop();
    }
  }

  function drawVisualizer() {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const analyser = analyserRef.current;
    const bufferLength = analyser ? analyser.frequencyBinCount : 32;
    const dataArray = new Uint8Array(bufferLength);

    const render = () => {
      animationFrameRef.current = requestAnimationFrame(render);

      if (analyser && callStateRef.current === "listening" && !mutedRef.current) {
        analyser.getByteFrequencyData(dataArray);
      } else if (callStateRef.current === "speaking") {
        // Simulated cyber wave while Nyx speaks
        for (let i = 0; i < bufferLength; i++) {
          dataArray[i] = Math.sin(Date.now() * 0.008 + i * 0.4) * 60 + 80;
        }
      } else {
        // Low idle wave
        for (let i = 0; i < bufferLength; i++) {
          dataArray[i] = 10;
        }
      }

      ctx.clearRect(0, 0, canvas.width, canvas.height);

      const barWidth = (canvas.width / bufferLength) * 1.8;
      let x = 0;

      for (let i = 0; i < bufferLength; i++) {
        const barHeight = (dataArray[i] / 255) * canvas.height * 0.85;

        // Gradient cyber color: Cyan (#00f2fe) to Neon Accent
        const gradient = ctx.createLinearGradient(0, canvas.height, 0, 0);
        if (callStateRef.current === "listening") {
          gradient.addColorStop(0, "rgba(34, 211, 238, 0.2)");
          gradient.addColorStop(1, "rgba(34, 211, 238, 0.9)");
        } else if (callStateRef.current === "speaking") {
          gradient.addColorStop(0, "rgba(168, 85, 247, 0.2)");
          gradient.addColorStop(1, "rgba(192, 132, 252, 0.9)");
        } else {
          gradient.addColorStop(0, "rgba(148, 163, 184, 0.1)");
          gradient.addColorStop(1, "rgba(148, 163, 184, 0.4)");
        }

        ctx.fillStyle = gradient;
        // Symmetric center bars
        const y = (canvas.height - barHeight) / 2;
        ctx.fillRect(x, y, barWidth - 2, barHeight);

        x += barWidth;
      }
    };

    render();
  }

  function cleanupCall() {
    isCallActiveRef.current = false;
    handlingSpeechRef.current = false;
    speechQueueRef.current?.cancel();
    if (recognitionRestartRef.current) {
      clearTimeout(recognitionRestartRef.current);
      recognitionRestartRef.current = null;
    }
    stopSpeaking();
    playCallDisconnectSound();

    if (recognitionRef.current) {
      try {
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        (recognitionRef.current as any).abort();
      } catch {
        // ignore
      }
      recognitionRef.current = null;
    }

    if (mediaStreamRef.current) {
      mediaStreamRef.current.getTracks().forEach((track) => track.stop());
      mediaStreamRef.current = null;
    }

    if (audioContextRef.current) {
      audioContextRef.current.close().catch(() => {});
      audioContextRef.current = null;
    }

    if (animationFrameRef.current) {
      cancelAnimationFrame(animationFrameRef.current);
      animationFrameRef.current = null;
    }
  }

  function formatDuration(sec: number) {
    const mins = Math.floor(sec / 60);
    const s = sec % 60;
    return `${mins.toString().padStart(2, "0")}:${s.toString().padStart(2, "0")}`;
  }

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-[60] flex flex-col items-center justify-between overflow-y-auto bg-[#070b12]/95 px-3 pb-[max(env(safe-area-inset-bottom),0.75rem)] pt-[max(env(safe-area-inset-top),0.75rem)] text-fg backdrop-blur-2xl sm:p-6">
      {/* Top Bar: Telemetry & Link Status */}
      <div className="flex w-full max-w-4xl shrink-0 items-center justify-between gap-3 border-b border-border/50 pb-3 sm:pb-4">
        <div className="flex min-w-0 items-center gap-2 sm:gap-3">
          <div className="relative flex h-3 w-3">
            <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-accent opacity-75" />
            <span className="relative inline-flex h-3 w-3 rounded-full bg-accent" />
          </div>
          <div>
            <div className="truncate font-mono text-[10px] font-semibold uppercase tracking-widest text-accent sm:text-xs">
              LIVE VOICE • NYX
            </div>
            <div className="text-[10px] text-muted">
              NYX • NEURAL VOICE + SECBRAIN
            </div>
          </div>
        </div>

        <div className="font-mono text-sm tracking-wider text-muted font-bold">
          {formatDuration(callDuration)}
        </div>
      </div>

      {/* Center Stage: Holographic Avatar & Sound Wave */}
      <div className="my-auto flex w-full max-w-xl flex-col items-center justify-center space-y-4 py-4 text-center sm:space-y-6">
        {/* Operator Avatar Hologram */}
        <div className="relative flex items-center justify-center">
          <div
            className={`absolute h-32 w-32 rounded-full border border-accent/40 transition-all duration-700 sm:h-40 sm:w-40 ${
              callState === "speaking"
                ? "scale-125 border-purple-500/60 animate-pulse"
                : callState === "listening"
                ? "scale-110 border-accent animate-ping duration-1000"
                : "scale-100 border-border"
            }`}
          />
          <div
            className={`relative flex h-28 w-28 items-center justify-center rounded-full border-2 bg-surface shadow-[0_0_40px_rgba(34,211,238,0.2)] transition-all sm:h-32 sm:w-32 ${
              callState === "speaking"
                ? "border-purple-400 shadow-[0_0_50px_rgba(192,132,252,0.4)]"
                : callState === "listening"
                ? "border-accent shadow-[0_0_50px_rgba(34,211,238,0.4)]"
                : "border-border"
            }`}
          >
            <span className="text-4xl">
              {callState === "speaking" ? "👩‍💻" : callState === "thinking" ? "⚡" : "🎧"}
            </span>
          </div>
        </div>

        {/* State Indicator */}
        <div className="space-y-1">
          <div className="font-mono text-xs uppercase tracking-widest text-accent font-semibold">
            {callState === "connecting" && "CONNECTING TO NYX…"}
            {callState === "listening" && "🟢 NYX IS LISTENING"}
            {callState === "thinking" && "⚡ THINKING…"}
            {callState === "speaking" && "🔊 NYX IS SPEAKING"}
          </div>
          <div className="text-xs text-muted">
            {callState === "listening"
              ? "Speak naturally; Nyx will reply when you finish"
              : callState === "speaking"
              ? "Nyx is replying"
              : "Connecting…"}
          </div>
        </div>

        {/* Dynamic Waveform Visualizer */}
        <div className="w-full h-24 flex items-center justify-center">
          <canvas ref={canvasRef} width={400} height={90} className="w-full max-w-md h-full" />
        </div>

        {/* Live Subtitles / Transcripts */}
        <div className="max-h-36 w-full min-h-[5.5rem] overflow-y-auto rounded-2xl border border-border/60 bg-surface/80 p-3 text-left shadow-inner sm:max-h-48 sm:p-4">
          <div className="text-[10px] uppercase tracking-wider text-muted font-mono mb-1">
            Live transcript
          </div>
          {userTranscript && (
            <p className="text-xs text-muted mb-1.5">
              <span className="text-fg font-semibold">You:</span> {userTranscript}
            </p>
          )}
          {aiTranscript ? (
            <p className="text-xs text-fg leading-relaxed">
              <span className="text-accent font-mono font-semibold">Nyx:</span> {aiTranscript}
            </p>
          ) : (
            <p className="text-xs italic text-muted">Waiting…</p>
          )}
        </div>

        {errorMessage && (
          <div className="text-xs text-danger font-mono bg-danger/10 border border-danger/30 px-3 py-1.5 rounded">
            ⚠️ {errorMessage}
          </div>
        )}
      </div>

      {/* Bottom Controls Bar */}
      <div className="flex w-full max-w-xl shrink-0 flex-col items-center gap-3 pb-1 sm:gap-4">
        {/* Quick text input fallback while on call */}
        <form
          onSubmit={(e) => {
            e.preventDefault();
            if (manualText.trim()) {
              handleUserSpeech(manualText);
              setManualText("");
            }
          }}
          className="flex w-full gap-2"
        >
          <input
            type="text"
            placeholder="Type a message during call if in a noisy environment..."
            value={manualText}
            onChange={(e) => setManualText(e.target.value)}
            className="min-w-0 flex-1 rounded-xl border border-border bg-surface px-3 py-2.5 text-sm text-fg outline-none focus:border-accent"
          />
          <button
            type="submit"
            disabled={!manualText.trim()}
            className="shrink-0 rounded-xl border border-accent/40 bg-accent-dim/20 px-4 py-2.5 text-sm font-medium text-accent transition hover:bg-accent hover:text-black"
          >
            Send
          </button>
        </form>

        {/* Tactical Call Buttons */}
        <div className="flex items-center gap-5 sm:gap-6">
          {/* Mute button */}
          <button
            onClick={() => {
              const nextMuted = !mutedRef.current;
              mutedRef.current = nextMuted;
              setIsMuted(nextMuted);
              if (mediaStreamRef.current) {
                mediaStreamRef.current.getAudioTracks().forEach((track) => {
                  track.enabled = !nextMuted;
                });
              }
              if (nextMuted && recognitionRef.current) {
                (recognitionRef.current as { abort: () => void }).abort();
              } else if (!nextMuted && isCallActiveRef.current) {
                startListeningLoop();
              }
            }}
            title={isMuted ? "Unmute Microphone" : "Mute Microphone"}
            className={`flex h-12 w-12 items-center justify-center rounded-full border transition-all ${
              isMuted
                ? "border-danger bg-danger/20 text-danger"
                : "border-border bg-surface text-muted hover:text-fg hover:border-fg"
            }`}
          >
            <span className="text-lg">{isMuted ? "🔇" : "🎙️"}</span>
          </button>

          {/* End Call Button (Big Red Call End) */}
          <button
            onClick={onClose}
            title="End Call"
            className="flex items-center gap-2 rounded-full bg-danger px-4 py-3 font-mono text-[10px] font-bold text-white shadow-[0_0_20px_rgba(239,68,68,0.5)] transition-all hover:bg-danger/80 sm:px-6 sm:text-xs"
          >
            <span className="text-base">📞</span>
            <span className="sm:hidden">END</span><span className="hidden sm:inline">END CALL</span>
          </button>

          {/* Push to talk / Re-listen trigger */}
          <button
            onClick={() => {
              stopSpeaking();
              mutedRef.current = false;
              setIsMuted(false);
              startListeningLoop();
            }}
            title={errorMessage ? "Retry voice recognition" : "Tap to speak now"}
            className="flex h-12 w-12 items-center justify-center rounded-full border border-border bg-surface text-muted hover:text-accent hover:border-accent transition-all"
          >
            <span className="text-lg">⚡</span>
          </button>
        </div>
      </div>
    </div>
  );
}
