# Architecture

## System overview

The Meeting Live Trans platform enables browser-based video meetings with realtime English ↔ Thai translation. Participants connect through a Next.js frontend that communicates with a LiveKit self-hosted media server. A Python translation worker subscribes to each participant's microphone track independently and streams audio to the OpenAI Realtime API. Translated captions are routed only to authorized internal users through an authenticated WebSocket managed by the FastAPI backend.

## Key decisions

1. **Separate audio tracks per participant.** Each microphone track is processed independently. The worker knows each participant's identity and language without speaker diarization.

2. **Provider abstraction.** Production uses the `openai-hybrid` policy. The
   synthetically validated English → Thai direction streams direct
   `gpt-realtime-translate` transcript deltas for user UAT. Thai → English uses
   `gpt-realtime-whisper` transcription
   plus configurable text translation because direct synthetic Thai quality was
   not consistent enough on dates and times. Debounced fallback partials are
   revision-safe, and the final transcript always replaces the partial. A
   direct-session failure automatically switches only that speaker to the
   fallback. Both paths receive mono PCM16 audio at 24 kHz, and validated direct
   source languages remain environment-configurable.

3. **Private caption routing.** Captions are delivered through authenticated WebSocket connections. The backend enforces authorization server-side. Guests cannot access captions even by modifying frontend JavaScript. Internal users receive their configured caption language and a private preview of translations generated from their own microphone, so one-device translation testing does not require a second internal account.

## Component diagram

```
Browser (Next.js)
    → LiveKit (media)
    → FastAPI (HTTP + WebSocket captions)

FastAPI
    → PostgreSQL (users, meetings, invites)
    → Redis (sessions, rate limiting)

Translation Worker (Python)
    → LiveKit (subscribe audio tracks)
    → OpenAI Realtime API (transcription/translation)
    → FastAPI (caption events)
```
