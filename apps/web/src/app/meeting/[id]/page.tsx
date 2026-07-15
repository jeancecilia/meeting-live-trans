"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { apiFetch, getApiUrl } from "@/lib/api";
import {
  LiveKitRoom,
  GridLayout,
  ParticipantTile,
  RoomAudioRenderer,
  ControlBar,
  useTracks,
} from "@livekit/components-react";
import { Track } from "livekit-client";
import "@livekit/components-styles";

interface MeetingInfo {
  id: string;
  title: string;
  status: "created" | "active" | "ended";
  auto_end_at: string | null;
  max_duration_minutes: number;
}

interface CaptionLine {
  id: string;
  speaker: string;
  text: string;
  isFinal: boolean;
}

interface SystemLog {
  id: string;
  type: string;
  message: string;
  time: string;
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

function formatCountdown(deadline: string | null, now: number) {
  if (!deadline) return "60:00";
  const remaining = Math.max(0, new Date(deadline).getTime() - now);
  const minutes = Math.floor(remaining / 60000);
  const seconds = Math.floor((remaining % 60000) / 1000);
  return `${minutes}:${seconds.toString().padStart(2, "0")}`;
}

export default function MeetingRoom() {
  const { id: meetingId } = useParams<{ id: string }>();
  const router = useRouter();
  const [token, setToken] = useState<string | null>(null);
  const [wsUrl, setWsUrl] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [isGuest, setIsGuest] = useState(false);
  const [role, setRole] = useState<string | null>(null);
  const [meeting, setMeeting] = useState<MeetingInfo | null>(null);
  const [now, setNow] = useState(Date.now());
  const [ending, setEnding] = useState(false);
  const [currentCaption, setCurrentCaption] = useState<CaptionLine | null>(null);
  const [captionHistory, setCaptionHistory] = useState<CaptionLine[]>([]);
  const [captionsEnabled, setCaptionsEnabled] = useState(true);
  const [fontSize, setFontSize] = useState<"small" | "medium" | "large">("medium");
  const [translationStatus, setTranslationStatus] = useState<"connecting" | "ready" | "reconnecting" | "unavailable">("connecting");
  const [systemAlerts, setSystemAlerts] = useState<{ id: string; message: string }[]>([]);
  const [systemLogs, setSystemLogs] = useState<SystemLog[]>([]);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const reconnectRef = useRef(0);

  const updateMeeting = useCallback(async () => {
    const res = await apiFetch(`/api/meetings/${meetingId}`);
    if (res.ok) setMeeting(await res.json());
  }, [meetingId]);

  useEffect(() => {
    const clock = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(clock);
  }, []);

  useEffect(() => {
    async function connectToMeeting() {
      const guestSession = sessionStorage.getItem("guest_session_token");
      const guest = Boolean(guestSession);
      setIsGuest(guest);
      setRole(guest ? "guest" : readRole());

      try {
        if (guest) {
          setMeeting({
            id: meetingId,
            title: sessionStorage.getItem("meeting_title") || "Private meeting",
            status: "active",
            auto_end_at: sessionStorage.getItem("meeting_auto_end_at"),
            max_duration_minutes: 60,
          });
          const res = await apiFetch(`/api/meetings/${meetingId}/livekit-token/guest`, {
            method: "POST",
            body: JSON.stringify({ guest_session_token: guestSession, display_name: sessionStorage.getItem("display_name") || "Client" }),
          });
          if (!res.ok) {
            const data = await res.json().catch(() => null);
            throw new Error(data?.detail || "This client session is no longer valid.");
          }
          const data = await res.json();
          setToken(data.token);
          setWsUrl(data.ws_url);
        } else {
          await updateMeeting();
          const res = await apiFetch(`/api/meetings/${meetingId}/livekit-token`, { method: "POST" });
          if (!res.ok) {
            const data = await res.json().catch(() => null);
            throw new Error(data?.detail || "Could not connect to the meeting.");
          }
          const data = await res.json();
          setToken(data.token);
          setWsUrl(data.ws_url);
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : "Could not connect to the meeting.");
      } finally {
        setLoading(false);
      }
    }
    connectToMeeting();
  }, [meetingId, updateMeeting]);

  useEffect(() => {
    if (isGuest || !token) return;
    const poll = window.setInterval(updateMeeting, 15000);
    return () => window.clearInterval(poll);
  }, [isGuest, token, updateMeeting]);

  useEffect(() => {
    if (isGuest || !token) return;
    let ws: WebSocket | null = null;
    let closed = false;
    let reconnectTimer: ReturnType<typeof setTimeout> | null = null;

    function connect() {
      if (closed || reconnectRef.current >= 5) {
        if (!closed) setTranslationStatus("unavailable");
        return;
      }
      const accessToken = localStorage.getItem("access_token");
      if (!accessToken) return;
      setTranslationStatus(reconnectRef.current > 0 ? "reconnecting" : "connecting");
      const apiBase = getApiUrl().replace(/^http/, "ws");
      ws = new WebSocket(`${apiBase}/api/ws/meetings/${meetingId}/captions?token=${accessToken}`);

      ws.onopen = () => {
        reconnectRef.current = 0;
        setTranslationStatus("ready");
      };
      ws.onclose = (event) => {
        if (closed) return;
        setTranslationStatus("reconnecting");
        if (event.code >= 4000) apiFetch(`/api/meetings/${meetingId}`).catch(() => null);
        reconnectRef.current += 1;
        reconnectTimer = setTimeout(connect, Math.min(1000 * 2 ** reconnectRef.current, 10000));
      };
      ws.onerror = () => ws?.close();
      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          if (data.type === "caption.delta" || data.type === "caption.final") {
            const id = data.event_id || `${data.speaker_id}-${data.sequence}`;
            const line = { id, speaker: data.speaker_name, text: data.translated_text, isFinal: data.type === "caption.final" || Boolean(data.is_final) };
            setCurrentCaption(line);
            if (line.isFinal) {
              setCaptionHistory((previous) => [...previous.filter((item) => item.id !== id), line].slice(-3));
            }
          } else if (data.type === "system.error" || data.type === "system.info") {
            const log = { id: `${Date.now()}-${Math.random()}`, type: data.type, message: data.message, time: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) };
            setSystemLogs((previous) => [...previous, log].slice(-12));
            if (data.type === "system.error") {
              setTranslationStatus("unavailable");
              setSystemAlerts((previous) => [...previous, { id: log.id, message: data.message }]);
            }
          }
        } catch {
          // Ignore malformed events rather than disrupting the call.
        }
      };
    }

    connect();
    return () => {
      closed = true;
      if (reconnectTimer) clearTimeout(reconnectTimer);
      ws?.close();
    };
  }, [isGuest, meetingId, token]);

  const countdown = formatCountdown(meeting?.auto_end_at ?? null, now);
  const deadlineReached = Boolean(meeting?.auto_end_at && new Date(meeting.auto_end_at).getTime() <= now);
  const previousCaptions = useMemo(() => captionHistory.filter((line) => line.id !== currentCaption?.id).slice(-2), [captionHistory, currentCaption?.id]);
  const captionSize = fontSize === "small" ? "text-base" : fontSize === "large" ? "text-2xl" : "text-xl";

  function handleDisconnected() {
    if (isGuest) {
      ["guest_session_token", "guest_identity", "display_name", "meeting_id", "meeting_title", "meeting_auto_end_at", "spoken_language"].forEach((key) => sessionStorage.removeItem(key));
      router.push("/");
    } else {
      router.push("/dashboard");
    }
  }

  async function endMeeting() {
    if (!window.confirm("End this meeting for everyone?")) return;
    setEnding(true);
    const res = await apiFetch(`/api/meetings/${meetingId}/end`, { method: "POST" });
    if (!res.ok) {
      const data = await res.json().catch(() => null);
      setSystemAlerts((previous) => [...previous, { id: `${Date.now()}`, message: data?.detail || "The meeting could not be ended." }]);
      setEnding(false);
    }
  }

  if (error) {
    return <MeetingState title="Unable to join" message={error} action={() => router.push(isGuest ? "/" : "/dashboard")} actionLabel={isGuest ? "Return home" : "Back to meetings"} />;
  }
  if (loading || !token) {
    return <MeetingState title="Preparing your room" message="Connecting secure video, audio, and translation…" loading />;
  }

  return (
    <main className="meeting-shell min-h-screen bg-[#070b14]">
      <LiveKitRoom token={token} serverUrl={wsUrl} connect video audio data-lk-theme="default" style={{ height: "100vh" }} onDisconnected={handleDisconnected}>
        <div className="relative flex h-full flex-col overflow-hidden">
          <header className="pointer-events-none fixed inset-x-0 top-0 z-40 flex items-center justify-between gap-3 border-b border-white/10 bg-slate-950/75 px-4 py-3 backdrop-blur-xl sm:px-6">
            <div className="pointer-events-auto flex min-w-0 items-center gap-3">
              <button onClick={handleDisconnected} className="grid h-9 w-9 shrink-0 place-items-center rounded-xl border border-white/10 bg-white/5 text-slate-400 transition hover:text-white" aria-label="Leave room">←</button>
              <div className="min-w-0"><h1 className="truncate text-sm font-semibold text-white sm:text-base">{meeting?.title || "Private meeting"}</h1><div className="mt-0.5 flex items-center gap-2 text-[10px] font-medium uppercase tracking-[0.12em] text-slate-500"><span className="h-1.5 w-1.5 rounded-full bg-emerald-400 shadow-[0_0_10px_rgba(52,211,153,.7)]" /> Live · Secure</div></div>
            </div>

            <div className="pointer-events-auto flex items-center gap-2">
              <div className={`hidden items-center gap-2 rounded-xl border px-3 py-2 text-xs sm:flex ${deadlineReached ? "border-amber-400/20 bg-amber-400/10 text-amber-200" : "border-white/10 bg-white/5 text-slate-300"}`}><span className="text-slate-500">Ends in</span><span className="font-mono font-semibold tabular-nums">{deadlineReached ? "Ending…" : countdown}</span></div>
              {!isGuest && <button onClick={() => setSettingsOpen((open) => !open)} className={`secondary-button !px-3 !py-2 ${settingsOpen ? "!border-cyan-400/30 !text-cyan-200" : ""}`}><span className="rounded bg-white/10 px-1 text-[10px]">CC</span><span className="hidden sm:inline">Captions</span></button>}
              {role === "host" && <button onClick={endMeeting} disabled={ending} className="danger-button !px-3 !py-2"><span className="hidden sm:inline">{ending ? "Ending…" : "End meeting"}</span><span className="sm:hidden">End</span></button>}
            </div>
          </header>

          <div className="min-h-0 flex-1"><MeetingVideoGrid /></div>

          {!isGuest && captionsEnabled && currentCaption?.text && (
            <div className="caption-overlay">
              {previousCaptions.map((line) => <p key={line.id} className="mb-1 truncate text-xs text-slate-500"><span className="font-medium text-slate-400">{line.speaker}:</span> {line.text}</p>)}
              <span className="caption-speaker">{currentCaption.speaker}</span>
              <p className={`${captionSize} font-medium leading-snug tracking-[-0.01em]`}>{currentCaption.text}</p>
              {!currentCaption.isFinal && <span className="mt-2 inline-flex items-center gap-1 text-[10px] text-slate-500"><span className="h-1 w-1 animate-pulse rounded-full bg-cyan-300" /> Translating</span>}
            </div>
          )}

          {systemAlerts.length > 0 && !isGuest && (
            <div className="fixed right-4 top-20 z-50 flex max-w-sm flex-col gap-2">
              {systemAlerts.map((alert) => <div key={alert.id} className="flex items-start gap-3 rounded-xl border border-rose-400/25 bg-rose-950/90 px-4 py-3 text-sm text-rose-100 shadow-2xl backdrop-blur"><span className="mt-0.5 text-rose-300">!</span><span className="flex-1">{alert.message}</span><button onClick={() => setSystemAlerts((previous) => previous.filter((item) => item.id !== alert.id))} className="text-rose-300">×</button></div>)}
            </div>
          )}

          {settingsOpen && !isGuest && (
            <aside className="fixed right-4 top-20 z-40 w-[min(360px,calc(100vw-2rem))] rounded-2xl border border-white/10 bg-slate-950/95 p-5 shadow-2xl backdrop-blur-xl">
              <div className="flex items-center justify-between"><div><h2 className="font-semibold text-white">Private captions</h2><p className="mt-1 text-xs text-slate-500">Only authorized internal users receive these.</p></div><button onClick={() => setSettingsOpen(false)} className="text-xl text-slate-500 hover:text-white">×</button></div>
              <div className="mt-5 flex items-center justify-between rounded-xl border border-white/10 bg-white/[0.025] p-3"><div className="flex items-center gap-2"><span className={`h-2 w-2 rounded-full ${translationStatus === "ready" ? "bg-emerald-400" : translationStatus === "unavailable" ? "bg-rose-400" : "animate-pulse bg-amber-300"}`} /><span className="text-sm capitalize text-slate-300">{translationStatus === "ready" ? "Translation ready" : translationStatus}</span></div><button onClick={() => setCaptionsEnabled((enabled) => !enabled)} className={`rounded-lg px-3 py-1.5 text-xs font-semibold transition ${captionsEnabled ? "bg-cyan-400 text-slate-950" : "bg-white/10 text-slate-400"}`}>{captionsEnabled ? "On" : "Off"}</button></div>
              <div className="mt-4"><p className="mb-2 text-xs font-medium text-slate-500">Caption size</p><div className="grid grid-cols-3 gap-1 rounded-xl bg-white/[0.035] p-1">{(["small", "medium", "large"] as const).map((size) => <button key={size} onClick={() => setFontSize(size)} className={`rounded-lg py-2 text-xs capitalize transition ${fontSize === size ? "bg-white/10 text-white" : "text-slate-500 hover:text-slate-300"}`}>{size}</button>)}</div></div>
              {systemLogs.length > 0 && <div className="mt-5 border-t border-white/10 pt-4"><p className="text-[10px] font-semibold uppercase tracking-[0.14em] text-slate-600">Recent service activity</p><div className="mt-2 max-h-28 space-y-2 overflow-y-auto">{systemLogs.slice(-4).map((log) => <div key={log.id} className="flex gap-2 text-[11px] leading-4 text-slate-500"><span className="shrink-0 font-mono text-slate-600">{log.time}</span><span>{log.message}</span></div>)}</div></div>}
            </aside>
          )}

          <RoomAudioRenderer />
          <ControlBar />
        </div>
      </LiveKitRoom>
    </main>
  );
}

function MeetingVideoGrid() {
  const tracks = useTracks(
    [{ source: Track.Source.Camera, withPlaceholder: true }, { source: Track.Source.ScreenShare, withPlaceholder: false }],
    { onlySubscribed: false },
  ).filter((track) => !track.participant.identity.startsWith("agent"));
  return <GridLayout tracks={tracks} style={{ height: "100%" }}><ParticipantTile /></GridLayout>;
}

function MeetingState({ title, message, loading = false, action, actionLabel }: { title: string; message: string; loading?: boolean; action?: () => void; actionLabel?: string }) {
  return <main className="grid min-h-screen place-items-center p-6"><div className="glass-panel max-w-md rounded-[1.75rem] p-9 text-center">{loading ? <span className="mx-auto block h-9 w-9 animate-spin rounded-full border-2 border-cyan-400/20 border-t-cyan-300" /> : <span className="mx-auto grid h-12 w-12 place-items-center rounded-2xl bg-rose-400/10 text-xl text-rose-300">!</span>}<h1 className="mt-5 text-2xl font-semibold text-white">{title}</h1><p className="mt-3 text-sm leading-6 text-slate-400">{message}</p>{action && <button onClick={action} className="secondary-button mt-6">{actionLabel}</button>}</div></main>;
}
