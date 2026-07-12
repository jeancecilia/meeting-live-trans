export const VALID_LANGUAGES = ["en", "th"] as const;
export const VALID_ROLES = ["host", "internal_partner", "guest"] as const;
export const VALID_MEETING_STATUSES = ["created", "active", "ended"] as const;

export const LIVEKIT_AUDIO_SAMPLE_RATE = 24000;
export const LIVEKIT_AUDIO_CHANNELS = 1;
export const MAX_PARTICIPANTS_PER_ROOM = 5;

export const INVITE_DEFAULT_EXPIRE_HOURS = 24;
export const INVITE_MAX_USES_DEFAULT = 1;

export const JWT_ACCESS_TOKEN_EXPIRE_MINUTES = 15;
export const JWT_REFRESH_TOKEN_EXPIRE_DAYS = 7;
