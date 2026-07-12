"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import { useParams, useRouter } from "next/navigation";

interface Participant {
  identity: string;
  name: string;
  isSpeaking: boolean;
}

export default function MeetingRoom() {
  const { id: meetingId } = useParams<{ id: string }>();
  const router = useRouter();

  const [participants, setParticipants] = useState<Participant[]>([]);
  const [micEnabled, setMicEnabled] = useState(true);
  const [cameraEnabled, setCameraEnabled] = useState(true);
  const [screenSharing, setScreenSharing] = useState(false);
  const [connectionState, setConnectionState] = useState<
    "connecting" | "connected" | "disconnected"
  >("connecting");
  const [captionText, setCaptionText] = useState<string | null>(null);
  const [captionSpeaker, setCaptionSpeaker] = useState<string>("");
  const [captionsEnabled, setCaptionsEnabled] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const videoGridRef = useRef<HTMLDivElement>(null);

  // Simulated connection - in production, this uses LiveKit client SDK
  useEffect(() => {
    const timer = setTimeout(() => {
      setConnectionState("connected");
      setParticipants([
        { identity: "internal_en", name: "English Speaker (You)", isSpeaking: false },
        { identity: "internal_th", name: "Thai Speaker", isSpeaking: true },
        { identity: "guest_1", name: "Guest", isSpeaking: false },
      ]);
    }, 1500);
    return () => clearTimeout(timer);
  }, [meetingId]);

  const handleLeave = useCallback(() => {
    router.push("/");
  }, [router]);

  const handleToggleMic = () => setMicEnabled((p) => !p);
  const handleToggleCamera = () => setCameraEnabled((p) => !p);
  const handleToggleScreen = () => setScreenSharing((p) => !p);
  const handleToggleCaptions = () => setCaptionsEnabled((p) => !p);

  return (
    <div className="min-h-screen bg-slate-950 flex flex-col">
      {/* Connection status */}
      {connectionState !== "connected" && (
        <div className="absolute top-0 left-0 right-0 z-50">
          <div className="bg-yellow-600 text-white text-center py-2 text-sm">
            {connectionState === "connecting"
              ? "Connecting to meeting..."
              : "Connection lost. Reconnecting..."}
          </div>
        </div>
      )}

      {/* Video grid */}
      <div
        ref={videoGridRef}
        className="flex-1 grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-2 p-4 auto-rows-fr"
      >
        {participants.map((p) => (
          <div
            key={p.identity}
            className={`relative bg-slate-800 rounded-lg flex items-center justify-center min-h-[200px]
                        ${p.isSpeaking ? "ring-2 ring-blue-500" : ""}`}
          >
            <div className="text-center">
              <div className="w-16 h-16 bg-slate-600 rounded-full mx-auto mb-2 flex items-center justify-center text-2xl">
                {p.name.charAt(0)}
              </div>
              <p className="text-slate-200 text-sm font-medium">{p.name}</p>
              {p.isSpeaking && (
                <span className="text-xs text-blue-400 mt-1 block">
                  Speaking
                </span>
              )}
            </div>
          </div>
        ))}
      </div>

      {/* Caption overlay */}
      {captionsEnabled && captionText && (
        <div className="caption-overlay">
          <span className="caption-speaker">{captionSpeaker}</span>
          {captionText}
        </div>
      )}

      {/* Controls bar */}
      <div className="bg-slate-900 border-t border-slate-700 px-4 py-3">
        <div className="flex items-center justify-center gap-4 flex-wrap">
          <ControlButton
            icon={micEnabled ? "🎤" : "🔇"}
            label={micEnabled ? "Mute" : "Unmute"}
            active={micEnabled}
            onClick={handleToggleMic}
          />
          <ControlButton
            icon={cameraEnabled ? "📷" : "📷❌"}
            label={cameraEnabled ? "Camera" : "Camera Off"}
            active={cameraEnabled}
            onClick={handleToggleCamera}
          />
          <ControlButton
            icon="🖥"
            label={screenSharing ? "Stop Share" : "Share Screen"}
            active={screenSharing}
            onClick={handleToggleScreen}
          />
          <ControlButton
            icon="💬"
            label={captionsEnabled ? "Captions On" : "Captions Off"}
            active={captionsEnabled}
            onClick={handleToggleCaptions}
          />

          <div className="w-px h-8 bg-slate-700 mx-2" />

          <button
            onClick={handleLeave}
            className="px-4 py-2 bg-red-600 hover:bg-red-700 text-white text-sm
                       font-medium rounded-lg transition-colors"
          >
            Leave
          </button>
        </div>
      </div>
    </div>
  );
}

function ControlButton({
  icon,
  label,
  active,
  onClick,
}: {
  icon: string;
  label: string;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      className={`flex flex-col items-center gap-1 px-3 py-2 rounded-lg text-xs
                  transition-colors ${
                    active
                      ? "bg-slate-700 text-slate-100 hover:bg-slate-600"
                      : "bg-red-900/50 text-red-400 hover:bg-red-900"
                  }`}
    >
      <span className="text-lg">{icon}</span>
      <span>{label}</span>
    </button>
  );
}
