// ──── Caption Event Protocol ────
// Shared schema between backend worker → API → frontend

export interface CaptionEvent {
  type: "caption.delta" | "caption.final";
  event_id: string;
  meeting_id: string;
  speaker_id: string;
  speaker_name: string;
  source_language: "en" | "th";
  target_language: "en" | "th";
  translated_text: string;
  sequence: number;
  revision: number;
  is_final: boolean;
  started_at?: string; // ISO 8601, only on caption.delta
}

// ──── LiveKit Token Metadata ────

export interface ParticipantTokenMetadata {
  app_role: "internal" | "guest";
  spoken_language: "en" | "th";
  caption_language: "en" | "th" | null;
  caption_access: boolean;
}

// ──── API Contracts ────

export interface CreateMeetingPayload {
  title: string;
  guest_spoken_language: "en" | "th";
  expires_in_hours: number;
}

export interface MeetingResponse {
  id: string;
  room_name: string;
  title: string;
  status: "created" | "active" | "ended";
  created_by: string;
  created_at: string;
  started_at: string | null;
  ended_at: string | null;
}

export interface InviteResponse {
  id: string;
  token: string;
  invite_url: string;
  guest_name: string;
  expires_at: string;
}

export interface LoginPayload {
  email: string;
  password: string;
}

export interface AuthTokens {
  access_token: string;
  refresh_token: string;
  token_type: "bearer";
}

export type MeetingRole = "host" | "internal_partner" | "guest";
export type Language = "en" | "th";
export type MeetingStatus = "created" | "active" | "ended";
