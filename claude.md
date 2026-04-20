# Claude Code Task: Build an Autonomous YouTube Channel Agent ("Chill Dude Explains" clone)

## Your Role

You are a senior Python engineer. Your job is to build a fully autonomous YouTube content pipeline that can run unattended on a VPS and publish ~4 videos per day to a YouTube channel in the style of "Chill Dude Explains" — AI-voiced, AI-illustrated countdown listicles about weird psychology, hidden dangers, bizarre science, and dark curiosity.

I will not be writing code or reviewing individual stages. Build the whole thing. Make sensible decisions. Ask me clarifying questions ONLY when you genuinely cannot proceed (e.g., missing API keys). Otherwise, assume sensible defaults, document them in a `DECISIONS.md` file, and keep going.

---

## Project Overview

Build a Python application called `chill-agent` that, on a cron schedule, performs this loop end-to-end with zero human intervention:

1. Picks a topic (avoiding duplicates from a local DB)
2. Generates a script in the "Chill Dude Explains" voice
3. Generates a voiceover
4. Generates illustrations (one per countdown item + a thumbnail)
5. Assembles a 1080p MP4 with Ken Burns pan/zoom, background music, and optional captions
6. Generates title, description, tags, chapter timestamps
7. Uploads to YouTube via the Data API, scheduled (not all at once)
8. Logs everything to a local DB and tracks performance over time
9. Feeds performance data back into topic selection

---

## Content Formula (This Is Non-Negotiable — It's What Makes the Channel Work)

### Topics
Weird psychology, hidden dangers, bizarre science, misunderstood history, survival trivia, dark curiosity, human-body glitches, myth-busting. Think: *"7 Creepy Things Your Brain Does When You Sleep"*, *"Disturbing Truths About Your Own Memory"*, *"Perfectly Normal Habits That Are Actually Terrifying"*.

### Title rules
- 1–6 words, bold topic-label style
- Uses phrasing like: "Creepy Things…", "Perfectly Normal But…", "Disturbing Truths…", "Weird Human Glitches…", "Popular Advice That's Totally Wrong…"
- Must spark curiosity or mild discomfort immediately
- No generic/obvious phrasing

### Script rules
- Starts with exactly: **"Let's get right into it."**
- Countdown format: "Number seven: [Bold Topic Label]", then ~250–450 words on that item
- Typically 7–10 items per video (let the topic decide)
- Tone: funny, sarcastic, smart, casual
- POV: mostly second-person ("you," "your body," "your brain") — but don't robotically start every paragraph with "you"
- Pacing: energetic paragraph flow, no bullet points, no dead air, no lazy transitions like "Next up" or "Coming soon"
- Voice: like a clever friend on a comedic rant — not dry, not try-hard
- Each item ends with a punchline (irony, metaphor, quick jab). Example style: *"Basically, your nervous system is throwing a tantrum in your honor."*
- Explains real psychology/biology/science in a "smart-dumb" way — simplify without dumbing down, use metaphors and daily-life analogies
- Ends with exactly: **"That's all for today, I'll be making similar videos in the future. Subscribe to see them."**
- Total length: 1,500–2,500 words

### Visual style
- Flat cartoon illustrations, bold outlines, limited palette, quirky expressions
- One image per countdown item + one thumbnail
- 16:9 aspect ratio for video images, 1280x720 for thumbnail
- Consistent style across all videos — lock a style suffix into every image prompt

### Voice style
- Calm, laid-back male voice — "chill guy" archetype
- Pick ONE voice and never change it (channel consistency)

### Video assembly
- Ken Burns slow pan/zoom on each image while the corresponding narration plays
- Background lo-fi music at ~12–15% volume
- Optional burned-in captions (make this configurable)
- 1080p, 30fps, H.264, AAC audio

---

## Technical Stack

Use these. Do not substitute without good reason.

| Layer | Choice | Why |
|---|---|---|
| Language | Python 3.11+ | Ecosystem |
| LLM | DeepSeek API (deepseek-chat / V3.2) via OpenAI SDK | Frontier-class quality at ~$0.28/$0.42 per 1M tokens — 10x cheaper than Claude Sonnet. OpenAI-compatible API = zero migration effort. 5M free tokens on signup. |
| TTS | Fish Audio API (primary) with ElevenLabs as fallback adapter | ~$15/1M chars, #1 on TTS-Arena, much cheaper than ElevenLabs |
| Images | Replicate API running Flux.1 (primary) with an SDXL local fallback adapter | Best cartoon quality at reasonable cost |
| Forced alignment | WhisperX (local) | Word-level timestamps for chapters + captions |
| Video assembly | FFmpeg via `ffmpeg-python` | Industry standard, scriptable |
| Upload | YouTube Data API v3 via `google-api-python-client` | Official |
| DB | SQLite via `sqlalchemy` | Simple, file-based, zero ops |
| Scheduler | APScheduler (in-process) OR system cron — support both | Flexibility |
| Config | `pydantic-settings` reading `.env` | Type-safe config |
| Logging | `structlog` with JSON output | Queryable logs |
| Error alerting | Discord or Slack webhook (configurable) | So I know when something breaks |

---

## Architecture

Build it as a clean modular package. Each stage is a separate module with a single well-defined interface so any stage can be swapped out (e.g., Fish Audio → ElevenLabs).

```
chill-agent/
├── pyproject.toml
├── README.md
├── DECISIONS.md              # Log every non-obvious choice you make
├── .env.example
├── .gitignore
├── Dockerfile
├── docker-compose.yml
├── config/
│   ├── style_suffix.txt      # Locked image style string
│   ├── voice_config.json     # Locked voice ID + settings
│   └── prompts/
│       ├── ideation.md
│       ├── script.md
│       ├── image_prompts.md
│       └── metadata.md
├── src/
│   └── chill_agent/
│       ├── __init__.py
│       ├── cli.py            # `chill-agent run` / `chill-agent run-once` / `chill-agent backfill`
│       ├── orchestrator.py   # Runs the whole pipeline for one video
│       ├── scheduler.py      # Decides when to run, spaces uploads
│       ├── config.py         # Pydantic settings
│       ├── db/
│       │   ├── models.py     # Video, Topic, Run, Metric
│       │   └── repo.py
│       ├── stages/
│       │   ├── ideation.py
│       │   ├── script.py
│       │   ├── tts.py
│       │   ├── images.py
│       │   ├── assembly.py
│       │   ├── thumbnail.py
│       │   ├── metadata.py
│       │   └── upload.py
│       ├── services/         # Swappable provider adapters
│       │   ├── llm/
│       │   │   ├── base.py
│       │   │   └── deepseek.py
│       │   ├── tts/
│       │   │   ├── base.py
│       │   │   ├── fish_audio.py
│       │   │   └── elevenlabs.py
│       │   ├── image/
│       │   │   ├── base.py
│       │   │   ├── replicate_flux.py
│       │   │   └── sdxl_local.py
│       │   └── youtube/
│       │       └── client.py
│       ├── media/
│       │   ├── alignment.py   # WhisperX wrapper → word timestamps
│       │   ├── ffmpeg_ops.py  # Ken Burns, concat, mux, captions
│       │   └── music.py       # Rotates royalty-free background tracks
│       └── utils/
│           ├── retry.py       # Exponential backoff for all API calls
│           ├── alerts.py      # Discord/Slack webhook
│           └── paths.py
├── tests/
│   ├── test_script.py
│   ├── test_assembly.py
│   ├── test_db.py
│   └── fixtures/
└── assets/
    ├── music/                 # Drop royalty-free tracks here
    └── fonts/                 # For thumbnail text overlay
```

---

## Stage-by-Stage Specification

### Stage 1: Ideation (`stages/ideation.py`)

**Input:** Nothing (or optional seed topic from Reddit/YouTube scraping — implement this as optional, flag `--seed-from-reddit`)

**Process:**
1. Pull the list of all past topics from the DB (last 200 videos)
2. Call DeepSeek (deepseek-chat) with the ideation prompt (stored in `config/prompts/ideation.md`)
3. Ask for 10 candidate titles in a strict JSON schema
4. Filter out any that are too similar to past titles (use simple cosine similarity on embeddings, threshold 0.82)
5. Score remaining candidates against a "performance prior" — if a past topic cluster has performed well (views/hour in first 24h), weight similar topics higher
6. Return the winning title + a 2-sentence topic brief

**Prompt template for ideation.md:**
```
You are a YouTube content ideation assistant for a viral educational-entertainment channel that mixes science, psychology, history, survival, and dark curiosity.

Generate 10 viral video title ideas that match this specific tone and topic style:
- Titles should sound fascinating, weird, slightly creepy, or myth-busting
- Blend science, human biology, psychology, history, danger, survival, or space
- Use casual, click-inducing language like: "Creepy Things…", "Perfectly Normal But…", "Disturbing Truths…", "Weird Human Glitches…", "Popular Advice That's Totally Wrong…"
- Focus on hidden dangers, forgotten truths, bizarre facts, or misunderstood phenomena
- Avoid generic or obvious phrasing
- 1–6 words per title, bold topic-label style

Titles to AVOID (already used):
{past_titles}

Return ONLY a JSON array of 10 objects, each with: {"title": str, "brief": str (2 sentences explaining the angle)}
```

### Stage 2: Script (`stages/script.py`)

**Input:** Title + brief from Stage 1

**Process:**
1. Call DeepSeek (deepseek-chat, temperature=1.3) with the script prompt
2. Request the script be written in natural parts (don't blast the full 2,500 words in one go — better quality if you prompt it to do intro → each item → outro)
3. Actually — just prompt once with clear instructions, DeepSeek handles it fine
4. Also request: image prompts per segment, thumbnail prompt, metadata (title, desc, tags)
5. Return a structured object: `Script(segments=[...], intro, outro, thumbnail_prompt, metadata)`

**Prompt template for script.md:**
```
You are writing a long-form YouTube narration script in the exact style of a quirky, sarcastic, educational countdown video that explores weird psychology, misunderstood science, or bizarre human behavior.

Topic: {title}
Angle: {brief}

Rules (FOLLOW EXACTLY):
- Start the script with exactly: "Let's get right into it."
- Then begin the countdown. Number the items from the highest number DOWN to 1 (e.g., "Number seven:", "Number six:", …, "Number one:")
- The number of items depends on the topic — use as many as needed, typically 7–10
- Each item starts with: "Number X: [Bold Topic Label]" (e.g., "Number five: Button Phobia")
- Each item is 250–450 words
- End the entire script with exactly: "That's all for today, I'll be making similar videos in the future. Subscribe to see them."

Tone:
- Funny, sarcastic, smart, casual
- Second-person POV (you, your body, your brain) — use often but don't start every paragraph with "you"
- Energetic paragraph flow — NO bullet points, NO dead air
- Like a clever friend on a comedic rant
- Real psychology/biology explained "smart-dumb" style — metaphors, daily-life analogies, vivid imagery
- Each item ends with a punchline: irony, metaphor, comparison, or quick jab
- No lazy transitions ("Next up", "Coming soon", "Let's dive in")

Total length: 1,500–2,500 words.

Return a JSON object with this exact structure:
{
  "title": "final polished title",
  "description": "YouTube description — 2-3 paragraph hook, then {CHAPTERS} placeholder, then 5 hashtags",
  "tags": ["tag1", "tag2", ...] (12-15 tags),
  "thumbnail_prompt": "detailed image prompt for thumbnail",
  "segments": [
    {
      "number": 7,
      "label": "Button Phobia",
      "narration": "Number seven: Button Phobia...\n\n[full 250-450 word item text]",
      "image_prompt": "detailed image prompt for this segment"
    },
    ...
  ],
  "outro": "That's all for today, I'll be making similar videos in the future. Subscribe to see them."
}
```

### LLM Service Implementation Notes (`services/llm/deepseek.py`)

**CRITICAL:** DeepSeek uses an OpenAI-compatible API. Install `openai` SDK, NOT any DeepSeek-specific package.

```python
# pip install openai
from openai import OpenAI

client = OpenAI(
    api_key=os.environ["DEEPSEEK_API_KEY"],
    base_url="https://api.deepseek.com",   # NOT https://api.openai.com
)

response = client.chat.completions.create(
    model="deepseek-chat",  # maps to DeepSeek V3.2 non-thinking mode
    messages=[
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ],
    temperature=1.3,  # DeepSeek docs: 1.3 for creative writing, 0.0 for code
    response_format={"type": "json_object"},  # force JSON output for structured responses
)

text = response.choices[0].message.content
```

**Key differences from Anthropic SDK:**
- Uses `openai` Python package, just with a different `base_url`
- Model names: `deepseek-chat` (general) or `deepseek-reasoner` (chain-of-thought)
- Use `deepseek-chat` for ALL pipeline stages (ideation, script, metadata) — reasoner is overkill and burns more tokens
- Supports `response_format={"type": "json_object"}` for reliable JSON output — USE THIS for script/ideation/metadata stages
- Context caching is automatic — structure prompts with a consistent system prefix to get 90% input cost reduction on repeated calls
- Temperature: 1.3 for script writing (creative), 1.0 for ideation, 0.0 for metadata extraction
- Max output: 8K tokens in chat mode — more than enough for scripts (2,500 words ≈ ~3,500 tokens)
- If you hit rate limits during peak hours, implement exponential backoff (429 handling). DeepSeek can be flaky under load — the retry decorator from `utils/retry.py` must cover this

**Cost estimate at 4 videos/day:**
- ~3,000 input tokens + ~4,000 output tokens per video (script + ideation + metadata)
- Monthly: ~840K input + ~480K output = roughly $0.44/month at cache-miss rates
- With caching (same system prompt): even less. LLM costs are effectively negligible.

### Stage 3: TTS (`stages/tts.py` + `services/tts/fish_audio.py`)

**Process:**
1. Concatenate segments into one full narration string (with 0.8s silence markers between items — use SSML-style pauses or insert silence in post)
2. Call the TTS service — chunk if needed (Fish Audio handles long input, but safer to send per-segment and stitch)
3. Save per-segment MP3s AND a full concatenated WAV
4. Return paths + per-segment durations

**Voice config:** Stored in `config/voice_config.json`. Lock a single voice ID. Expose via env var `TTS_VOICE_ID`.

**Adapter interface:**
```python
class TTSProvider(Protocol):
    def synthesize(self, text: str, voice_id: str, output_path: Path) -> AudioResult: ...

@dataclass
class AudioResult:
    path: Path
    duration_seconds: float
    sample_rate: int
```

### Stage 4: Images (`stages/images.py` + `services/image/replicate_flux.py`)

**Process:**
1. For each segment's `image_prompt`, append the locked style suffix from `config/style_suffix.txt`
2. Generate one 1920x1080 image per segment + one 1280x720 thumbnail
3. Run them in parallel (asyncio or a thread pool — cap concurrency at 4 so you don't hit rate limits)
4. Retry on failure with exponential backoff
5. Save to `outputs/{video_id}/images/seg_{n}.png` and `thumbnail.png`

**Default style suffix** (put in `config/style_suffix.txt`):
```
flat cartoon illustration, bold black outlines, limited vibrant color palette, quirky exaggerated expressions, clean composition, centered subject, Chill Dude Explains channel style, flat shading, no gradients, 16:9
```

### Stage 5: Forced Alignment (`media/alignment.py`)

**Process:**
1. Run WhisperX on the full narration audio + the full narration text
2. Get word-level timestamps
3. Derive segment-level timestamps (start/end time for each countdown item)
4. Return a list of `(segment_idx, start_sec, end_sec)`

This gives us (a) chapter timestamps for the description, (b) accurate image switching in video assembly, (c) caption SRT if enabled.

### Stage 6: Video Assembly (`stages/assembly.py` + `media/ffmpeg_ops.py`)

**Process:**
1. For each segment, build a video clip:
   - Input: the segment image (PNG)
   - Apply Ken Burns: slow zoom from 1.0x to 1.08x OR slow pan across the image, duration = segment audio length
   - Output: per-segment MP4 at 1920x1080 @ 30fps
2. Concatenate all segment MP4s
3. Mux with the full narration audio
4. Mix in background music at 12% volume (pick a random track from `assets/music/`, loop if needed, duck under narration)
5. Optionally burn captions (WhisperX SRT → FFmpeg `subtitles` filter with readable font)
6. Output: `outputs/{video_id}/final.mp4`

**FFmpeg notes:**
- Use `zoompan` filter for Ken Burns. Alternate direction per segment (zoom in, zoom out, pan left, pan right) for variety.
- Use `amix` with proper weights for music + narration
- Use `sidechaincompress` to duck music under voice
- Always re-encode to H.264 high profile, yuv420p, 30fps, AAC 192k

### Stage 7: Thumbnail (`stages/thumbnail.py`)

**Process:**
1. Take the generated thumbnail image
2. Overlay 3–5 big bold words from the title using Pillow
3. Use a high-impact font (include one in `assets/fonts/` — Anton, Bebas Neue, or Impact substitute)
4. White text with thick black stroke, slight drop shadow
5. Optionally add a red or yellow accent circle/arrow highlighting the subject
6. Generate 2 variants (different text placements) so YouTube's built-in thumbnail testing can pick
7. Save as `thumbnail_a.jpg` and `thumbnail_b.jpg`

### Stage 8: Metadata Finalization (`stages/metadata.py`)

**Process:**
1. Take the metadata from the script stage
2. Replace `{CHAPTERS}` placeholder in description with real timestamps from forced alignment, formatted as:
   ```
   0:00 Intro
   0:42 Number 7: Button Phobia
   2:15 Number 6: …
   ```
3. Append standard channel boilerplate (CTA, disclaimers)
4. Return final title, description, tags, category=27 (Education), language=en

### Stage 9: Upload (`stages/upload.py` + `services/youtube/client.py`)

**Process:**
1. Authenticate with OAuth 2.0 using stored refresh token
2. Decide `publishAt` time:
   - Look at the DB, find the next empty 6-hour slot from now
   - Videos should publish at roughly 08:00, 14:00, 20:00, 02:00 UTC (configurable)
   - Never schedule more than 7 days out
3. Call `videos.insert` with:
   - Video file
   - Title, description, tags
   - `privacyStatus: "private"`, `publishAt: <scheduled_time>`
   - `categoryId: "27"` (Education)
   - `madeForKids: false`
   - `selfDeclaredMadeForKids: false`
   - `containsSyntheticMedia: true` — **CRITICAL**, YouTube requires AI disclosure
4. Call `thumbnails.set` with thumbnail_a.jpg
5. Save the video ID + scheduled time to DB
6. If quota exceeded, back off and retry next day

**Quota notes:** YouTube gives 10,000 units/day. Each upload = 1,600 units. Thumbnail set = 50 units. Max safe = 6 uploads/day. Log quota usage.

### Stage 10: Performance Tracking (`stages/track.py`)

Separate cron job, runs every 6 hours:
1. Pull stats (views, likes, CTR, AVD) for all videos published in last 30 days via YouTube Analytics API
2. Store time-series in DB
3. Compute per-topic-cluster performance scores that ideation can use next run

---

## Orchestrator Behavior

`orchestrator.py` runs the full pipeline for ONE video:

```python
def make_one_video() -> VideoResult:
    run = db.start_run()
    try:
        topic = ideate(past_topics=db.recent_topics(200), performance=db.topic_stats())
        script = generate_script(topic)
        audio = synthesize_voice(script)
        alignment = align(audio, script)
        images = generate_images(script)
        thumbnail = make_thumbnail(images.thumbnail, script.title)
        video_path = assemble_video(audio, images, alignment)
        metadata = finalize_metadata(script, alignment)
        upload_result = upload(video_path, thumbnail, metadata)
        db.finish_run(run, upload_result)
        return upload_result
    except Exception as e:
        db.fail_run(run, e)
        alert(f"Pipeline failed at stage {run.current_stage}: {e}")
        raise
```

Every stage must be **idempotent and resumable** — if stage 5 fails, I should be able to run `chill-agent resume <run_id>` and it picks up from where it crashed, reusing already-generated artifacts.

Store every intermediate artifact on disk in `outputs/{run_id}/` so nothing is lost.

---

## CLI

```
chill-agent init                    # create DB, check env, prompt for OAuth flow
chill-agent run                     # run the scheduler forever
chill-agent run-once                # produce and upload one video, then exit
chill-agent resume <run_id>         # resume a failed run
chill-agent backfill --count 10     # produce 10 videos fast for channel warm-up
chill-agent stats                   # print performance summary
chill-agent dry-run                 # full pipeline but skip upload (for testing)
```

---

## Configuration (`.env.example`)

```
# LLM (DeepSeek — OpenAI-compatible API)
DEEPSEEK_API_KEY=
LLM_MODEL=deepseek-chat            # DeepSeek V3.2 non-thinking mode (best for scripts)
LLM_BASE_URL=https://api.deepseek.com   # Do NOT change unless using a proxy/router
LLM_TEMPERATURE=1.3                # DeepSeek docs recommend 1.3 for creative writing

# TTS
TTS_PROVIDER=fish_audio      # or elevenlabs or google_cloud
FISH_AUDIO_API_KEY=
ELEVENLABS_API_KEY=
TTS_VOICE_ID=                # locked voice ID

# Images
IMAGE_PROVIDER=replicate_flux    # or sdxl_local
REPLICATE_API_TOKEN=
FLUX_MODEL=black-forest-labs/flux-1.1-pro

# YouTube
YOUTUBE_CLIENT_SECRETS_FILE=./secrets/client_secret.json
YOUTUBE_TOKEN_FILE=./secrets/token.json
YOUTUBE_CHANNEL_ID=

# Scheduling
VIDEOS_PER_DAY=4
PUBLISH_HOURS_UTC=8,14,20,2
ENABLE_CAPTIONS=true

# Alerts
DISCORD_WEBHOOK_URL=
# or SLACK_WEBHOOK_URL=

# Storage
OUTPUT_DIR=./outputs
DB_URL=sqlite:///./chill_agent.db
```

---

## Hard Requirements (Must-Haves)

1. **Idempotency**: Every stage writes its output to disk. Re-running a stage with the same inputs returns the cached output unless `--force` is passed.
2. **Retry with backoff**: Every external API call wrapped in a retry decorator (3 attempts, exponential backoff, 2s → 8s → 30s).
3. **Structured logging**: Every pipeline step logs JSON with `run_id`, `stage`, `duration_ms`, `status`.
4. **Alerts**: Pipeline failure → Discord/Slack ping with run_id and the failing stage.
5. **Cost tracking**: Log estimated $ cost per run (DeepSeek tokens at $0.28/$0.42 per 1M, TTS chars, image count × unit price). Sum daily total.
6. **Safety rails**:
   - Before upload, verify the final MP4: duration > 3 min, < 20 min; audio track present; no silent segments > 3s.
   - Content check: run a cheap moderation pass on the script before spending money on TTS/images. Reject scripts that contain gore, slurs, sexual content, or real-person defamation.
7. **AI disclosure**: `containsSyntheticMedia: true` on every upload, ALWAYS.
8. **Channel warm-up mode**: `--warmup` flag limits to 1 video/day for the first 14 days before ramping to 4/day.
9. **Testability**: `tests/` directory with at least: DB tests, script parsing tests, FFmpeg command-building tests (no actual encoding), and one integration test using mocked APIs for a full dry-run.
10. **Dockerized**: `docker-compose up` should start the scheduler.

---

## Nice-to-Haves (Build If Time Permits)

- A/B thumbnail testing via YouTube's built-in feature (upload 3 variants)
- Reddit topic seeding (scrape r/todayilearned, r/askreddit, r/Damnthatsinteresting top posts of the day)
- Local web dashboard (FastAPI + simple HTML) showing: queue, recent runs, performance stats, cost this month
- Multi-channel support (one config per channel, run multiple in parallel)

---

## What NOT to Do

- Do NOT use GUI automation, Selenium, or Puppeteer to upload to YouTube. Use the official Data API only.
- Do NOT clone a real person's voice.
- Do NOT generate images of real public figures or copyrighted characters.
- Do NOT use copyrighted music. Only royalty-free tracks from YouTube Audio Library, Uppbeat free tier, or Pixabay Music. Document the source of every track in `assets/music/SOURCES.md`.
- Do NOT bypass YouTube's AI disclosure requirement. The `containsSyntheticMedia` flag must always be true.
- Do NOT hardcode API keys. Everything goes through `.env` / pydantic settings.
- Do NOT make the pipeline monolithic. Every stage must be independently callable for testing and resumption.

---

## Deliverables

When done, I expect:

1. A working repo I can clone
2. `README.md` with: setup steps, how to get each API key, how to do YouTube OAuth, how to run in dev vs production
3. `DECISIONS.md` documenting every non-obvious choice you made and why
4. A working `docker-compose up` that boots the whole thing
5. A `chill-agent dry-run` that produces a full video locally without uploading, proving the pipeline works end-to-end
6. Tests that pass with `pytest`
7. At least one sample output video in `examples/` so I can verify the style is right

---

## Start Here

1. Read this entire spec. Then read it again.
2. Create the directory structure.
3. Write `DECISIONS.md` and `README.md` skeleton first.
4. Build in this order: config → DB → DeepSeek LLM service → script stage → TTS stage → images stage → assembly → thumbnail → metadata → upload → orchestrator → scheduler → CLI → Docker → tests.
5. Build each stage with a working dry-run before moving to the next. `chill-agent dry-run` should work after each stage is added.
6. If anything is genuinely ambiguous, ask ONE consolidated question per batch. Don't drip-feed questions.

Begin.