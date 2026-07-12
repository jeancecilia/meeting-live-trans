"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { apiFetch } from "@/lib/api";

interface Meeting {
  id: string;
  room_name: string;
  title: string;
  status: string;
  created_at: string;
}

export default function Dashboard() {
  const router = useRouter();
  const [meetings, setMeetings] = useState<Meeting[]>([]);
  const [showCreate, setShowCreate] = useState(false);
  const [title, setTitle] = useState("");
  const [guestLanguage, setGuestLanguage] = useState("en");
  const [expiresInHours, setExpiresInHours] = useState(24);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchMeetings();
  }, []);

  async function fetchMeetings() {
    try {
      const res = await apiFetch("/api/meetings");
      if (res.ok) setMeetings(await res.json());
    } catch {
      // Not authenticated yet
    }
  }

  async function createMeeting() {
    setError(null);
    try {
      const res = await apiFetch("/api/meetings", {
        method: "POST",
        body: JSON.stringify({
          title,
          guest_spoken_language: guestLanguage,
          expires_in_hours: expiresInHours,
        }),
      });
      if (!res.ok) throw new Error("Failed to create meeting");
      const meeting = await res.json();
      setShowCreate(false);
      setTitle("");
      fetchMeetings();
      router.push(`/meeting/${meeting.id}`);
    } catch {
      setError("Failed to create meeting. Please try again.");
    }
  }

  return (
    <main className="min-h-screen bg-slate-950 p-8">
      <div className="max-w-4xl mx-auto space-y-8">
        <div className="flex items-center justify-between">
          <h1 className="text-2xl font-bold text-slate-100">Dashboard</h1>
          <button
            onClick={() => setShowCreate(true)}
            className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white text-sm
                       font-medium rounded-lg transition-colors"
          >
            New Meeting
          </button>
        </div>

        {showCreate && (
          <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
            <div className="bg-slate-800 rounded-lg p-6 w-full max-w-md space-y-4">
              <h2 className="text-lg font-semibold text-slate-100">Create Meeting</h2>
              <div>
                <label className="block text-sm text-slate-300 mb-1">Meeting Title</label>
                <input
                  type="text"
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                  className="w-full px-4 py-2 bg-slate-900 border border-slate-600 rounded-lg
                             text-slate-100 focus:outline-none focus:border-blue-500"
                  placeholder="Client project consultation"
                />
              </div>
              <div>
                <label className="block text-sm text-slate-300 mb-1">Guest Spoken Language</label>
                <select
                  value={guestLanguage}
                  onChange={(e) => setGuestLanguage(e.target.value)}
                  className="w-full px-4 py-2 bg-slate-900 border border-slate-600 rounded-lg
                             text-slate-100 focus:outline-none focus:border-blue-500"
                >
                  <option value="en">English</option>
                  <option value="th">Thai</option>
                </select>
              </div>
              <div>
                <label className="block text-sm text-slate-300 mb-1">Invitation Expires In (hours)</label>
                <input
                  type="number"
                  value={expiresInHours}
                  onChange={(e) => setExpiresInHours(Number(e.target.value))}
                  className="w-full px-4 py-2 bg-slate-900 border border-slate-600 rounded-lg
                             text-slate-100 focus:outline-none focus:border-blue-500"
                />
              </div>
              {error && <p className="text-red-400 text-sm">{error}</p>}
              <div className="flex gap-3 justify-end">
                <button
                  onClick={() => setShowCreate(false)}
                  className="px-4 py-2 bg-slate-700 hover:bg-slate-600 text-slate-200
                             text-sm rounded-lg transition-colors"
                >
                  Cancel
                </button>
                <button
                  onClick={createMeeting}
                  disabled={!title.trim()}
                  className="px-4 py-2 bg-blue-600 hover:bg-blue-700 disabled:bg-slate-600
                             text-white text-sm rounded-lg transition-colors"
                >
                  Create
                </button>
              </div>
            </div>
          </div>
        )}

        <div className="space-y-3">
          {meetings.length === 0 && (
            <p className="text-slate-500 text-center py-12">
              No meetings yet. Create one to get started.
            </p>
          )}
          {meetings.map((m) => (
            <div
              key={m.id}
              className="bg-slate-800 rounded-lg p-4 flex items-center justify-between
                         hover:bg-slate-750 transition-colors cursor-pointer"
              onClick={() => router.push(`/meeting/${m.id}`)}
            >
              <div>
                <h3 className="text-slate-100 font-medium">{m.title}</h3>
                <p className="text-slate-400 text-sm">
                  {m.status} · {new Date(m.created_at).toLocaleDateString()}
                </p>
              </div>
              <span
                className={`px-2 py-1 rounded text-xs font-medium ${
                  m.status === "active"
                    ? "bg-green-900 text-green-300"
                    : m.status === "ended"
                    ? "bg-slate-700 text-slate-400"
                    : "bg-blue-900 text-blue-300"
                }`}
              >
                {m.status}
              </span>
            </div>
          ))}
        </div>
      </div>
    </main>
  );
}
