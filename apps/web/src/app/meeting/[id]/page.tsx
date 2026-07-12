"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import { useParams, useRouter } from "next/navigation";
import { apiFetch, getApiUrl } from "@/lib/api";

import {
  LiveKitRoom,
  VideoConference,
  GridLayout,
  ParticipantTile,
  RoomAudioRenderer,
  ControlBar,
  useTracks,
  TrackReference,
} from "@livekit/components-react";
import { Room, Track } from "livekit-client";
import "@livekit/components-styles";

export default function MeetingRoom() {
  const { id: meetingId } = useParams<{ id: string }>();
  const router = useRouter();

  const [token, setToken] = useState<string | null>(null);
  const [wsUrl, setWsUrl] = useState<string>("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  // Fetch LiveKit token on mount
  useEffect(() => {
    async function fetchToken() {
      try {
        const isGuest = !!sessionStorage.getItem("guest_session_token");

        if (isGuest) {
          const guestToken = sessionStorage.getItem("guest_session_token")!;
          const displayName = sessionStorage.getItem("display_name") || "Guest";

          const res = await apiFetch(`/api/meetings/${meetingId}/livekit-token/guest`, {
            method: "POST",
            body: JSON.stringify({
              guest_session_token: guestToken,
              display_name: displayName,
            }),
          });
          if (!res.ok) throw new Error("Failed to get guest token");
          const data = await res.json();
          setToken(data.token);
          setWsUrl(data.ws_url);
        } else {
          const res = await apiFetch(`/api/meetings/${meetingId}/livekit-token`, {
            method: "POST",
          });
          if (!res.ok) throw new Error("Failed to get token");
          const data = await res.json();
          setToken(data.token);
          setWsUrl(data.ws_url);
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to connect");
      } finally {
        setLoading(false);
      }
    }
    fetchToken();
  }, [meetingId]);

  function handleLeave() {
    router.push("/dashboard");
  }

  if (error) {
    return (
      <main className="min-h-screen flex items-center justify-center p-8 bg-slate-950">
        <div className="text-center space-y-4">
          <p className="text-red-400">{error}</p>
          <button
            onClick={() => router.push("/dashboard")}
            className="px-4 py-2 bg-slate-700 text-white rounded-lg"
          >
            Back to Dashboard
          </button>
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
      <LiveKitRoom
        token={token}
        serverUrl={wsUrl}
        connect={true}
        video={true}
        audio={true}
        data-lk-theme="default"
        style={{ height: "100vh" }}
        onDisconnected={() => router.push("/dashboard")}
      >
        <div className="flex flex-col h-full">
          <div className="flex-1">
            <GridLayout tracks={[]}>
              <MeetingVideoGrid />
            </GridLayout>
          </div>
          <RoomAudioRenderer />
          <div className="bg-slate-900 border-t border-slate-700">
            <ControlBar />
          </div>
        </div>
      </LiveKitRoom>
    </main>
  );
}

function MeetingVideoGrid() {
  const tracks = useTracks(
    [
      { source: Track.Source.Camera, withPlaceholder: true },
      { source: Track.Source.ScreenShare, withPlaceholder: false },
    ],
    { onlySubscribed: false }
  );

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-2 p-4 auto-rows-fr h-full">
      {tracks.map((trackRef: TrackReference) => (
        <ParticipantTile key={trackRef.publication?.trackSid} trackRef={trackRef} />
      ))}
    </div>
  );
}
