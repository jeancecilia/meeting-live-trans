"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { apiFetch } from "@/lib/api";
import { Brand } from "@/components/Brand";
import { LanguageToggle } from "@/components/LanguageToggle";
import { type UiLanguage, useUiLanguage } from "@/lib/ui-language";

interface Meeting {
  id: string;
  room_name: string;
  title: string;
  status: "created" | "active" | "ended";
  created_at: string;
  started_at: string | null;
  ended_at: string | null;
  auto_end_at: string | null;
  max_duration_minutes: number;
}

interface InviteResult {
  id: string;
  token: string;
  invite_url: string;
  guest_name: string;
  expires_at: string;
}

interface ShareDetails extends InviteResult {
  meetingId: string;
  meetingTitle: string;
}

const COPY = {
  en: {
    workspace: "Internal workspace", signOut: "Sign out", eyebrow: "Meeting workspace", heading: "Your conversations",
    intro: "Create a room, copy the private client link, and join when you are ready. Every room closes automatically after 60 minutes.",
    newMeeting: "New meeting", liveNow: "Live now", ready: "Ready", completed: "Completed", live: "Live", ended: "Ended",
    loading: "Loading your meetings…", emptyTitle: "Your first meeting starts here", emptyText: "Create a room and we will generate the client invitation link automatically.",
    createMeeting: "Create a meeting", clientLink: "Client link", joinRoom: "Join room", end: "End", completedTime: "Completed", limit: "60 minute limit", endingNow: "Ending now", remaining: "remaining",
    createTitle: "Create a meeting", createSubtitle: "A private, single-use client link will be created with the room.", meetingTitle: "Meeting title", meetingPlaceholder: "Client project consultation",
    clientName: "Client name", clientDefault: "Client", clientLanguage: "Client’s spoken language", english: "English", thai: "Thai",
    protectionTitle: "60-minute protection.", protectionText: "The invitation and room expire automatically. The client gets video and audio access, never private captions.",
    cancel: "Cancel", creating: "Creating…", createAndLink: "Create & get link", createLink: "Create client link", createLinkSubtitle: (title: string) => `For “${title}”. Each link admits one client once.`,
    createLinkButton: "Create link", shareReadyTitle: "Client link is ready", shareReadySubtitle: "Send this private link to your client. It can be used once and expires with the meeting.",
    readyToShare: "Ready to share", forGuest: "For", expires: "Expires", copied: "Copied ✓", copyLink: "Copy client link", share: "Share…", joinNow: "Join the meeting now",
    close: "Close", loadError: "Could not load meetings", createError: "Could not create the meeting", linkError: "Could not create the client link",
    partialError: "The meeting was created, but its client link was not. Use “Client link” on the meeting card to retry.", endError: "Could not end the meeting",
    endConfirm: (title: string) => `End “${title}” for everyone?`, shareText: (title: string) => `Join ${title}`,
  },
  th: {
    workspace: "พื้นที่ทำงานภายใน", signOut: "ออกจากระบบ", eyebrow: "พื้นที่การประชุม", heading: "การสนทนาของคุณ",
    intro: "สร้างห้อง คัดลอกลิงก์ส่วนตัวสำหรับลูกค้า และเข้าร่วมเมื่อพร้อม ทุกห้องจะปิดอัตโนมัติหลัง 60 นาที",
    newMeeting: "สร้างการประชุม", liveNow: "กำลังประชุม", ready: "พร้อม", completed: "เสร็จสิ้น", live: "กำลังประชุม", ended: "สิ้นสุดแล้ว",
    loading: "กำลังโหลดการประชุม…", emptyTitle: "เริ่มการประชุมแรกของคุณที่นี่", emptyText: "สร้างห้อง แล้วระบบจะสร้างลิงก์เชิญลูกค้าให้โดยอัตโนมัติ",
    createMeeting: "สร้างการประชุม", clientLink: "ลิงก์ลูกค้า", joinRoom: "เข้าร่วมห้อง", end: "สิ้นสุด", completedTime: "เสร็จสิ้น", limit: "จำกัด 60 นาที", endingNow: "กำลังสิ้นสุด", remaining: "ที่เหลือ",
    createTitle: "สร้างการประชุม", createSubtitle: "ระบบจะสร้างลิงก์ส่วนตัวแบบใช้ครั้งเดียวสำหรับลูกค้าพร้อมกับห้อง", meetingTitle: "ชื่อการประชุม", meetingPlaceholder: "ปรึกษาโครงการกับลูกค้า",
    clientName: "ชื่อลูกค้า", clientDefault: "ลูกค้า", clientLanguage: "ภาษาพูดของลูกค้า", english: "อังกฤษ", thai: "ไทย",
    protectionTitle: "การป้องกัน 60 นาที", protectionText: "คำเชิญและห้องจะหมดอายุโดยอัตโนมัติ ลูกค้าใช้วิดีโอและเสียงได้ แต่จะไม่เห็นคำบรรยายส่วนตัว",
    cancel: "ยกเลิก", creating: "กำลังสร้าง…", createAndLink: "สร้างและรับลิงก์", createLink: "สร้างลิงก์ลูกค้า", createLinkSubtitle: (title: string) => `สำหรับ “${title}” แต่ละลิงก์ให้ลูกค้าเข้าร่วมได้หนึ่งคนและใช้ได้ครั้งเดียว`,
    createLinkButton: "สร้างลิงก์", shareReadyTitle: "ลิงก์ลูกค้าพร้อมแล้ว", shareReadySubtitle: "ส่งลิงก์ส่วนตัวนี้ให้ลูกค้า ลิงก์ใช้ได้ครั้งเดียวและจะหมดอายุพร้อมการประชุม",
    readyToShare: "พร้อมแชร์", forGuest: "สำหรับ", expires: "หมดอายุ", copied: "คัดลอกแล้ว ✓", copyLink: "คัดลอกลิงก์ลูกค้า", share: "แชร์…", joinNow: "เข้าร่วมการประชุมตอนนี้",
    close: "ปิด", loadError: "ไม่สามารถโหลดการประชุมได้", createError: "ไม่สามารถสร้างการประชุมได้", linkError: "ไม่สามารถสร้างลิงก์ลูกค้าได้",
    partialError: "สร้างการประชุมแล้ว แต่ยังสร้างลิงก์ลูกค้าไม่สำเร็จ โปรดกด “ลิงก์ลูกค้า” บนการ์ดการประชุมเพื่อลองอีกครั้ง", endError: "ไม่สามารถสิ้นสุดการประชุมได้",
    endConfirm: (title: string) => `ต้องการสิ้นสุด “${title}” สำหรับทุกคนหรือไม่`, shareText: (title: string) => `เข้าร่วม ${title}`,
  },
} as const;

function readRole(): string | null {
  try {
    const token = localStorage.getItem("access_token");
    if (!token) return null;
    return JSON.parse(atob(token.split(".")[1].replace(/-/g, "+").replace(/_/g, "/"))).role ?? null;
  } catch {
    return null;
  }
}

function displayStatus(status: Meeting["status"], language: UiLanguage) {
  const copy = COPY[language];
  if (status === "active") return copy.live;
  if (status === "created") return copy.ready;
  return copy.ended;
}

function timeRemaining(meeting: Meeting, now: number, language: UiLanguage) {
  const copy = COPY[language];
  if (meeting.status === "ended") return copy.completedTime;
  if (!meeting.auto_end_at) return copy.limit;
  const milliseconds = new Date(meeting.auto_end_at).getTime() - now;
  if (milliseconds <= 0) return copy.endingNow;
  const minutes = Math.floor(milliseconds / 60000);
  const seconds = Math.floor((milliseconds % 60000) / 1000);
  return `${minutes}:${seconds.toString().padStart(2, "0")} ${copy.remaining}`;
}

export default function Dashboard() {
  const router = useRouter();
  const { language, setLanguage } = useUiLanguage();
  const copy = COPY[language];
  const [meetings, setMeetings] = useState<Meeting[]>([]);
  const [showCreate, setShowCreate] = useState(false);
  const [inviteMeeting, setInviteMeeting] = useState<Meeting | null>(null);
  const [share, setShare] = useState<ShareDetails | null>(null);
  const [title, setTitle] = useState("");
  const [guestName, setGuestName] = useState("Client");
  const [guestLanguage, setGuestLanguage] = useState<"en" | "th">("en");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [copied, setCopied] = useState(false);
  const [now, setNow] = useState(Date.now());
  const [role, setRole] = useState<string | null>(null);

  const fetchMeetings = useCallback(async () => {
    try {
      const res = await apiFetch("/api/meetings");
      if (!res.ok) throw new Error(COPY[language].loadError);
      setMeetings(await res.json());
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : COPY[language].loadError);
    } finally {
      setLoading(false);
    }
  }, [language]);

  useEffect(() => {
    setRole(readRole());
    fetchMeetings();
    const refresh = window.setInterval(fetchMeetings, 15000);
    const clock = window.setInterval(() => setNow(Date.now()), 1000);
    return () => { window.clearInterval(refresh); window.clearInterval(clock); };
  }, [fetchMeetings]);

  const stats = useMemo(() => ({
    live: meetings.filter((meeting) => meeting.status === "active").length,
    ready: meetings.filter((meeting) => meeting.status === "created").length,
    completed: meetings.filter((meeting) => meeting.status === "ended").length,
  }), [meetings]);

  function clientUrl(data: InviteResult) {
    return typeof window === "undefined" ? data.invite_url : `${window.location.origin}/join/${data.token}`;
  }

  async function issueInvite(meeting: Meeting, name: string, spokenLanguage: "en" | "th") {
    const res = await apiFetch(`/api/meetings/${meeting.id}/invites`, {
      method: "POST",
      body: JSON.stringify({ guest_name: name.trim(), expected_spoken_language: spokenLanguage, expires_in_hours: 1, max_uses: 1 }),
    });
    if (!res.ok) throw new Error(copy.linkError);
    const data: InviteResult = await res.json();
    setShare({ ...data, invite_url: clientUrl(data), meetingId: meeting.id, meetingTitle: meeting.title });
    setCopied(false);
  }

  async function createMeeting() {
    if (!title.trim() || !guestName.trim()) return;
    setSubmitting(true);
    setError(null);
    let meeting: Meeting | null = null;
    try {
      const res = await apiFetch("/api/meetings", {
        method: "POST",
        body: JSON.stringify({ title: title.trim(), guest_spoken_language: guestLanguage, expires_in_hours: 1 }),
      });
      if (!res.ok) throw new Error(copy.createError);
      meeting = await res.json();
      await issueInvite(meeting!, guestName, guestLanguage);
      setShowCreate(false);
      setTitle("");
      setGuestName(copy.clientDefault);
      await fetchMeetings();
    } catch (err) {
      setError(meeting ? copy.partialError : err instanceof Error ? err.message : copy.createError);
      if (meeting) {
        setShowCreate(false);
        await fetchMeetings();
      }
    } finally {
      setSubmitting(false);
    }
  }

  async function createLinkForExisting() {
    if (!inviteMeeting || !guestName.trim()) return;
    setSubmitting(true);
    setError(null);
    try {
      await issueInvite(inviteMeeting, guestName, guestLanguage);
      setInviteMeeting(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : copy.linkError);
    } finally {
      setSubmitting(false);
    }
  }

  async function copyLink() {
    if (!share) return;
    await navigator.clipboard.writeText(share.invite_url);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 2200);
  }

  async function shareLink() {
    if (!share) return;
    if (navigator.share) {
      await navigator.share({ title: share.meetingTitle, text: copy.shareText(share.meetingTitle), url: share.invite_url });
    } else {
      await copyLink();
    }
  }

  function openMeeting(meetingId: string) {
    sessionStorage.removeItem("guest_session_token");
    sessionStorage.removeItem("guest_identity");
    router.push(`/meeting/${meetingId}`);
  }

  async function endMeeting(meeting: Meeting) {
    if (!window.confirm(copy.endConfirm(meeting.title))) return;
    const res = await apiFetch(`/api/meetings/${meeting.id}/end`, { method: "POST" });
    if (!res.ok) {
      setError(copy.endError);
      return;
    }
    await fetchMeetings();
  }

  async function logout() {
    await apiFetch("/api/auth/logout", { method: "POST" }).catch(() => null);
    localStorage.removeItem("access_token");
    localStorage.removeItem("refresh_token");
    router.push("/login");
  }

  return (
    <main className="app-shell">
      <div className="mx-auto w-full max-w-6xl">
        <header className="flex items-center justify-between gap-3">
          <Brand href="/dashboard" />
          <div className="flex items-center gap-2">
            <span className="hidden rounded-full border border-white/10 bg-white/[0.035] px-3 py-2 text-xs text-slate-400 md:block">{copy.workspace}</span>
            <LanguageToggle language={language} onChange={setLanguage} compact />
            <button onClick={logout} className="ghost-button">{copy.signOut}</button>
          </div>
        </header>

        <section className="mt-12 flex flex-col justify-between gap-7 sm:flex-row sm:items-end">
          <div>
            <p className="eyebrow mb-3">{copy.eyebrow}</p>
            <h1 className="text-4xl font-semibold tracking-[-0.045em] text-white sm:text-5xl">{copy.heading}</h1>
            <p className="mt-3 max-w-xl text-sm leading-6 text-slate-400">{copy.intro}</p>
          </div>
          <button onClick={() => { setError(null); setGuestName(copy.clientDefault); setShowCreate(true); }} className="primary-button shrink-0 !px-5"><span className="text-lg leading-none">＋</span> {copy.newMeeting}</button>
        </section>

        <section className="mt-9 grid grid-cols-3 gap-3 sm:max-w-lg">
          {[
            { label: copy.liveNow, value: stats.live, color: "text-emerald-300" },
            { label: copy.ready, value: stats.ready, color: "text-cyan-300" },
            { label: copy.completed, value: stats.completed, color: "text-slate-300" },
          ].map((item) => (
            <div key={item.label} className="surface-panel rounded-2xl px-4 py-3.5"><p className={`text-2xl font-semibold ${item.color}`}>{item.value}</p><p className="mt-1 text-[11px] font-medium uppercase tracking-[0.12em] text-slate-600">{item.label}</p></div>
          ))}
        </section>

        {error && <div role="alert" className="mt-6 flex items-start justify-between rounded-2xl border border-rose-400/20 bg-rose-500/10 px-4 py-3 text-sm text-rose-200"><span>{error}</span><button onClick={() => setError(null)} className="ml-4 text-rose-300" aria-label={copy.close}>×</button></div>}

        <section className="mt-8 space-y-3">
          {loading && <div className="glass-panel rounded-2xl p-8 text-center text-sm text-slate-500">{copy.loading}</div>}
          {!loading && meetings.length === 0 && (
            <div className="glass-panel rounded-[1.75rem] px-6 py-16 text-center"><div className="mx-auto grid h-14 w-14 place-items-center rounded-2xl border border-cyan-400/15 bg-cyan-400/[0.07] text-2xl text-cyan-300">✦</div><h2 className="mt-5 text-xl font-semibold text-white">{copy.emptyTitle}</h2><p className="mx-auto mt-2 max-w-sm text-sm leading-6 text-slate-500">{copy.emptyText}</p><button onClick={() => { setGuestName(copy.clientDefault); setShowCreate(true); }} className="primary-button mt-6">{copy.createMeeting}</button></div>
          )}
          {meetings.map((meeting) => (
            <article key={meeting.id} className="glass-panel group rounded-2xl p-4 transition hover:border-white/20 sm:p-5">
              <div className="flex flex-col gap-5 sm:flex-row sm:items-center sm:justify-between">
                <button onClick={() => meeting.status !== "ended" && openMeeting(meeting.id)} className="min-w-0 flex-1 text-left disabled:cursor-default" disabled={meeting.status === "ended"}>
                  <div className="flex items-center gap-3">
                    <span className={`h-2.5 w-2.5 rounded-full ${meeting.status === "active" ? "bg-emerald-400 shadow-[0_0_14px_rgba(52,211,153,.7)]" : meeting.status === "created" ? "bg-cyan-400" : "bg-slate-700"}`} />
                    <h2 className="truncate text-[17px] font-semibold tracking-[-0.02em] text-white">{meeting.title}</h2>
                    <span className={`rounded-full px-2.5 py-1 text-[10px] font-semibold uppercase tracking-[0.12em] ${meeting.status === "active" ? "bg-emerald-400/10 text-emerald-300" : meeting.status === "created" ? "bg-cyan-400/10 text-cyan-300" : "bg-white/5 text-slate-500"}`}>{displayStatus(meeting.status, language)}</span>
                  </div>
                  <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 pl-5 text-xs text-slate-500"><span>{new Date(meeting.created_at).toLocaleString(language === "th" ? "th-TH" : "en-US", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" })}</span><span>·</span><span className={meeting.status !== "ended" ? "text-slate-400" : ""}>{timeRemaining(meeting, now, language)}</span></div>
                </button>
                <div className="flex flex-wrap items-center gap-2 sm:justify-end">
                  {meeting.status !== "ended" && <button onClick={() => { setGuestName(copy.clientDefault); setGuestLanguage("en"); setInviteMeeting(meeting); }} className="secondary-button !px-3.5 !py-2.5"><span aria-hidden>↗</span> {copy.clientLink}</button>}
                  {meeting.status !== "ended" && <button onClick={() => openMeeting(meeting.id)} className="primary-button !px-4 !py-2.5">{copy.joinRoom}</button>}
                  {role === "host" && meeting.status !== "ended" && <button onClick={() => endMeeting(meeting)} className="ghost-button !text-rose-300">{copy.end}</button>}
                </div>
              </div>
            </article>
          ))}
        </section>
      </div>

      {showCreate && (
        <Modal title={copy.createTitle} subtitle={copy.createSubtitle} closeLabel={copy.close} onClose={() => !submitting && setShowCreate(false)}>
          <div className="space-y-5">
            <div><label htmlFor="create-title" className="field-label">{copy.meetingTitle}</label><input id="create-title" autoFocus value={title} onChange={(event) => setTitle(event.target.value)} className="field" placeholder={copy.meetingPlaceholder} maxLength={255} /></div>
            <div><label htmlFor="create-client" className="field-label">{copy.clientName}</label><input id="create-client" value={guestName} onChange={(event) => setGuestName(event.target.value)} className="field" placeholder={copy.clientDefault} maxLength={100} /></div>
            <LanguageField value={guestLanguage} onChange={setGuestLanguage} language={language} />
            <div className="rounded-xl border border-cyan-400/10 bg-cyan-400/[0.055] p-3 text-xs leading-5 text-slate-400"><span className="font-semibold text-cyan-300">{copy.protectionTitle}</span> {copy.protectionText}</div>
            <div className="flex justify-end gap-3 pt-1"><button onClick={() => setShowCreate(false)} disabled={submitting} className="secondary-button">{copy.cancel}</button><button onClick={createMeeting} disabled={!title.trim() || !guestName.trim() || submitting} className="primary-button">{submitting ? copy.creating : copy.createAndLink}</button></div>
          </div>
        </Modal>
      )}

      {inviteMeeting && (
        <Modal title={copy.createLink} subtitle={copy.createLinkSubtitle(inviteMeeting.title)} closeLabel={copy.close} onClose={() => !submitting && setInviteMeeting(null)}>
          <div className="space-y-5">
            <div><label htmlFor="invite-client" className="field-label">{copy.clientName}</label><input id="invite-client" autoFocus value={guestName} onChange={(event) => setGuestName(event.target.value)} className="field" maxLength={100} /></div>
            <LanguageField value={guestLanguage} onChange={setGuestLanguage} language={language} />
            <div className="flex justify-end gap-3"><button onClick={() => setInviteMeeting(null)} className="secondary-button">{copy.cancel}</button><button onClick={createLinkForExisting} disabled={!guestName.trim() || submitting} className="primary-button">{submitting ? copy.creating : copy.createLinkButton}</button></div>
          </div>
        </Modal>
      )}

      {share && (
        <Modal title={copy.shareReadyTitle} subtitle={copy.shareReadySubtitle} closeLabel={copy.close} onClose={() => setShare(null)}>
          <div className="rounded-2xl border border-emerald-400/15 bg-emerald-400/[0.06] p-4">
            <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.14em] text-emerald-300"><span className="grid h-5 w-5 place-items-center rounded-full bg-emerald-400/15">✓</span> {copy.readyToShare}</div>
            <p className="mt-3 break-all rounded-xl bg-slate-950/60 p-3 font-mono text-xs leading-5 text-slate-300">{share.invite_url}</p>
            <p className="mt-3 text-xs text-slate-500">{copy.forGuest} {share.guest_name} · {copy.expires} {new Date(share.expires_at).toLocaleString(language === "th" ? "th-TH" : "en-US")}</p>
          </div>
          <div className="mt-5 grid gap-3 sm:grid-cols-2"><button onClick={copyLink} className="primary-button">{copied ? copy.copied : copy.copyLink}</button><button onClick={shareLink} className="secondary-button">{copy.share}</button></div>
          <button onClick={() => { const meetingId = share.meetingId; setShare(null); openMeeting(meetingId); }} className="ghost-button mt-4 w-full">{copy.joinNow} <span aria-hidden>→</span></button>
        </Modal>
      )}
    </main>
  );
}

function LanguageField({ value, onChange, language }: { value: "en" | "th"; onChange: (language: "en" | "th") => void; language: UiLanguage }) {
  const copy = COPY[language];
  return (
    <div><label className="field-label">{copy.clientLanguage}</label><div className="grid grid-cols-2 gap-2 rounded-xl bg-slate-950/50 p-1.5">
      <button type="button" onClick={() => onChange("en")} className={`rounded-lg px-4 py-2.5 text-sm font-medium transition ${value === "en" ? "bg-white/10 text-white shadow" : "text-slate-500 hover:text-slate-300"}`}>{copy.english}</button>
      <button type="button" onClick={() => onChange("th")} className={`rounded-lg px-4 py-2.5 text-sm font-medium transition ${value === "th" ? "bg-white/10 text-white shadow" : "text-slate-500 hover:text-slate-300"}`}>{copy.thai}</button>
    </div></div>
  );
}

function Modal({ title, subtitle, closeLabel, onClose, children }: { title: string; subtitle: string; closeLabel: string; onClose: () => void; children: React.ReactNode }) {
  return (
    <div className="fixed inset-0 z-[100] grid place-items-center bg-slate-950/75 p-4 backdrop-blur-sm" role="dialog" aria-modal="true">
      <div className="glass-panel animate-lift-in w-full max-w-lg rounded-[1.75rem] p-6 sm:p-7">
        <div className="mb-6 flex items-start justify-between gap-6"><div><h2 className="text-2xl font-semibold tracking-[-0.03em] text-white">{title}</h2><p className="mt-2 text-sm leading-6 text-slate-500">{subtitle}</p></div><button onClick={onClose} className="grid h-9 w-9 shrink-0 place-items-center rounded-full bg-white/5 text-xl text-slate-500 transition hover:bg-white/10 hover:text-white" aria-label={closeLabel}>×</button></div>
        {children}
      </div>
    </div>
  );
}
