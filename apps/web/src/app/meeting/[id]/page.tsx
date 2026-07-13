"use client";

import { useEffect, useRef, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { apiFetch, getApiUrl } from "@/lib/api";

import {
  LiveKitRoom,
  GridLayout,
  ParticipantTile,
  RoomAudioRenderer,
  ControlBar,
  useTracks,
  TrackReference,
} from "@livekit/components-react";
import { Track } from "livekit-client";
import "@livekit/components-styles";

export default function MeetingRoom() {
  const { id: meetingId } = useParams<{ id: string }>();
  const router = useRouter();

  const [token, setToken] = useState<string | null>(null);
  const [wsUrl, setWsUrl] = useState<string>("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [systemAlerts, setSystemAlerts] = useState<{ id: string; message: string }[]>([]);

  const [captionText, setCaptionText] = useState("");
  const [captionSpeaker, setCaptionSpeaker] = useState("");
  const [captionsEnabled, setCaptionsEnabled] = useState(true);
  
  const [systemLogs, setSystemLogs] = useState<{ id: string; type: string; message: string; time: string }[]>([]);
  const [isLogPanelOpen, setIsLogPanelOpen] = useState(false);
  const reconnectRef = useRef<number>(0);
  const MAX_RECONNECT = 5;

  // Fetch LiveKit token
  useEffect(() => {
    async function fetchToken() {
      try {
        const isGuest = !!sessionStorage.getItem("guest_session_token");
        if (isGuest) {
          const gt = sessionStorage.getItem("guest_session_token")!;
          const dn = sessionStorage.getItem("display_name") || "Guest";
          const res = await apiFetch(`/api/meetings/${meetingId}/livekit-token/guest`, {
            method: "POST", body: JSON.stringify({ guest_session_token: gt, display_name: dn }),
          });
          if (!res.ok) throw new Error("Failed");
          const d = await res.json();
          setToken(d.token); setWsUrl(d.ws_url);
        } else {
          const res = await apiFetch(`/api/meetings/${meetingId}/livekit-token`, { method: "POST" });
          if (!res.ok) throw new Error("Failed");
          const d = await res.json();
          setToken(d.token); setWsUrl(d.ws_url);
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to connect");
      } finally {
        setLoading(false);
      }
    }
    fetchToken();
  }, [meetingId]);

  // Caption WebSocket with auto-reconnect
  useEffect(() => {
    const isGuest = !!sessionStorage.getItem("guest_session_token");
    if (isGuest) return;

    let ws: WebSocket | null = null;
    let closed = false;

    function connect() {
      if (closed || reconnectRef.current >= MAX_RECONNECT) return;
      const at = localStorage.getItem("access_token");
      if (!at) return;
      
      const apiBase = getApiUrl().replace(/^http/, "ws");
      ws = new WebSocket(`${apiBase}/api/ws/meetings/${meetingId}/captions?token=${at}`);

      ws.onopen = () => { reconnectRef.current = 0; };
      ws.onclose = (event) => {
        if (!closed) {
          if (event.code >= 4000) {
            // Potentially expired token. Trigger apiFetch to auto-refresh it
            apiFetch(`/api/meetings/${meetingId}`).catch(console.error);
          }
          reconnectRef.current += 1;
          const delay = Math.min(1000 * (2 ** reconnectRef.current), 10000);
          setTimeout(connect, delay);
        }
      };
      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          if (data.type === "caption.delta" || data.type === "caption.final") {
            setCaptionText(data.translated_text);
            setCaptionSpeaker(data.speaker_name);
          } else if (data.type === "system.error" || data.type === "system.info") {
            const newLog = {
              id: Date.now().toString() + Math.random(),
              type: data.type,
              message: data.message,
              time: new Date().toLocaleTimeString(),
            };
            setSystemLogs((prev) => [...prev, newLog]);
            
            if (data.type === "system.error") {
              setSystemAlerts((prev) => [...prev, { id: newLog.id, message: data.message }]);
            }
          }
        } catch {}
      };
      ws.onerror = () => ws?.close();
    }

    connect();
    return () => { closed = true; ws?.close(); };
  }, [meetingId]);

  if (error) {
    return (
      <main className="min-h-screen flex items-center justify-center p-8 bg-slate-950">
        <div className="text-center space-y-4">
          <p className="text-red-400">{error}</p>
          <button onClick={() => router.push("/dashboard")} className="px-4 py-2 bg-slate-700 text-white rounded-lg">Back</button>
        </div>
      </main>
    );
  }

  if (loading || !token) {
    return (
      <main className="min-h-screen flex items-center justify-center p-8 bg-slate-950">
        <p className="text-slate-400">Connecting to meeting...</p>
      </main>
    );
  }

  return (
    <main className="min-h-screen bg-slate-950">
      <LiveKitRoom token={token} serverUrl={wsUrl} connect={true} video={true} audio={true}
        data-lk-theme="default" style={{ height: "100vh" }} onDisconnected={() => router.push("/dashboard")}>
        <div className="flex flex-col h-full">
          <div className="flex-1">
            <MeetingVideoGrid />
          </div>
          {captionsEnabled && captionText && !sessionStorage.getItem("guest_session_token") && (
            <div className="fixed bottom-20 left-1/2 -translate-x-1/2 bg-slate-900/85 text-white px-6 py-3 rounded-lg max-w-2xl text-center text-lg font-medium shadow-lg backdrop-blur-sm z-50">
              <span className="text-xs text-slate-400 mb-1 block">{captionSpeaker}</span>
              {captionText}
            </div>
          )}
          {systemAlerts.length > 0 && !sessionStorage.getItem("guest_session_token") && (
            <div className="fixed top-20 right-8 z-50 flex flex-col gap-2 max-w-sm">
              {systemAlerts.map((alert) => (
                <div key={alert.id} className="bg-red-900/90 text-white px-4 py-3 rounded shadow-lg backdrop-blur flex justify-between items-start gap-4 border border-red-500/50">
                  <div className="text-sm font-medium">{alert.message}</div>
                  <button onClick={() => setSystemAlerts(prev => prev.filter(a => a.id !== alert.id))} className="text-red-200 hover:text-white mt-0.5">
                    &times;
                  </button>
                </div>
              ))}
            </div>
          )}
          
          {/* System Logs Panel Toggle */}
          {!sessionStorage.getItem("guest_session_token") && (
            <button 
              onClick={() => setIsLogPanelOpen(!isLogPanelOpen)}
              className="fixed top-6 right-6 z-40 bg-slate-800 hover:bg-slate-700 text-white px-4 py-2 rounded-lg text-sm font-medium shadow border border-slate-600 transition-colors"
            >
              {isLogPanelOpen ? "Close Logs" : "View System Logs"}
            </button>
          )}

          {/* System Logs Sidebar */}
          {isLogPanelOpen && !sessionStorage.getItem("guest_session_token") && (
            <div className="fixed top-0 right-0 bottom-0 w-96 bg-slate-900/95 border-l border-slate-700 shadow-2xl z-40 flex flex-col backdrop-blur-xl">
              <div className="p-4 border-b border-slate-700 flex justify-between items-center">
                <h3 className="text-white font-medium">System Diagnostics Logs</h3>
                <button onClick={() => setSystemLogs([])} className="text-xs text-slate-400 hover:text-white">Clear</button>
              </div>
              <div className="flex-1 overflow-y-auto p-4 flex flex-col gap-3">
                {systemLogs.length === 0 ? (
                  <p className="text-slate-500 text-sm italic text-center mt-10">No system events received.</p>
                ) : (
                  systemLogs.map((log) => (
                    <div key={log.id} className={`p-3 rounded border text-sm ${log.type === 'system.error' ? 'bg-red-950/50 border-red-800 text-red-200' : 'bg-slate-800/50 border-slate-700 text-slate-300'}`}>
                      <div className="flex justify-between items-start mb-1 opacity-70 text-xs">
                        <span className="uppercase tracking-wider">{log.type.split('.')[1]}</span>
                        <span>{log.time}</span>
                      </div>
                      <div className="font-mono">{log.message}</div>
                    </div>
                  ))
                )}
              </div>
            </div>
          )}

          <RoomAudioRenderer />
          <div className="bg-slate-900 border-t border-slate-700"><ControlBar /></div>
        </div>
      </LiveKitRoom>
    </main>
  );
}

function MeetingVideoGrid() {
  const tracks = useTracks(
    [{ source: Track.Source.Camera, withPlaceholder: true }, { source: Track.Source.ScreenShare, withPlaceholder: false }],
    { onlySubscribed: false }
  ).filter((t) => !t.participant.identity.startsWith("agent"));
  return (
    <GridLayout tracks={tracks} style={{ height: "100%" }}>
      <ParticipantTile />
    </GridLayout>
  );
}
