"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { apiFetch } from "@/lib/api";
import { Brand } from "@/components/Brand";
import { LanguageToggle } from "@/components/LanguageToggle";
import { languageFromAccessToken, saveUiLanguage, useUiLanguage } from "@/lib/ui-language";

const COPY = {
  en: {
    workspace: "Internal workspace",
    headline: <>One conversation.<br />Two languages.</>,
    intro: "Your English and Thai team accounts receive private translated captions. Client participants never receive caption data.",
    benefits: ["Live translated captions for internal users", "One-click, expiring client invitation links", "No recording and no stored transcript by default"],
    welcome: "Welcome back",
    signIn: "Sign in",
    accountHelp: "Use your English or Thai internal account.",
    email: "Email address",
    emailPlaceholder: "name@company.com",
    password: "Password",
    internalOnly: "Internal accounts only",
    passwordPlaceholder: "Enter your password",
    signingIn: "Signing in…",
    continue: "Continue",
    clientHelp: "Clients do not sign in here. They join using the private invitation link you share with them.",
    loginError: "We could not sign you in with those details.",
  },
  th: {
    workspace: "พื้นที่ทำงานสำหรับทีม",
    headline: <>หนึ่งบทสนทนา<br />สองภาษา</>,
    intro: "บัญชีทีมภาษาอังกฤษและภาษาไทยจะได้รับคำบรรยายแปลแบบส่วนตัว ส่วนผู้เข้าร่วมที่เป็นลูกค้าจะไม่ได้รับข้อมูลคำบรรยาย",
    benefits: ["คำบรรยายแปลสดสำหรับผู้ใช้ภายใน", "ลิงก์เชิญลูกค้าที่สร้างได้ในคลิกเดียวและหมดอายุอัตโนมัติ", "ไม่มีการบันทึกเสียงและไม่จัดเก็บบทสนทนาเป็นค่าเริ่มต้น"],
    welcome: "ยินดีต้อนรับกลับ",
    signIn: "เข้าสู่ระบบ",
    accountHelp: "ใช้บัญชีภายในภาษาอังกฤษหรือภาษาไทยของคุณ",
    email: "อีเมล",
    emailPlaceholder: "name@company.com",
    password: "รหัสผ่าน",
    internalOnly: "เฉพาะบัญชีภายใน",
    passwordPlaceholder: "กรอกรหัสผ่าน",
    signingIn: "กำลังเข้าสู่ระบบ…",
    continue: "ดำเนินการต่อ",
    clientHelp: "ลูกค้าไม่ต้องเข้าสู่ระบบที่นี่ แต่เข้าร่วมผ่านลิงก์เชิญส่วนตัวที่คุณส่งให้",
    loginError: "ไม่สามารถเข้าสู่ระบบด้วยข้อมูลนี้ได้ โปรดตรวจสอบอีกครั้ง",
  },
} as const;

export default function LoginPage() {
  const router = useRouter();
  const { language, setLanguage } = useUiLanguage();
  const copy = COPY[language];
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
      if (!res.ok) throw new Error(copy.loginError);
      const tokens = await res.json();
      localStorage.setItem("access_token", tokens.access_token);
      localStorage.setItem("refresh_token", tokens.refresh_token);
      saveUiLanguage(languageFromAccessToken(tokens.access_token));
      sessionStorage.removeItem("guest_session_token");
      sessionStorage.removeItem("guest_identity");
      router.push("/dashboard");
    } catch (err) {
      setError(err instanceof Error ? err.message : copy.loginError);
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="app-shell flex min-h-screen flex-col">
      <header className="mx-auto flex w-full max-w-6xl items-center justify-between gap-3"><Brand /><LanguageToggle language={language} onChange={setLanguage} /></header>
      <div className="mx-auto grid w-full max-w-6xl flex-1 items-center gap-12 py-12 lg:grid-cols-2">
        <section className="hidden max-w-lg lg:block">
          <p className="eyebrow mb-4">{copy.workspace}</p>
          <h1 className="text-5xl font-semibold leading-[1.08] tracking-[-0.05em] text-white">{copy.headline}</h1>
          <p className="mt-6 text-lg leading-8 text-slate-400">{copy.intro}</p>
          <div className="mt-9 space-y-4 text-sm text-slate-300">
            {copy.benefits.map((item) => (
              <div key={item} className="flex items-center gap-3"><span className="grid h-6 w-6 place-items-center rounded-full bg-cyan-400/10 text-xs text-cyan-300">✓</span>{item}</div>
            ))}
          </div>
        </section>

        <section className="glass-panel animate-lift-in mx-auto w-full max-w-md rounded-[1.75rem] p-7 sm:p-9">
          <div className="mb-8">
            <p className="eyebrow mb-3">{copy.welcome}</p>
            <h2 className="text-3xl font-semibold tracking-[-0.035em] text-white">{copy.signIn}</h2>
            <p className="mt-2 text-sm leading-6 text-slate-400">{copy.accountHelp}</p>
          </div>
          <form onSubmit={handleLogin} className="space-y-5">
            <div>
              <label htmlFor="email" className="field-label">{copy.email}</label>
              <input id="email" type="email" autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)} required className="field" placeholder={copy.emailPlaceholder} />
            </div>
            <div>
              <div className="mb-2 flex items-center justify-between"><label htmlFor="password" className="text-sm font-medium text-slate-300">{copy.password}</label><span className="text-xs text-slate-600">{copy.internalOnly}</span></div>
              <input id="password" type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} required className="field" placeholder={copy.passwordPlaceholder} />
            </div>
            {error && <div role="alert" className="rounded-xl border border-rose-400/20 bg-rose-500/10 px-4 py-3 text-sm text-rose-200">{error}</div>}
            <button type="submit" disabled={loading} className="primary-button w-full">
              {loading ? <><span className="h-4 w-4 animate-spin rounded-full border-2 border-slate-900/30 border-t-slate-900" />{copy.signingIn}</> : <>{copy.continue} <span aria-hidden>→</span></>}
            </button>
          </form>
          <p className="mt-7 border-t border-white/10 pt-6 text-center text-xs leading-5 text-slate-500">{copy.clientHelp}</p>
        </section>
      </div>
    </main>
  );
}
