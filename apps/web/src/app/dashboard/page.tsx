"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { apiFetch } from "@/lib/api";
import { Brand } from "@/components/Brand";

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

function readRole(): string | null {
  try {
    const token = localStorage.getItem("access_token");
    if (!token) return null;
    return JSON.parse(atob(token.split(".")[1].replace(/-/g, "+").replace(/_/g, "/"))).role ?? null;
  } catch {
    return null;
  }
}

function displayStatus(status: Meeting["status"]) {
  if (status === "active") return "Live";
  if (status === "created") return "Ready";
  return "Ended";
}

function timeRemaining(meeting: Meeting, now: number) {
  if (meeting.status === "ended") return "Completed";
  if (!meeting.auto_end_at) return "60 minute limit";
  const milliseconds = new Date(meeting.auto_end_at).getTime() - now;
  if (milliseconds <= 0) return "Ending now";
  const minutes = Math.floor(milliseconds / 60000);
  const seconds = Math.floor((milliseconds % 60000) / 1000);
  return `${minutes}:${seconds.toString().padStart(2, "0")} remaining`;
}

export default function Dashboard() {
  const router = useRouter();
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
      if (!res.ok) throw new Error("Could not load meetings");
      setMeetings(await res.json());
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load meetings");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    setRole(readRole());
    fetchMeetings();
    const refresh = window.setInterval(fetchMeetings, 15000);
    const clock = window.setInterval(() => setNow(Date.now()), 1000);
    return () => { window.clearInterval(refresh); window.clearInterval(clock); };
  }, [fetchMeetings]);

  const stats = useMemo(() => ({
    live: meetings.filter((m) => m.status === "active").length,
    ready: meetings.filter((m) => m.status === "created").length,
    completed: meetings.filter((m) => m.status === "ended").length,
  }), [meetings]);

  function clientUrl(data: InviteResult) {
    return typeof window === "undefined" ? data.invite_url : `${window.location.origin}/join/${data.token}`;
  }

  async function issueInvite(meeting: Meeting, name: string, language: "en" | "th") {
    const res = await apiFetch(`/api/meetings/${meeting.id}/invites`, {
      method: "POST",
      body: JSON.stringify({ guest_name: name.trim(), expected_spoken_language: language, expires_in_hours: 1, max_uses: 1 }),
    });
    if (!res.ok) {
      const data = await res.json().catch(() => null);
      throw new Error(data?.detail || "Could not create the client link");
    }
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
      if (!res.ok) throw new Error("Could not create the meeting");
      meeting = await res.json();
      await issueInvite(meeting!, guestName, guestLanguage);
      setShowCreate(false);
      setTitle("");
      setGuestName("Client");
      await fetchMeetings();
    } catch (err) {
      setError(meeting ? "The meeting was created, but its client link was not. Use “Client link” on the meeting card to retry." : err instanceof Error ? err.message : "Could not create the meeting");
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
      setError(err instanceof Error ? err.message : "Could not create the client link");
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
      await navigator.share({ title: share.meetingTitle, text: `Join ${share.meetingTitle}`, url: share.invite_url });
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
    if (!window.confirm(`End “${meeting.title}” for everyone?`)) return;
    const res = await apiFetch(`/api/meetings/${meeting.id}/end`, { method: "POST" });
    if (!res.ok) {
      const data = await res.json().catch(() => null);
      setError(data?.detail || "Could not end the meeting");
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
        <header className="flex items-center justify-between">
          <Brand href="/dashboard" />
          <div className="flex items-center gap-2">
            <span className="hidden rounded-full border border-white/10 bg-white/[0.035] px-3 py-2 text-xs text-slate-400 sm:block">Internal workspace</span>
            <button onClick={logout} className="ghost-button">Sign out</button>
          </div>
        </header>

        <section className="mt-12 flex flex-col justify-between gap-7 sm:flex-row sm:items-end">
          <div>
            <p className="eyebrow mb-3">Meeting workspace</p>
            <h1 className="text-4xl font-semibold tracking-[-0.045em] text-white sm:text-5xl">Your conversations</h1>
            <p className="mt-3 max-w-xl text-sm leading-6 text-slate-400">Create a room, copy the private client link, and join when you are ready. Every room closes automatically after 60 minutes.</p>
          </div>
          <button onClick={() => { setError(null); setShowCreate(true); }} className="primary-button shrink-0 !px-5"><span className="text-lg leading-none">＋</span> New meeting</button>
        </section>

        <section className="mt-9 grid grid-cols-3 gap-3 sm:max-w-lg">
          {[{ label: "Live now", value: stats.live, color: "text-emerald-300" }, { label: "Ready", value: stats.ready, color: "text-cyan-300" }, { label: "Completed", value: stats.completed, color: "text-slate-300" }].map((item) => (
            <div key={item.label} className="surface-panel rounded-2xl px-4 py-3.5"><p className={`text-2xl font-semibold ${item.color}`}>{item.value}</p><p className="mt-1 text-[11px] font-medium uppercase tracking-[0.12em] text-slate-600">{item.label}</p></div>
          ))}
        </section>

        {error && <div role="alert" className="mt-6 flex items-start justify-between rounded-2xl border border-rose-400/20 bg-rose-500/10 px-4 py-3 text-sm text-rose-200"><span>{error}</span><button onClick={() => setError(null)} className="ml-4 text-rose-300">×</button></div>}

        <section className="mt-8 space-y-3">
          {loading && <div className="glass-panel rounded-2xl p-8 text-center text-sm text-slate-500">Loading your meetings…</div>}
          {!loading && meetings.length === 0 && (
            <div className="glass-panel rounded-[1.75rem] px-6 py-16 text-center"><div className="mx-auto grid h-14 w-14 place-items-center rounded-2xl border border-cyan-400/15 bg-cyan-400/[0.07] text-2xl text-cyan-300">✦</div><h2 className="mt-5 text-xl font-semibold text-white">Your first meeting starts here</h2><p className="mx-auto mt-2 max-w-sm text-sm leading-6 text-slate-500">Create a room and we will generate the client invitation link automatically.</p><button onClick={() => setShowCreate(true)} className="primary-button mt-6">Create a meeting</button></div>
          )}
          {meetings.map((meeting) => (
            <article key={meeting.id} className="glass-panel group rounded-2xl p-4 transition hover:border-white/20 sm:p-5">
              <div className="flex flex-col gap-5 sm:flex-row sm:items-center sm:justify-between">
                <button onClick={() => meeting.status !== "ended" && openMeeting(meeting.id)} className="min-w-0 flex-1 text-left disabled:cursor-default" disabled={meeting.status === "ended"}>
                  <div className="flex items-center gap-3">
                    <span className={`h-2.5 w-2.5 rounded-full ${meeting.status === "active" ? "bg-emerald-400 shadow-[0_0_14px_rgba(52,211,153,.7)]" : meeting.status === "created" ? "bg-cyan-400" : "bg-slate-700"}`} />
                    <h2 className="truncate text-[17px] font-semibold tracking-[-0.02em] text-white">{meeting.title}</h2>
                    <span className={`rounded-full px-2.5 py-1 text-[10px] font-semibold uppercase tracking-[0.12em] ${meeting.status === "active" ? "bg-emerald-400/10 text-emerald-300" : meeting.status === "created" ? "bg-cyan-400/10 text-cyan-300" : "bg-white/5 text-slate-500"}`}>{displayStatus(meeting.status)}</span>
                  </div>
                  <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 pl-5 text-xs text-slate-500"><span>{new Date(meeting.created_at).toLocaleString([], { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" })}</span><span>·</span><span className={meeting.status !== "ended" ? "text-slate-400" : ""}>{timeRemaining(meeting, now)}</span></div>
                </button>
                <div className="flex flex-wrap items-center gap-2 sm:justify-end">
                  {meeting.status !== "ended" && <button onClick={() => { setGuestName("Client"); setGuestLanguage("en"); setInviteMeeting(meeting); }} className="secondary-button !px-3.5 !py-2.5"><span aria-hidden>↗</span> Client link</button>}
                  {meeting.status !== "ended" && <button onClick={() => openMeeting(meeting.id)} className="primary-button !px-4 !py-2.5">Join room</button>}
                  {role === "host" && meeting.status !== "ended" && <button onClick={() => endMeeting(meeting)} className="ghost-button !text-rose-300">End</button>}
                </div>
              </div>
            </article>
          ))}
        </section>
      </div>

      {showCreate && (
        <Modal title="Create a meeting" subtitle="A private, single-use client link will be created with the room." onClose={() => !submitting && setShowCreate(false)}>
          <div className="space-y-5">
            <div><label htmlFor="create-title" className="field-label">Meeting title</label><input id="create-title" autoFocus value={title} onChange={(e) => setTitle(e.target.value)} className="field" placeholder="Client project consultation" maxLength={255} /></div>
            <div><label htmlFor="create-client" className="field-label">Client name</label><input id="create-client" value={guestName} onChange={(e) => setGuestName(e.target.value)} className="field" placeholder="Client" maxLength={100} /></div>
            <LanguageField value={guestLanguage} onChange={setGuestLanguage} />
            <div className="rounded-xl border border-cyan-400/10 bg-cyan-400/[0.055] p-3 text-xs leading-5 text-slate-400"><span className="font-semibold text-cyan-300">60-minute protection.</span> The invitation and room expire automatically. The client gets video and audio access, never private captions.</div>
            <div className="flex justify-end gap-3 pt-1"><button onClick={() => setShowCreate(false)} disabled={submitting} className="secondary-button">Cancel</button><button onClick={createMeeting} disabled={!title.trim() || !guestName.trim() || submitting} className="primary-button">{submitting ? "Creating…" : "Create & get link"}</button></div>
          </div>
        </Modal>
      )}

      {inviteMeeting && (
        <Modal title="Create client link" subtitle={`For “${inviteMeeting.title}”. Each link admits one client once.`} onClose={() => !submitting && setInviteMeeting(null)}>
          <div className="space-y-5">
            <div><label htmlFor="invite-client" className="field-label">Client name</label><input id="invite-client" autoFocus value={guestName} onChange={(e) => setGuestName(e.target.value)} className="field" maxLength={100} /></div>
            <LanguageField value={guestLanguage} onChange={setGuestLanguage} />
            <div className="flex justify-end gap-3"><button onClick={() => setInviteMeeting(null)} className="secondary-button">Cancel</button><button onClick={createLinkForExisting} disabled={!guestName.trim() || submitting} className="primary-button">{submitting ? "Creating…" : "Create link"}</button></div>
          </div>
        </Modal>
      )}

      {share && (
        <Modal title="Client link is ready" subtitle="Send this private link to your client. It can be used once and expires with the meeting." onClose={() => setShare(null)}>
          <div className="rounded-2xl border border-emerald-400/15 bg-emerald-400/[0.06] p-4">
            <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.14em] text-emerald-300"><span className="grid h-5 w-5 place-items-center rounded-full bg-emerald-400/15">✓</span> Ready to share</div>
            <p className="mt-3 break-all rounded-xl bg-slate-950/60 p-3 font-mono text-xs leading-5 text-slate-300">{share.invite_url}</p>
            <p className="mt-3 text-xs text-slate-500">For {share.guest_name} · Expires {new Date(share.expires_at).toLocaleString()}</p>
          </div>
          <div className="mt-5 grid gap-3 sm:grid-cols-2"><button onClick={copyLink} className="primary-button">{copied ? "Copied ✓" : "Copy client link"}</button><button onClick={shareLink} className="secondary-button">Share…</button></div>
          <button onClick={() => { const id = share.meetingId; setShare(null); openMeeting(id); }} className="ghost-button mt-4 w-full">Join the meeting now <span aria-hidden>→</span></button>
        </Modal>
      )}
    </main>
  );
}

function LanguageField({ value, onChange }: { value: "en" | "th"; onChange: (language: "en" | "th") => void }) {
  return (
    <div><label className="field-label">Client’s spoken language</label><div className="grid grid-cols-2 gap-2 rounded-xl bg-slate-950/50 p-1.5">
      <button onClick={() => onChange("en")} className={`rounded-lg px-4 py-2.5 text-sm font-medium transition ${value === "en" ? "bg-white/10 text-white shadow" : "text-slate-500 hover:text-slate-300"}`}>English</button>
      <button onClick={() => onChange("th")} className={`rounded-lg px-4 py-2.5 text-sm font-medium transition ${value === "th" ? "bg-white/10 text-white shadow" : "text-slate-500 hover:text-slate-300"}`}>ไทย</button>
    </div></div>
  );
}

function Modal({ title, subtitle, onClose, children }: { title: string; subtitle: string; onClose: () => void; children: React.ReactNode }) {
  return (
    <div className="fixed inset-0 z-[100] grid place-items-center bg-slate-950/75 p-4 backdrop-blur-sm" role="dialog" aria-modal="true">
      <div className="glass-panel animate-lift-in w-full max-w-lg rounded-[1.75rem] p-6 sm:p-7">
        <div className="mb-6 flex items-start justify-between gap-6"><div><h2 className="text-2xl font-semibold tracking-[-0.03em] text-white">{title}</h2><p className="mt-2 text-sm leading-6 text-slate-500">{subtitle}</p></div><button onClick={onClose} className="grid h-9 w-9 shrink-0 place-items-center rounded-full bg-white/5 text-xl text-slate-500 transition hover:bg-white/10 hover:text-white" aria-label="Close">×</button></div>
        {children}
      </div>
    </div>
  );
}
