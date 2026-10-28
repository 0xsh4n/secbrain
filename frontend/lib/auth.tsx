"use client";

import { createContext, useContext, useEffect, useState, ReactNode } from "react";
import { useRouter } from "next/navigation";
import { api, setToken, getToken } from "./api";
import type { UserOut } from "./types";

interface AuthState {
  user: UserOut | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string, org: string, name: string) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<UserOut | null>(null);
  const [loading, setLoading] = useState(true);
  const router = useRouter();

  useEffect(() => {
    const token = getToken();
    if (!token) {
      setLoading(false);
      return;
    }
    api<UserOut>("/auth/me")
      .then(setUser)
      .catch(() => setToken(null))
      .finally(() => setLoading(false));
  }, []);

  async function login(email: string, password: string) {
    const res = await api<{ access_token: string }>("/auth/login", {
      method: "POST",
      auth: false,
      body: { email, password },
    });
    setToken(res.access_token);
    setUser(await api<UserOut>("/auth/me"));
    router.push("/dashboard");
  }

  async function register(email: string, password: string, org: string, name: string) {
    const res = await api<{ access_token: string }>("/auth/register", {
      method: "POST",
      auth: false,
      body: { email, password, organization_name: org, full_name: name },
    });
    setToken(res.access_token);
    setUser(await api<UserOut>("/auth/me"));
    router.push("/dashboard");
  }

  function logout() {
    setToken(null);
    setUser(null);
    router.push("/login");
  }

  return (
    <AuthContext.Provider value={{ user, loading, login, register, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
