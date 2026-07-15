"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { apiFetch } from "@/lib/api";
import { Brand } from "@/components/Brand";
import { LanguageToggle } from "@/components/LanguageToggle";
import { type UiLanguage, useUiLanguage } from "@/lib/ui-language";

interface InvitePreview {
  guest_name: string;
  meeting_title: string;
  expected_spoken_language: "en" | "th";
  expires_at: string;
  is_valid: boolean;
}

const COPY = {
  en: {
    invalid: "This invitation link is invalid, expired, or has already been used.", unavailable: "This link is not available",
    opening: "Opening your invitation", checking: "Checking the secure meeting link…", expired: "This invitation has expired", freshLink: "Ask the meeting host to create a fresh client link.",
    privateInvite: "Private invitation", invited: "You’re invited to", browser: "Join directly in your browser. You do not need an account or any software installation.",
    yourLanguage: "Your language", english: "English", thai: "Thai", closes: "Room closes automatically after 60 minutes", permissions: "Your browser will ask for camera and microphone access",
    ready: "Ready to join?", checkName: "Check your name before entering", displayName: "Your display name", namePlaceholder: "Your name",
    consent: "I understand that this meeting uses automated speech transcription and translation. Audio is processed in real time and is not recorded by this application.",
    joinError: "The invitation could not be used.", failed: "Failed to join. Please request a new link.", joining: "Joining securely…", join: "Join meeting",
    privacy: "Private translated captions are visible only to authorized internal participants.",
  },
  th: {
    invalid: "ลิงก์เชิญนี้ไม่ถูกต้อง หมดอายุ หรือถูกใช้งานแล้ว", unavailable: "ไม่สามารถใช้ลิงก์นี้ได้",
    opening: "กำลังเปิดคำเชิญ", checking: "กำลังตรวจสอบลิงก์การประชุมที่ปลอดภัย…", expired: "คำเชิญนี้หมดอายุแล้ว", freshLink: "โปรดขอให้เจ้าของการประชุมสร้างลิงก์ลูกค้าใหม่",
    privateInvite: "คำเชิญส่วนตัว", invited: "คุณได้รับเชิญให้เข้าร่วม", browser: "เข้าร่วมได้โดยตรงผ่านเบราว์เซอร์ ไม่ต้องมีบัญชีหรือติดตั้งซอฟต์แวร์",
    yourLanguage: "ภาษาของคุณ", english: "อังกฤษ", thai: "ไทย", closes: "ห้องจะปิดอัตโนมัติหลัง 60 นาที", permissions: "เบราว์เซอร์จะขอสิทธิ์ใช้กล้องและไมโครโฟน",
    ready: "พร้อมเข้าร่วมหรือยัง", checkName: "ตรวจสอบชื่อของคุณก่อนเข้าห้อง", displayName: "ชื่อที่แสดง", namePlaceholder: "ชื่อของคุณ",
    consent: "ฉันเข้าใจว่าการประชุมนี้ใช้ระบบถอดเสียงและแปลภาษาอัตโนมัติ เสียงจะถูกประมวลผลแบบเรียลไทม์และแอปพลิเคชันนี้จะไม่บันทึกเสียง",
    joinError: "ไม่สามารถใช้คำเชิญนี้ได้", failed: "ไม่สามารถเข้าร่วมได้ โปรดขอลิงก์ใหม่", joining: "กำลังเข้าร่วมอย่างปลอดภัย…", join: "เข้าร่วมการประชุม",
    privacy: "คำบรรยายแปลส่วนตัวจะแสดงเฉพาะผู้เข้าร่วมภายในที่ได้รับอนุญาต",
  },
} as const;

export default function JoinPage() {
  const { token } = useParams<{ token: string }>();
  const router = useRouter();
  const { language, setLanguage } = useUiLanguage();
  const copy = COPY[language];
  const [preview, setPreview] = useState<InvitePreview | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [displayName, setDisplayName] = useState("");
  const [consent, setConsent] = useState(false);
  const [joining, setJoining] = useState(false);

  useEffect(() => {
    async function fetchPreview() {
      try {
        const res = await apiFetch(`/api/public/invites/${token}`);
        if (!res.ok) throw new Error();
        const data: InvitePreview = await res.json();
        setPreview(data);
        setDisplayName(data.guest_name || "");
        setLanguage(data.expected_spoken_language);
      } catch {
        setError(COPY[language].invalid);
      }
    }
    fetchPreview();
    // The invitation is fetched once; language changes remain under the guest's control afterwards.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  async function handleJoin() {
    if (!displayName.trim() || !consent || !preview) return;
    setJoining(true);
    setError(null);
    try {
      const res = await apiFetch(`/api/public/invites/${token}/join`, {
        method: "POST",
        body: JSON.stringify({ display_name: displayName.trim() }),
      });
      if (!res.ok) throw new Error(copy.joinError);
      const data = await res.json();
      sessionStorage.setItem("guest_session_token", data.guest_session_token);
      sessionStorage.setItem("guest_identity", data.guest_identity);
      sessionStorage.setItem("display_name", displayName.trim());
      sessionStorage.setItem("meeting_id", data.meeting_id);
      sessionStorage.setItem("meeting_title", preview.meeting_title);
      sessionStorage.setItem("meeting_auto_end_at", preview.expires_at);
      sessionStorage.setItem("spoken_language", preview.expected_spoken_language);
      router.push(`/meeting/${data.meeting_id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : copy.failed);
    } finally {
      setJoining(false);
    }
  }

  if (error && !preview) return <InvitationState title={copy.unavailable} message={error} language={language} onLanguageChange={setLanguage} />;
  if (!preview) return <InvitationState title={copy.opening} message={copy.checking} loading language={language} onLanguageChange={setLanguage} />;
  if (!preview.is_valid) return <InvitationState title={copy.expired} message={copy.freshLink} language={language} onLanguageChange={setLanguage} />;

  return (
    <main className="app-shell flex min-h-screen flex-col">
      <header className="mx-auto flex w-full max-w-6xl items-center justify-between gap-3"><Brand /><LanguageToggle language={language} onChange={setLanguage} /></header>
      <div className="mx-auto grid w-full max-w-5xl flex-1 items-center gap-10 py-10 lg:grid-cols-[.9fr_1.1fr]">
        <section className="animate-lift-in">
          <p className="eyebrow mb-4">{copy.privateInvite}</p>
          <h1 className="text-4xl font-semibold leading-[1.08] tracking-[-0.045em] text-white sm:text-5xl">{copy.invited}<br /><span className="text-cyan-300">{preview.meeting_title}</span></h1>
          <p className="mt-5 max-w-md text-base leading-7 text-slate-400">{copy.browser}</p>
          <div className="mt-8 space-y-3 text-sm text-slate-400">
            <div className="flex items-center gap-3"><span className="grid h-8 w-8 place-items-center rounded-xl bg-white/5 text-cyan-300">⌁</span><span>{copy.yourLanguage}: <strong className="font-medium text-slate-200">{preview.expected_spoken_language === "en" ? copy.english : copy.thai}</strong></span></div>
            <div className="flex items-center gap-3"><span className="grid h-8 w-8 place-items-center rounded-xl bg-white/5 text-cyan-300">◷</span><span>{copy.closes}</span></div>
            <div className="flex items-center gap-3"><span className="grid h-8 w-8 place-items-center rounded-xl bg-white/5 text-cyan-300">◇</span><span>{copy.permissions}</span></div>
          </div>
        </section>

        <section className="glass-panel animate-lift-in rounded-[1.75rem] p-6 [animation-delay:100ms] sm:p-8">
          <div className="mb-7 flex items-center gap-4">
            <div className="grid h-12 w-12 place-items-center rounded-2xl bg-gradient-to-br from-cyan-400/20 to-violet-500/20 text-lg font-semibold text-cyan-200">{displayName.trim().charAt(0).toUpperCase() || "C"}</div>
            <div><h2 className="text-xl font-semibold text-white">{copy.ready}</h2><p className="mt-1 text-xs text-slate-500">{copy.checkName}</p></div>
          </div>

          <div>
            <label htmlFor="display-name" className="field-label">{copy.displayName}</label>
            <input id="display-name" autoFocus value={displayName} onChange={(event) => setDisplayName(event.target.value)} className="field" placeholder={copy.namePlaceholder} maxLength={100} />
          </div>

          <label className="mt-5 flex cursor-pointer items-start gap-3 rounded-xl border border-white/10 bg-white/[0.025] p-4 transition hover:bg-white/[0.045]">
            <input type="checkbox" checked={consent} onChange={(event) => setConsent(event.target.checked)} className="mt-0.5 h-4 w-4 rounded border-white/20 bg-slate-950 accent-cyan-400" />
            <span className="text-xs leading-5 text-slate-400">{copy.consent}</span>
          </label>

          {error && <div role="alert" className="mt-4 rounded-xl border border-rose-400/20 bg-rose-500/10 p-3 text-sm text-rose-200">{error}</div>}

          <button onClick={handleJoin} disabled={!displayName.trim() || !consent || joining} className="primary-button mt-6 w-full !py-3.5">
            {joining ? <><span className="h-4 w-4 animate-spin rounded-full border-2 border-slate-900/30 border-t-slate-900" />{copy.joining}</> : <>{copy.join} <span aria-hidden>→</span></>}
          </button>
          <p className="mt-4 text-center text-[11px] leading-5 text-slate-600">{copy.privacy}</p>
        </section>
      </div>
    </main>
  );
}

function InvitationState({ title, message, language, onLanguageChange, loading = false }: { title: string; message: string; language: UiLanguage; onLanguageChange: (language: UiLanguage) => void; loading?: boolean }) {
  return (
    <main className="app-shell flex min-h-screen flex-col"><header className="mx-auto flex w-full max-w-6xl items-center justify-between gap-3"><Brand /><LanguageToggle language={language} onChange={onLanguageChange} /></header><div className="grid flex-1 place-items-center"><div className="glass-panel max-w-md rounded-[1.75rem] p-9 text-center">{loading ? <span className="mx-auto block h-8 w-8 animate-spin rounded-full border-2 border-cyan-400/20 border-t-cyan-300" /> : <span className="mx-auto grid h-12 w-12 place-items-center rounded-2xl bg-amber-400/10 text-xl text-amber-300">!</span>}<h1 className="mt-5 text-2xl font-semibold text-white">{title}</h1><p className="mt-3 text-sm leading-6 text-slate-400">{message}</p></div></div></main>
  );
}
