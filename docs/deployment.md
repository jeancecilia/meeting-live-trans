# Deployment

## Infrastructure

The production deployment runs on an Ubuntu VPS with Docker Compose:

- `meet.example.com` — Next.js frontend
- `api.meet.example.com` — FastAPI + caption WebSocket
- `rtc.meet.example.com` — LiveKit media server

## Requirements

- Ubuntu 22.04+ VPS
- Public IP address
- Domain name with DNS configured
- Docker & Docker Compose installed
- OpenAI API key

## Production checklist

- [ ] TLS certificates configured (Caddy auto-provisions)
- [ ] Firewall: ports 80, 443, 7880-7882 open
- [ ] TURN/TLS configured for restrictive networks
- [ ] Database password changed from default
- [ ] LiveKit API key/secret rotated
- [ ] PostgreSQL not publicly exposed
- [ ] OpenAI API key set in worker environment only
- [ ] Worker provider is `openai-hybrid`: direct `gpt-realtime-translate` for
      validated English → Thai and transcribe-then-translate for Thai → English
- [ ] `OPENAI_REALTIME_TRANSLATE_SOURCE_LANGUAGES` contains only directions that
      passed realistic microphone quality validation
- [ ] Fallback models remain configured for every source language and direct
      session failures are visible in operational logs
- [ ] Worker API and caption-router URLs resolve to the meeting API service; use
      a project-specific Docker network alias when the network is shared
- [ ] Server reboot restores services (Docker restart policies)
- [ ] Automated database backups enabled
- [ ] Health check monitoring configured
- [ ] `PUBLIC_WEB_URL` points to the public frontend origin so generated client
      invitations use the production domain
- [ ] `MEETING_MAX_DURATION_MINUTES=60` and
      `MEETING_EXPIRY_SWEEP_SECONDS=15` are present on the API service
- [ ] `SEED_ENGLISH_EMAIL` and `SEED_THAI_EMAIL` contain the two production
      internal login addresses; changing them renames the existing role
      accounts on API startup without losing meeting history
- [ ] Verify that host-triggered and automatic meeting endings disconnect the
      corresponding LiveKit room
