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
- [ ] Worker transcription model is `gpt-realtime-whisper` (or another verified
      realtime transcription model) and is configured through the environment
- [ ] Worker API and caption-router URLs resolve to the meeting API service; use
      a project-specific Docker network alias when the network is shared
- [ ] Server reboot restores services (Docker restart policies)
- [ ] Automated database backups enabled
- [ ] Health check monitoring configured
