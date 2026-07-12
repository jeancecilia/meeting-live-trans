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

  const [captionText, setCaptionText] = useState("");
  const [captionSpeaker, setCaptionSpeaker] = useState("");
  const [captionsEnabled, setCaptionsEnabled] = useState(true);
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

    const at = localStorage.getItem("access_token");
    if (!at) return;

    let ws: WebSocket | null = null;
    let closed = false;

    function connect() {
      if (closed || reconnectRef.current >= MAX_RECONNECT) return;
      const apiBase = getApiUrl().replace(/^http/, "ws");
      ws = new WebSocket(`${apiBase}/api/ws/meetings/${meetingId}/captions?token=${at}`);

      ws.onopen = () => { reconnectRef.current = 0; };
      ws.onclose = () => {
        if (!closed) {
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
            <GridLayout tracks={[]}><MeetingVideoGrid /></GridLayout>
          </div>
          {captionsEnabled && captionText && !sessionStorage.getItem("guest_session_token") && (
            <div className="fixed bottom-20 left-1/2 -translate-x-1/2 bg-slate-900/85 text-white px-6 py-3 rounded-lg max-w-2xl text-center text-lg font-medium shadow-lg backdrop-blur-sm z-50">
              <span className="text-xs text-slate-400 mb-1 block">{captionSpeaker}</span>
              {captionText}
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
  );
  return (
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-2 p-4 auto-rows-fr h-full">
      {tracks.map((tr: TrackReference) => (
        <ParticipantTile key={tr.publication?.trackSid} trackRef={tr} />
      ))}
    </div>
  );
}
