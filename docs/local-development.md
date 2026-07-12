# Local Development

## Prerequisites

- Node.js 20+
- Python 3.12+
- Docker & Docker Compose
- LiveKit CLI (optional, for debugging)

## Quick start

```bash
# Copy environment variables
cp .env.example .env

# Start all services
docker compose up

# Or start individually:

# 1. Infrastructure
docker compose up postgres redis livekit -d

# 2. Backend
cd apps/api
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000

# 3. Worker
cd apps/translation-worker
pip install -e .
python main.py

# 4. Frontend
cd apps/web
npm install
npm run dev
```

## Services

| Service     | URL                    |
| ----------- | ---------------------- |
| Frontend    | http://localhost:3000  |
| API         | http://localhost:8000  |
| API Docs    | http://localhost:8000/api/docs |
| LiveKit     | ws://localhost:7880    |
| PostgreSQL  | localhost:5432         |
| Redis       | localhost:6379         |

## Health checks

```bash
curl http://localhost:8000/api/health
curl http://localhost:8000/api/health/database
curl http://localhost:8000/api/health/redis
curl http://localhost:8000/api/health/livekit
```
