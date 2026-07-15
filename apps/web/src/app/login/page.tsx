"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { apiFetch } from "@/lib/api";
import { Brand } from "@/components/Brand";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function handleLogin(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      const res = await apiFetch("/api/auth/login", {
        method: "POST",
        body: JSON.stringify({ email: email.trim().toLowerCase(), password }),
      });
      if (!res.ok) {
        const data = await res.json().catch(() => null);
        throw new Error(data?.detail || "We could not sign you in with those details.");
      }
      const tokens = await res.json();
      localStorage.setItem("access_token", tokens.access_token);
      localStorage.setItem("refresh_token", tokens.refresh_token);
      sessionStorage.removeItem("guest_session_token");
      sessionStorage.removeItem("guest_identity");
      router.push("/dashboard");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Login failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="app-shell flex min-h-screen flex-col">
      <header className="mx-auto w-full max-w-6xl"><Brand /></header>
      <div className="mx-auto grid w-full max-w-6xl flex-1 items-center gap-12 py-12 lg:grid-cols-2">
        <section className="hidden max-w-lg lg:block">
          <p className="eyebrow mb-4">Internal workspace</p>
          <h1 className="text-5xl font-semibold leading-[1.08] tracking-[-0.05em] text-white">One conversation.<br />Two languages.</h1>
          <p className="mt-6 text-lg leading-8 text-slate-400">Your English and Thai team accounts receive private translated captions. Client participants never receive caption data.</p>
          <div className="mt-9 space-y-4 text-sm text-slate-300">
            {["Live translated captions for internal users", "One-click, expiring client invitation links", "No recording and no stored transcript by default"].map((item) => (
              <div key={item} className="flex items-center gap-3"><span className="grid h-6 w-6 place-items-center rounded-full bg-cyan-400/10 text-xs text-cyan-300">✓</span>{item}</div>
            ))}
          </div>
        </section>

        <section className="glass-panel animate-lift-in mx-auto w-full max-w-md rounded-[1.75rem] p-7 sm:p-9">
          <div className="mb-8">
            <p className="eyebrow mb-3">Welcome back</p>
            <h2 className="text-3xl font-semibold tracking-[-0.035em] text-white">Sign in</h2>
            <p className="mt-2 text-sm leading-6 text-slate-400">Use your English or Thai internal account.</p>
          </div>
          <form onSubmit={handleLogin} className="space-y-5">
            <div>
              <label htmlFor="email" className="field-label">Email address</label>
              <input id="email" type="email" autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)} required className="field" placeholder="name@company.com" />
            </div>
            <div>
              <div className="mb-2 flex items-center justify-between"><label htmlFor="password" className="text-sm font-medium text-slate-300">Password</label><span className="text-xs text-slate-600">Internal accounts only</span></div>
              <input id="password" type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} required className="field" placeholder="Enter your password" />
            </div>
            {error && <div role="alert" className="rounded-xl border border-rose-400/20 bg-rose-500/10 px-4 py-3 text-sm text-rose-200">{error}</div>}
            <button type="submit" disabled={loading} className="primary-button w-full">
              {loading ? <><span className="h-4 w-4 animate-spin rounded-full border-2 border-slate-900/30 border-t-slate-900" />Signing in…</> : <>Continue <span aria-hidden>→</span></>}
            </button>
          </form>
          <p className="mt-7 border-t border-white/10 pt-6 text-center text-xs leading-5 text-slate-500">Clients do not sign in here. They join using the private invitation link you share with them.</p>
        </section>
      </div>
    </main>
  );
}
