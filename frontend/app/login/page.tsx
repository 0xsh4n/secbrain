"use client";

import { useState } from "react";
import { useAuth } from "@/lib/auth";
import { Button, Card, Input, ErrorNote } from "@/components/ui";

export default function LoginPage() {
  const { login, register } = useAuth();
  const [mode, setMode] = useState<"login" | "register">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [org, setOrg] = useState("");
  const [name, setName] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setBusy(true);
    try {
      if (mode === "login") await login(email, password);
      else await register(email, password, org, name);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Request failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center p-4">
      <Card className="w-full max-w-md p-6">
        <div className="mb-6 text-center">
          <div className="text-2xl font-bold text-accent">◆ SecBrain</div>
          <p className="mt-1 text-sm text-muted">Cybersecurity knowledge platform</p>
        </div>
        <form onSubmit={submit} className="space-y-3">
          {mode === "register" && (
            <>
              <Input placeholder="Full name" value={name} onChange={(e) => setName(e.target.value)} />
              <Input
                placeholder="Organization name"
                value={org}
                onChange={(e) => setOrg(e.target.value)}
              />
            </>
          )}
          <Input
            type="email"
            placeholder="Email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
          />
          <Input
            type="password"
            placeholder="Password (min 8 chars)"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
          />
          {error && <ErrorNote message={error} />}
          <Button type="submit" className="w-full" disabled={busy}>
            {busy ? "Please wait…" : mode === "login" ? "Sign in" : "Create account"}
          </Button>
        </form>
        <div className="mt-4 text-center text-sm text-muted">
          {mode === "login" ? "No account?" : "Have an account?"}{" "}
          <button
            className="text-accent hover:underline"
            onClick={() => {
              setMode(mode === "login" ? "register" : "login");
              setError("");
            }}
          >
            {mode === "login" ? "Register a workspace" : "Sign in"}
          </button>
        </div>
      </Card>
    </div>
  );
}
