# Master implementation ticket: Private English ↔ Thai meeting platform

## Important technical decision

Build the meeting system with **separate audio tracks for every participant**. Do not send a mixed room recording to OpenAI. The translation worker subscribes to each participant's microphone track separately, knowing each participant's identity and selected language without needing speaker diarization. LiveKit supports processing individual participant tracks as realtime audio frames. ([LiveKit Doku][1])

For the AI, implement a provider abstraction with two possible pipelines:

```text
Preferred, when verified:
Audio → gpt-realtime-translate → translated transcript

Guaranteed fallback:
Audio → gpt-realtime-whisper → fast OpenAI text translation
```

OpenAI's current documentation confirms that `gpt-realtime-translate` streams translated audio and transcript deltas, while `gpt-realtime-whisper` provides native realtime transcription deltas. The direct English → Thai and Thai → English quality and availability must be tested before committing to the direct-translation implementation. ([OpenAI Entwickler][2])

## Fixed MVP scope

The first version will support:

* Browser-based video meetings.
* Maximum five participants.
* Two authenticated internal users:

  * English-speaking internal user.
  * Thai-speaking internal user.
* Guest clients joining through expiring invitation links.
* English and Thai only.
* Private translated subtitles for internal users.
* No captions delivered to guest clients.
* Manual spoken-language selection.
* Camera, microphone, screen sharing and participant grid.
* No recording.
* No translated artificial voice.
* No transcript storage by default.
* No calendar integration.
* No mobile app for V1.

## Recommended stack

```text
Frontend:
Next.js + TypeScript
LiveKit React components
Tailwind CSS

Application backend:
Python 3.12
FastAPI
SQLAlchemy
Alembic
PostgreSQL
Redis

Meeting infrastructure:
Self-hosted LiveKit
TURN/TLS fallback
Caddy or Traefik

AI worker:
Python
LiveKit server/RTC SDK
OpenAI Realtime WebSocket API

Deployment:
Docker Compose
Ubuntu VPS
GitHub Actions
```

LiveKit can be self-hosted, but production WebRTC deployment requires correct public networking, TLS and TURN connectivity, so this must be treated as a dedicated infrastructure task rather than a normal HTTP deployment. ([LiveKit Doku][3])

## Roles and permissions

| Capability                        | Host | Internal partner | Guest client |
| --------------------------------- | ---: | ---------------: | -----------: |
| Join meeting                      |  Yes |              Yes |          Yes |
| Publish microphone/camera         |  Yes |              Yes |          Yes |
| Receive other participants' media |  Yes |              Yes |          Yes |
| Create meeting                    |  Yes |         Optional |           No |
| End meeting                       |  Yes |               No |           No |
| Receive private captions          |  Yes |              Yes |       **No** |
| Select caption language           |  Yes |              Yes |           No |
| View meeting history              |  Yes |         Optional |           No |

The guest must not merely have captions hidden in the interface. The backend must refuse to create a caption subscription for guest roles.

---

# 3. Architecture

```text
Participant browser
    │
    ├── Camera/video ───────────────┐
    ├── Microphone/audio ───────────┤
    │                               ▼
    │                       Self-hosted LiveKit
    │                               │
    │                   Separate microphone tracks
    │                               │
    │                               ▼
    │                       Translation worker
    │                               │
    │                  Resample to mono PCM 24 kHz
    │                               │
    │                               ▼
    │                     OpenAI Realtime API
    │                               │
    │                  Transcript / translation deltas
    │                               │
    │                               ▼
    └── Private caption WebSocket ◄─ FastAPI caption router
```

OpenAI's realtime transcription endpoint accepts server-side WebSocket connections and documents 24 kHz mono PCM input for `gpt-realtime-whisper`. ([OpenAI Entwickler][2])

## Implementation tickets in exact order

### Epic 0 — Mandatory technical validation

#### MTG-001 — Validate OpenAI English ↔ Thai pipeline

**Objective:** Determine the final OpenAI pipeline before building the complete worker.

**Implementation:**

1. Prepare at least 30 English audio samples and 30 Thai audio samples.
2. Include:

   * Clean microphone recordings.
   * Thai and international English accents.
   * Names.
   * Dates and prices.
   * Software terminology.
   * Background noise.
3. Test direct realtime translation:

   * English audio → Thai transcript.
   * Thai audio → English transcript.
4. Test fallback pipeline:

   * `gpt-realtime-whisper` transcription.
   * OpenAI text-model translation.
5. Record:

   * Time to first partial caption.
   * Time to final caption.
   * Missing sentences.
   * Incorrect numbers.
   * Incorrect names.
   * Translation quality.
6. Place model names in environment variables rather than hard-coding them.

**Acceptance criteria:**

* Both language directions have been tested.
* Results are stored in a benchmark report.
* The chosen production pipeline is documented.
* A fallback provider is documented.
* The application can switch providers through configuration.
* No frontend implementation begins based only on an assumption about direct Thai support.

---

#### MTG-002 — Prove separate-track audio processing

**Objective:** Confirm that the worker can independently receive two participants' microphones.

**Implementation:**

1. Run LiveKit locally.
2. Connect two browser participants.
3. Join the room with a Python worker.
4. Subscribe to microphone tracks.
5. Log:

   * Participant identity.
   * Track identity.
   * Audio frame timestamp.
   * Sample rate.
6. Confirm simultaneous speakers remain separate.

**Acceptance criteria:**

* Audio frames are received separately for each participant.
* Every frame is associated with the correct participant identity.
* Muting stops frames for only that participant.
* Disconnecting one participant cleans up only that participant's pipeline.

---

### Epic 1 — Repository and infrastructure foundation

#### MTG-010 — Create monorepo structure

```text
/apps
  /web
  /api
  /translation-worker

/packages
  /contracts
  /shared-config

/infrastructure
  /docker
  /livekit
  /proxy

/docs
  architecture.md
  local-development.md
  deployment.md
```

**Acceptance criteria:**

* All three services start independently.
* Shared event schemas are versioned.
* `.env.example` exists.
* Secrets are excluded from Git.
* Formatting, linting and tests run through one command.

---

#### MTG-011 — Create local Docker environment

Create containers for:

* PostgreSQL.
* Redis.
* LiveKit.
* FastAPI backend.
* Translation worker.
* Next.js frontend.

**Acceptance criteria:**

```bash
docker compose up
```

starts the complete local environment.

Health checks must exist for:

```text
/api/health
/api/health/database
/api/health/redis
/api/health/livekit
```

---

#### MTG-012 — Implement database schema and migrations

Create the following tables.

##### `users`

```text
id
email
password_hash
display_name
role
preferred_spoken_language
preferred_caption_language
is_active
created_at
updated_at
```

##### `meetings`

```text
id
room_name
title
status
created_by
scheduled_at
started_at
ended_at
created_at
```

##### `meeting_invites`

```text
id
meeting_id
token_hash
guest_name
expected_spoken_language
expires_at
max_uses
use_count
revoked_at
created_at
```

##### `meeting_participants`

```text
id
meeting_id
user_id nullable
guest_identity nullable
livekit_identity
display_name
role
spoken_language
caption_language nullable
caption_access
joined_at
left_at
```

##### `audit_logs`

```text
id
actor_id nullable
meeting_id nullable
event_type
metadata_json
created_at
```

Do not create audio-storage tables for the MVP.

**Acceptance criteria:**

* Alembic migrations work forward and backward.
* Invite tokens are stored as hashes.
* Database constraints prevent invalid roles and language codes.
* Guest participants always default to `caption_access = false`.

---

#### MTG-013 — Implement internal authentication

**Implementation:**

* Email and password login.
* Secure password hashing.
* Access and refresh tokens.
* Logout.
* Disabled-user handling.
* Seed script for the two internal accounts.
* Role-based route protection.

**Acceptance criteria:**

* Guests cannot access the dashboard.
* Expired access tokens are rejected.
* Refresh tokens can be revoked.
* Passwords never appear in logs.
* Authentication tests cover valid and invalid sessions.

---

### Epic 2 — Meetings and guest links

#### MTG-020 — Create meeting API

Create:

```http
POST /api/meetings
GET  /api/meetings
GET  /api/meetings/{meeting_id}
POST /api/meetings/{meeting_id}/end
```

Example creation payload:

```json
{
  "title": "Client project consultation",
  "guest_spoken_language": "en",
  "expires_in_hours": 24
}
```

**Acceptance criteria:**

* Only authorized internal users can create meetings.
* LiveKit room names are generated server-side.
* Room names are not predictable.
* Meeting status transitions are validated.
* Ending a meeting prevents new guest joins.

---

#### MTG-021 — Generate secure guest invitations

Create:

```http
POST /api/meetings/{meeting_id}/invites
GET  /api/public/invites/{token}
POST /api/public/invites/{token}/join
```

Invitation URL:

```text
https://meet.example.com/join/{random-token}
```

**Rules:**

* Token expires.
* Token can be revoked.
* Usage limit is configurable.
* Only a hash is stored.
* Token grants access to one meeting only.
* Token grants no caption permissions.

**Acceptance criteria:**

* Expired and revoked links cannot join.
* A token from one meeting cannot access another.
* A guest cannot modify their role through the request body.
* Guessing meeting IDs does not provide access.

---

#### MTG-022 — Generate LiveKit participant tokens

Token metadata must include:

```json
{
  "app_role": "internal",
  "spoken_language": "en",
  "caption_language": "en",
  "caption_access": true
}
```

Guest example:

```json
{
  "app_role": "guest",
  "spoken_language": "en",
  "caption_language": null,
  "caption_access": false
}
```

**Acceptance criteria:**

* Tokens are short-lived.
* Participants can publish microphone and camera.
* Guests cannot impersonate internal identities.
* Participant identities are unique per meeting.
* Application permissions are validated by the backend, not trusted from browser metadata.

---

#### MTG-023 — Build pre-join screen

Screen must include:

* Camera preview.
* Microphone preview.
* Input-device selector.
* Output-device selector where supported.
* Display name.
* Spoken-language selector.
* Join button.
* Permission error guidance.
* Notice that automated transcription/translation processes meeting audio.

The client does not see translated captions, but should be informed that their audio is being processed.

**Acceptance criteria:**

* Joining is blocked until microphone permission is resolved.
* Internal users can select English or Thai.
* Guest language defaults from the invitation.
* Guest cannot enable captions.
* Device errors are understandable.

---

#### MTG-024 — Build meeting room interface

Include:

* Responsive video grid.
* Participant names.
* Active-speaker indicator.
* Microphone toggle.
* Camera toggle.
* Screen sharing.
* Device settings.
* Leave meeting.
* Host-only end meeting.
* Network/reconnection indicator.
* Private-caption panel placeholder.

**Acceptance criteria:**

* Three participants can join successfully.
* Mute and camera changes are reflected for everyone.
* Screen sharing works.
* Temporary network loss attempts reconnection.
* The meeting UI remains usable at laptop and tablet widths.

---

#### MTG-025 — Synchronize meeting lifecycle

Add LiveKit webhook processing for:

* Participant joined.
* Participant left.
* Track published.
* Track unpublished.
* Room finished.

LiveKit provides server-side webhooks and client-side events for room, participant and track changes. ([LiveKit Doku][4])

**Acceptance criteria:**

* Join and leave timestamps are recorded.
* Duplicate webhook delivery is idempotent.
* Meeting status changes to active when the first participant joins.
* Worker cleanup occurs after the room ends.

---

### Epic 3 — Translation worker

#### MTG-030 — Join room as hidden translation worker

**Implementation:**

* Start one worker job per active room.
* Join using an internal service identity.
* Do not publish video.
* Subscribe only to microphone tracks.
* Ignore screen-share audio in V1.
* Create one `ParticipantAudioPipeline` per microphone track.

**Acceptance criteria:**

* Worker joins automatically.
* Worker does not appear as a visible video participant.
* Every participant pipeline starts and stops independently.
* Worker restart does not terminate the video call.

---

#### MTG-031 — Normalize audio for OpenAI

Pipeline:

```text
LiveKit audio frames
→ mono conversion
→ 24 kHz resampling
→ PCM16 encoding
→ chunk buffer
→ OpenAI WebSocket
```

**Acceptance criteria:**

* Output is mono PCM16 at 24 kHz.
* Audio chunks preserve chronological order.
* Buffers have maximum-size limits.
* Backpressure cannot cause unlimited memory growth.
* Muted and silent audio is not unnecessarily transmitted.

---

#### MTG-032 — Implement OpenAI realtime transcription provider

Create interface:

```python
class RealtimeTranscriptionProvider:
    async def start(self, language: str) -> None: ...
    async def append_audio(self, pcm: bytes) -> None: ...
    async def stop(self) -> None: ...
```

Handle:

```text
conversation.item.input_audio_transcription.delta
conversation.item.input_audio_transcription.completed
error
connection closed
```

OpenAI notes that completion events across speech turns are not guaranteed to arrive in order, so the implementation must reconcile events using `item_id`. ([OpenAI Entwickler][2])

**Acceptance criteria:**

* English and Thai language hints are supported.
* Partial and final transcripts are emitted.
* Events are ordered by speaker and item ID.
* WebSocket reconnect uses bounded exponential backoff.
* API failure does not disconnect the meeting.
* API keys never reach the frontend.

---

#### MTG-033 — Implement translation-provider abstraction

```python
class TranslationProvider:
    async def translate_partial(
        self,
        text: str,
        source_language: str,
        target_language: str,
        revision: int,
    ) -> TranslationResult: ...

    async def translate_final(
        self,
        text: str,
        source_language: str,
        target_language: str,
    ) -> TranslationResult: ...
```

Provide:

```text
OpenAIRealtimeTranslateProvider
OpenAITranscribeThenTranslateProvider
```

For the fallback provider:

* Debounce partial transcript translation.
* Do not translate every character.
* Translate after a meaningful text increment or short interval.
* Always perform a final translation when the utterance completes.
* Cancel or discard stale partial translations.
* Keep model selection configurable.

**Acceptance criteria:**

* English → Thai works.
* Thai → English works.
* Final translation replaces partial translation.
* Stale responses cannot overwrite newer captions.
* Original names, numbers, dates and currencies receive dedicated test coverage.
* Provider can be changed using environment configuration.

---

#### MTG-034 — Define caption event protocol

Example:

```json
{
  "type": "caption.delta",
  "event_id": "evt_123",
  "meeting_id": "meeting_123",
  "speaker_id": "participant_456",
  "speaker_name": "Client",
  "source_language": "en",
  "target_language": "th",
  "translated_text": "เราต้องการเปิดตัวในเดือนกันยายน",
  "sequence": 18,
  "revision": 3,
  "is_final": false,
  "started_at": "2026-07-12T10:15:04.220Z"
}
```

Final event:

```json
{
  "type": "caption.final",
  "event_id": "evt_123",
  "sequence": 18,
  "revision": 4,
  "translated_text": "เราต้องการเปิดตัวแอปในเดือนกันยายน",
  "is_final": true
}
```

**Acceptance criteria:**

* Every event includes the speaker identity.
* Sequence numbers are scoped per speaker.
* Partial captions can be replaced.
* Old revisions are ignored.
* Schema is shared between backend and frontend.

---

#### MTG-035 — Implement private caption routing

Create:

```text
WS /api/ws/meetings/{meeting_id}/captions
```

Connection authorization checks:

1. Valid logged-in internal user.
2. User belongs to the meeting.
3. `caption_access = true`.
4. Requested caption language matches allowed language.
5. Meeting is active.

Routing example:

```text
English speaker
→ route Thai translation to internal Thai-caption subscribers

Thai speaker
→ route English translation to internal English-caption subscribers

Any guest
→ no caption WebSocket authorization
```

LiveKit also supports targeted data delivery to selected participant identities, but a separate authenticated WebSocket makes application-level authorization and auditing clearer for this MVP. ([LiveKit Doku][5])

**Acceptance criteria:**

* Guest WebSocket connections receive HTTP 403.
* No caption payload is broadcast to the room.
* Captions are sent only to matching internal recipients.
* Network inspection from a guest browser reveals no caption events.
* Changing frontend JavaScript cannot bypass authorization.

---

#### MTG-036 — Build private caption interface

Internal users receive:

* Current translated sentence.
* Speaker name.
* Previous two or three completed captions.
* Caption on/off control.
* Font-size control.
* Caption-language selector.
* Translation status indicator.
* "Translation unavailable" message.

Suggested layout:

```text
┌────────────────────────────────────────┐
│ Client                                 │
│ เราต้องการเปิดตัวแอปในเดือนกันยายน       │
└────────────────────────────────────────┘
```

**Acceptance criteria:**

* Partial text updates without duplicating the sentence.
* Final text replaces partial text cleanly.
* Captions remain readable over video.
* Caption panel can be moved or collapsed.
* Guests have no caption components or caption network connection.

---

#### MTG-037 — Implement reliability and cost controls

Add:

* Maximum OpenAI sessions per room.
* Session cleanup when tracks disappear.
* Silence detection.
* Partial-translation debounce.
* Maximum utterance length.
* Connection timeout.
* Retry limits.
* Per-meeting usage counters.
* Circuit breaker.
* Internal error notifications.

**Acceptance criteria:**

* Realtime translation failure does not terminate video.
* Failed sessions are cleaned up.
* Silent participants do not generate continuous translation requests.
* One failed speaker pipeline does not stop other speakers.
* Usage can be reviewed per meeting without storing raw audio.

---

### Epic 4 — Security and privacy

#### MTG-040 — Implement consent and privacy controls

Include before joining:

```text
This meeting uses automated speech transcription and translation.
Audio is processed in real time. Meeting audio is not recorded by
this application.
```

Add configuration for:

* Transcript storage disabled by default.
* Optional final-caption storage.
* Retention duration.
* Delete meeting data.
* Privacy-policy link.

**Acceptance criteria:**

* User must acknowledge the notice before joining.
* Raw audio is never written to disk.
* Caption content is not written to application logs.
* Deleting a meeting removes optional stored caption data.

---

#### MTG-041 — Harden invitation and API security

Implement:

* Rate limiting.
* Token hashing.
* Short-lived LiveKit tokens.
* Strict CORS.
* Secure cookies.
* CSRF protection where relevant.
* WebSocket origin validation.
* Input validation.
* Audit logs.
* Invite revocation.
* Brute-force protection.

**Acceptance criteria:**

* Invalid invite attempts are rate-limited.
* Guest identities cannot collide with internal identities.
* OpenAI and LiveKit secrets remain server-side.
* Security headers are present.
* Caption authorization has automated negative tests.

---

#### MTG-042 — Implement safe logging and observability fields

Permitted logs:

```text
meeting_id
participant_id
track_id
provider_name
connection_state
latency_ms
error_code
audio_duration_seconds
caption_event_count
```

Do not log:

```text
raw audio
full transcript
full translated text
API keys
invite tokens
passwords
```

**Acceptance criteria:**

* Production logs contain no spoken content.
* Secrets are redacted.
* Correlation IDs connect API, worker and meeting events.
* Operational failures can be diagnosed without reading conversations.

---

### Epic 5 — Testing

#### MTG-050 — Unit and integration tests

Test:

* Authentication.
* Invite expiry.
* Invite revocation.
* Role enforcement.
* LiveKit token claims.
* Caption routing.
* Event ordering.
* Translation revisions.
* Worker cleanup.
* Provider timeout handling.
* Database migrations.

**Acceptance criteria:**

* Critical backend and worker logic is covered.
* CI fails when tests or type checks fail.
* OpenAI calls are mocked in standard CI.
* Separate optional integration tests can call the real provider.

---

#### MTG-051 — Create English/Thai evaluation harness

Create a repeatable dataset containing:

* Normal business conversation.
* Software-development terms.
* Thai names.
* English names.
* Dates.
* Phone numbers.
* Prices in THB, EUR and USD.
* Email addresses.
* Interruptions.
* Background noise.
* Longer explanations.

Record:

```text
source audio
expected meaning
source transcript
translated text
first-caption latency
final-caption latency
manual quality rating
```

**Acceptance criteria:**

* Both directions have equal test coverage.
* Regression comparison is automatic where possible.
* Model or prompt changes produce a before/after report.
* Numbers and names are evaluated separately from general meaning.

OpenAI recommends testing each target language with realistic microphones, accents, background noise and domain vocabulary rather than relying only on clean synthetic audio. ([OpenAI Entwickler][2])

---

#### MTG-052 — Conduct meeting reliability tests

Test scenarios:

* Three-person 60-minute call.
* Two people speaking simultaneously.
* Participant muting and unmuting.
* Camera changes.
* Worker restart.
* API restart.
* Temporary OpenAI outage.
* Temporary internet loss.
* Browser refresh.
* Participant switching microphones.
* Host ending the meeting.

**Acceptance criteria:**

* Video meeting continues when translation fails.
* Caption recovery does not duplicate old sentences.
* Worker memory remains stable.
* Disconnected audio pipelines are removed.
* No raw audio files remain after the test.

---

#### MTG-053 — Prove that guests cannot access captions

Attempt:

* Opening caption WebSocket as guest.
* Reusing internal WebSocket URLs.
* Modifying browser role metadata.
* Editing local storage.
* Reusing expired access tokens.
* Guessing meeting IDs.
* Subscribing to LiveKit data events.
* Calling internal caption endpoints directly.

**Acceptance criteria:**

* Every attempt is rejected.
* Guest browser receives no original or translated transcript payload.
* The security test is automated in CI where possible.
* The result is included in the release checklist.

---

### Epic 6 — Production deployment

#### MTG-060 — Deploy VPS infrastructure

Suggested services:

```text
meet.example.com        Frontend
api.meet.example.com    FastAPI and caption WebSocket
rtc.meet.example.com    LiveKit
```

Deploy:

* Reverse proxy.
* TLS certificates.
* PostgreSQL.
* Redis.
* LiveKit.
* TURN/TLS.
* API.
* Worker.
* Frontend.
* Firewall.
* Automated database backup.
* Container restart policies.

**Acceptance criteria:**

* External users can connect from different networks.
* Camera and audio work behind restrictive networks.
* HTTPS and secure WebSockets work.
* Database is not publicly exposed.
* OpenAI API key exists only in the worker environment.
* Server reboot restores services automatically.

---

#### MTG-061 — Implement CI/CD

Pipeline:

```text
Pull request
→ lint
→ type check
→ unit tests
→ build containers
→ security scan
→ deploy staging

Approved main branch
→ database migration
→ deploy production
→ health checks
→ rollback on failure
```

**Acceptance criteria:**

* Production deployment is reproducible.
* Migrations run once.
* Failed health checks trigger rollback.
* Secrets are stored outside the repository.
* Images are tagged by commit SHA.

---

#### MTG-062 — Add monitoring and alerts

Monitor:

* Active meetings.
* Active participants.
* Active OpenAI sessions.
* Caption latency.
* Translation failures.
* Worker restarts.
* WebSocket disconnects.
* CPU and memory.
* LiveKit connectivity.
* Database and Redis health.

**Acceptance criteria:**

* Alerts exist for API failure, worker failure and high caption error rate.
* Dashboard shows caption latency without showing caption content.
* A failed translation provider is visible before the client reports it.

---

#### MTG-063 — Final UAT and release

Run a real three-person test:

1. English internal user joins.
2. Thai internal user joins.
3. English-speaking guest joins.
4. Guest speaks English.
5. Thai partner sees Thai captions.
6. Thai partner speaks Thai.
7. English user sees English captions.
8. Guest inspects the interface and network.
9. Guest receives no captions.
10. OpenAI is temporarily disconnected.
11. Video call continues.
12. Translation reconnects.

**Release acceptance criteria:**

* Both translation directions work.
* Speaker labels are correct.
* Captions are private.
* No audio is recorded.
* Guest invitations expire correctly.
* One-hour meeting completes without a critical failure.
* Error states are understandable.
* Production backup and rollback are tested.

---

# 5. Required backend API contract

```http
POST   /api/auth/login
POST   /api/auth/refresh
POST   /api/auth/logout

POST   /api/meetings
GET    /api/meetings
GET    /api/meetings/{meeting_id}
POST   /api/meetings/{meeting_id}/end

POST   /api/meetings/{meeting_id}/invites
DELETE /api/meetings/{meeting_id}/invites/{invite_id}

GET    /api/public/invites/{token}
POST   /api/public/invites/{token}/join

POST   /api/meetings/{meeting_id}/livekit-token
POST   /api/webhooks/livekit

WS     /api/ws/meetings/{meeting_id}/captions
```

---

# 6. Global definition of done

Every ticket is complete only when:

* Implementation is committed.
* Type checking passes.
* Linting passes.
* Relevant tests pass.
* Error handling exists.
* No secret is exposed.
* Authorization is enforced server-side.
* Documentation is updated.
* Docker build succeeds.
* Staging environment has been tested.
* No raw audio or caption text appears in logs.

---

[1]: https://docs.livekit.io/transport/media/raw-tracks/?utm_source=chatgpt.com "Processing raw media tracks"
[2]: https://developers.openai.com/api/docs/guides/realtime-transcription "
  Realtime transcription | OpenAI API
"
[3]: https://docs.livekit.io/transport/self-hosting/?utm_source=chatgpt.com "Self-hosting overview"
[4]: https://docs.livekit.io/intro/basics/rooms-participants-tracks/webhooks-events/?utm_source=chatgpt.com "Webhooks & events"
[5]: https://docs.livekit.io/transport/data/packets/?utm_source=chatgpt.com "Data packets"
