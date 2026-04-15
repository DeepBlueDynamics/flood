# flood

Web UI and CLI for generating long-form video with **Google Veo 3**. Supports single clips, seamless loops, chained long-form video, and extending existing footage — all driven by the "Nanobanana" frame-continuation technique.

---

## Prerequisites

- **Python 3.11+**
- **Google API key** with Veo 3 access ([get one here](https://aistudio.google.com/apikey))
- **ffmpeg** — installed locally on Mac/Linux, or via Docker on Windows

---

## Quick Start (Mac / Linux)

```bash
git clone <repo-url> && cd flow

# Install ffmpeg, create venv, install deps, seed .env
bash setup.sh

# Add your API key
edit .env          # set GOOGLE_API_KEY=...

# Run
source .venv/bin/activate
python run.py
```

Open **http://localhost:8080**

---

## Web UI

Four generation modes available from the browser:

| Tab | What it does |
|-----|-------------|
| **Generate** | Single 8-second clip from a text prompt |
| **Loop** | 3 segments cross-faded into a seamless 10-second loop |
| **Chain** | N segments chained end-to-end via frame seeding (8s × N) |
| **Extend** | Upload an existing video, add continuation segments |

Progress is streamed in real-time via SSE — the progress bar fills as each segment completes. The finished video plays inline with a download link.

---

## CLI

```bash
# Activate venv first
source .venv/bin/activate

# Single clip
python veo_agent.py "A hawk diving through storm clouds" output/clip.mp4

# Seamless loop
python veo_agent.py loop "Lava flowing into the ocean at dusk" output/loop.mp4

# Long-form chain (4 segments = ~32 seconds)
python veo_agent.py chain "A rover crossing a rust-red canyon" 4 output/long.mp4

# Chain with a specific starting image
python veo_agent.py chain "Continue the journey..." 3 output/long.mp4start.png

# Extend an existing video
python extend_video.py source.mp4 "The ship enters the nebula" "Crew reacts" \
  -o output/extended.mp4
```

---

## Configuration

Copy `.env.example` to `.env` and set your values:

```bash
cp .env.example .env
```

| Variable | Default | Description |
|----------|---------|-------------|
| `GOOGLE_API_KEY` | *(required)* | Google API key with Veo 3 access |
| `FFMPEG_MODE` | `local` | `local` = system binary, `docker` = nemisis8 container |
| `PORT` | `8080` | Web server port |
| `FFMPEG_DOCKER_IMAGE` | `nemisis8:latest` | Docker image to use when `FFMPEG_MODE=docker` |

---

## How It Works — "Nanobanana" Technique

Veo 3 generates 5–8 second clips. To produce longer video:

1. Generate **Segment A**
2. Extract the **exact last frame** of Segment A with OpenCV
3. Pass that frame as the `image` parameter when generating **Segment B**
4. Veo treats it as the starting state → seamless visual continuation
5. Repeat, then stitch all segments with ffmpeg

Each segment takes ~2 minutes to generate.

---

## Project Structure

```
core/
  veo.py          # All generation logic (generate, loop, chain, extend, storyboard)
  ffmpeg.py       # FFmpeg abstraction — local binary or Docker container
web/
  app.py          # FastAPI: job queue, SSE streaming, file serving
  static/
    index.html    # Single-page UI (no build step)
veo_agent.py      # CLI: generate / loop / chain
extend_video.py   # CLI: extend existing video
run.py            # Local dev entry point
setup.sh          # Mac/Linux one-shot setup
Dockerfile        # Cloud Run container (python:3.11-slim + ffmpeg)
.env.example      # Environment variable template
output/           # Generated videos (git-ignored)
```

---

## Cloud Run Deployment

```bash
gcloud run deploy veo-studio \
  --source . \
  --region us-central1 \
  --allow-unauthenticated \
  --timeout 3600 \
  --cpu-always-allocated \
  --max-instances 1 \
  --concurrency 1 \
  --memory 1Gi \
  --set-env-vars FFMPEG_MODE=local \
  --set-secrets GOOGLE_API_KEY=google-api-key:latest
```

Key flags:
- `--timeout 3600` — 1-hour timeout; each segment takes ~2 min
- `--cpu-always-allocated` — required for SSE to keep the connection alive
- `--concurrency 1` — job store is in-memory; one request at a time
- `FFMPEG_MODE=local` — uses the apt-installed ffmpeg in the container

---

## Docker (Local)

```bash
docker build -t veo-studio .
docker run -p 8080:8080 --env-file .env veo-studio
```
