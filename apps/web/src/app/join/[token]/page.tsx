"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { apiFetch } from "@/lib/api";

interface InvitePreview {
  guest_name: string;
  meeting_title: string;
  expected_spoken_language: string;
  expires_at: string;
  is_valid: boolean;
}

export default function JoinPage() {
  const { token } = useParams<{ token: string }>();
  const router = useRouter();
  const [preview, setPreview] = useState<InvitePreview | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [displayName, setDisplayName] = useState("");
  const [joining, setJoining] = useState(false);

  useEffect(() => {
    async function fetchPreview() {
      try {
        const res = await apiFetch(`/api/public/invites/${token}`);
        if (!res.ok) throw new Error("Invite not found or expired");
        setPreview(await res.json());
      } catch {
        setError("This invitation link is invalid or has expired.");
      }
    }
    fetchPreview();
  }, [token]);

  async function handleJoin() {
    if (!displayName.trim()) return;
    setJoining(true);
    try {
      const res = await apiFetch(`/api/public/invites/${token}/join`, {
        method: "POST",
        body: JSON.stringify({ display_name: displayName }),
      });
      if (!res.ok) throw new Error("Join failed");
      const data = await res.json();

      sessionStorage.setItem("guest_session_token", data.guest_session_token);
      sessionStorage.setItem("guest_identity", data.guest_identity);
      sessionStorage.setItem("display_name", displayName);
      sessionStorage.setItem("meeting_id", data.meeting_id);
      sessionStorage.setItem("spoken_language", preview?.expected_spoken_language || "en");
      router.push(`/meeting/${data.meeting_id}`);
    } catch {
      setError("Failed to join. Please try again.");
    } finally {
      setJoining(false);
    }
  }

  if (error) {
    return (
      <main className="flex min-h-screen items-center justify-center p-8">
        <div className="max-w-md text-center space-y-4">
          <div className="text-red-400 text-5xl mb-4">⚠</div>
          <h1 className="text-2xl font-bold text-slate-100">Cannot Join Meeting</h1>
          <p className="text-slate-400">{error}</p>
        </div>
      </main>
    );
  }

  if (!preview) {
    return (
      <main className="flex min-h-screen items-center justify-center p-8">
        <p className="text-slate-400">Loading invitation...</p>
      </main>
    );
  }

  if (!preview.is_valid) {
    return (
      <main className="flex min-h-screen items-center justify-center p-8">
        <div className="max-w-md text-center space-y-4">
          <h1 className="text-2xl font-bold text-slate-100">Invitation Expired</h1>
          <p className="text-slate-400">This invitation is no longer valid.</p>
        </div>
      </main>
    );
  }

  return (
    <main className="flex min-h-screen items-center justify-center p-8">
      <div className="w-full max-w-md space-y-6">
        <div className="text-center space-y-2">
          <h1 className="text-2xl font-bold text-slate-100">{preview.meeting_title}</h1>
          <p className="text-slate-400">
            You're invited as <span className="text-slate-200 font-medium">{preview.guest_name}</span>
          </p>
        </div>

        <div className="bg-slate-800 rounded-lg p-6 space-y-4">
          <div>
            <label className="block text-sm font-medium text-slate-300 mb-1">Your Display Name</label>
            <input
              type="text"
              value={displayName}
              onChange={(e) => setDisplayName(e.target.value)}
              placeholder={preview.guest_name}
              className="w-full px-4 py-2 bg-slate-900 border border-slate-600 rounded-lg text-slate-100 placeholder-slate-500 focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
            />
          </div>

          <div className="text-sm text-slate-400">
            Spoken language: <span className="text-slate-200 font-medium">{preview.expected_spoken_language === "en" ? "English" : "Thai"}</span>
          </div>

          <div className="bg-slate-700/50 rounded p-3 text-xs text-slate-400">
            This meeting uses automated speech transcription and translation.
            Audio is processed in real time. Meeting audio is not recorded by this application.
          </div>

          <button
            onClick={handleJoin}
            disabled={!displayName.trim() || joining}
            className="w-full py-3 px-4 bg-blue-600 hover:bg-blue-700 disabled:bg-slate-600 text-white font-medium rounded-lg transition-colors disabled:cursor-not-allowed"
          >
            {joining ? "Joining..." : "Join Meeting"}
          </button>
        </div>
      </div>
    </main>
  );
}
