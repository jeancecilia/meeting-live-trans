# Architecture

## System overview

The Meeting Live Trans platform enables browser-based video meetings with realtime English ↔ Thai translation. Participants connect through a Next.js frontend that communicates with a LiveKit self-hosted media server. A Python translation worker subscribes to each participant's microphone track independently and streams audio to the OpenAI Realtime API. Translated captions are routed only to authorized internal users through an authenticated WebSocket managed by the FastAPI backend.

## Key decisions

1. **Separate audio tracks per participant.** Each microphone track is processed independently. The worker knows each participant's identity and language without speaker diarization.

2. **Provider abstraction.** Production currently uses the verified fallback
   pipeline: `gpt-realtime-whisper` transcription followed by configurable
   text translation. The transcription WebSocket connects with
   `intent=transcription`, sends a `session.type` of `transcription`, and uses
   mono PCM16 audio at 24 kHz. Direct `gpt-realtime-translate` remains behind
   the provider abstraction until English ↔ Thai quality and availability are
   benchmarked.

3. **Private caption routing.** Captions are delivered through authenticated WebSocket connections. The backend enforces authorization server-side. Guests cannot access captions even by modifying frontend JavaScript.

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
