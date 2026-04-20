# chill-agent

Autonomous YouTube channel pipeline — "Chill Dude Explains" style. Picks topics, writes scripts, generates voiceovers and illustrations, assembles 1080p videos with Ken Burns effects, and uploads to YouTube on a schedule. Zero human intervention after setup.

---

## What it does

Runs a loop 4× per day:
1. Picks a topic (weird psychology, bizarre science, dark curiosity)
2. Writes a ~2,000-word countdown script in the "Chill Dude Explains" voice
3. Synthesizes narration with Fish Audio TTS
4. Generates flat-cartoon illustrations with Flux 1.1 Pro
5. Aligns audio to text for chapter markers and captions (WhisperX)
6. Assembles a 1080p MP4 with Ken Burns pan/zoom and lo-fi background music
7. Generates thumbnail variants (A/B)
8. Uploads to YouTube as a scheduled private video

---

## Requirements

- Python 3.11+
- FFmpeg (must be in PATH)
- Docker + Docker Compose (for production deployment)
- API keys: DeepSeek, Fish Audio (or ElevenLabs), Replicate
- YouTube Data API credentials (OAuth 2.0)

---

## API Keys

### DeepSeek (LLM)
1. Sign up at [platform.deepseek.com](https://platform.deepseek.com)
2. Create an API key in the dashboard
3. Set `DEEPSEEK_API_KEY=` in your `.env`

### Fish Audio (TTS — primary)
1. Sign up at [fish.audio](https://fish.audio)
2. Go to API → Create API Key
3. Set `FISH_AUDIO_API_KEY=` in your `.env`
4. Browse voices at fish.audio and pick one consistent voice; set `TTS_VOICE_ID=`

### ElevenLabs (TTS — fallback)
1. Sign up at [elevenlabs.io](https://elevenlabs.io)
2. Profile → API Key
3. Set `ELEVENLABS_API_KEY=` in your `.env`

### Replicate (image generation)
1. Sign up at [replicate.com](https://replicate.com)
2. Account → API Tokens → Create token
3. Set `REPLICATE_API_TOKEN=` in your `.env`

### YouTube Data API (upload)
1. Go to [console.cloud.google.com](https://console.cloud.google.com)
2. Create a project → Enable **YouTube Data API v3** and **YouTube Analytics API**
3. Credentials → Create OAuth 2.0 Client ID → Desktop App
4. Download `client_secret.json` → place in `./secrets/client_secret.json`
5. Run `chill-agent init` to go through the OAuth flow; token saved to `./secrets/token.json`
6. Set `YOUTUBE_CHANNEL_ID=` (your channel's UC... ID)

---

## Setup (local dev)

```bash
git clone <repo>
cd chill-agent

# Install with pip
pip install -e ".[dev]"

# Or with uv (faster)
uv pip install -e ".[dev]"

# Copy env and fill in your keys
cp .env.example .env
$EDITOR .env

# Initialize DB and OAuth
chill-agent init

# Test the full pipeline without uploading
chill-agent dry-run

# Run tests
pytest
```

### WhisperX (optional but recommended for accurate chapters/captions)

```bash
pip install whisperx
# WhisperX requires torch + a HuggingFace token for some alignment models
# See: https://github.com/m-bain/whisperX
```

If WhisperX is not installed, chapters use evenly-distributed timestamps (still works, just less precise).

---

## Setup (production — Docker)

```bash
# Fill in .env with all API keys
cp .env.example .env
$EDITOR .env

# Place client_secret.json in secrets/ directory
# Run OAuth flow locally first: chill-agent init
# Then copy secrets/token.json to the server

docker compose up -d
docker compose logs -f
```

The scheduler runs inside the container and produces ~4 videos/day.

---

## CLI Reference

```
chill-agent init              Create DB, verify env vars, run YouTube OAuth flow
chill-agent run               Start the scheduler (runs forever, 4 videos/day)
chill-agent run-once          Make and upload exactly one video, then exit
chill-agent dry-run           Full pipeline, skip upload (safe for testing)
chill-agent resume <run_id>   Resume a failed pipeline run from last checkpoint
chill-agent backfill -n 10    Produce 10 videos quickly (channel warm-up)
chill-agent stats             Print performance summary from DB
chill-agent run --warmup      Limit to 1 video/day for first 14 days
```

---

## Configuration

All config lives in `.env`. Key settings:

| Variable | Default | Description |
|---|---|---|
| `VIDEOS_PER_DAY` | `4` | Target uploads per day |
| `PUBLISH_HOURS_UTC` | `8,14,20,2` | Hours to schedule uploads |
| `ENABLE_CAPTIONS` | `true` | Burn captions into video |
| `WARMUP_MODE` | `false` | Limit to 1/day for first 14 days |
| `TTS_PROVIDER` | `fish_audio` | `fish_audio` or `elevenlabs` |
| `IMAGE_PROVIDER` | `replicate_flux` | `replicate_flux` or `sdxl_local` |

---

## Project Structure

```
src/chill_agent/
├── config.py          Pydantic settings (reads .env)
├── cli.py             Typer CLI entry points
├── orchestrator.py    Full pipeline for one video
├── scheduler.py       APScheduler-based run loop
├── db/
│   ├── models.py      SQLAlchemy models
│   └── repo.py        DB access layer
├── stages/            One module per pipeline stage
│   ├── ideation.py    Topic selection
│   ├── script.py      Script generation
│   ├── tts.py         Voice synthesis
│   ├── images.py      Image generation
│   ├── assembly.py    Video assembly
│   ├── thumbnail.py   Thumbnail generation
│   ├── metadata.py    Metadata finalization
│   ├── upload.py      YouTube upload
│   └── track.py       Performance tracking
├── services/          Swappable provider adapters
├── media/             FFmpeg, WhisperX, music
└── utils/             Retry, alerts, paths
```

---

## Cost estimate (4 videos/day)

| Service | Per video | Monthly |
|---|---|---|
| DeepSeek LLM | ~$0.001 | ~$0.12 |
| Fish Audio TTS | ~$0.03 | ~$3.60 |
| Replicate Flux (8 images) | ~$0.16 | ~$19.20 |
| **Total** | **~$0.19** | **~$22.92** |

---

## Assets

- `assets/music/` — Drop royalty-free MP3/WAV tracks here. See `assets/music/SOURCES.md` for attribution requirements.
- `assets/fonts/` — `Anton-Regular.ttf` for thumbnail text. Downloaded automatically by `chill-agent init`.

---

## Important

- All videos are uploaded with `containsSyntheticMedia: true` (YouTube AI disclosure, mandatory).
- Never commit `.env`, `secrets/`, or `outputs/` to git (all gitignored).
- YouTube API quota: 10,000 units/day. Each upload = ~1,650 units. Max 6 uploads/day safely.
