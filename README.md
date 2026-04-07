# Subgen (Groq Fork)

<img src="https://raw.githubusercontent.com/McCloudS/subgen/main/icon.png" width="200">

A **Groq-powered** fork of [McCloudS/subgen](https://github.com/McCloudS/subgen) that replaces local `faster-whisper` / `stable-ts` transcription with [Groq's](https://groq.com) cloud-based Whisper API. This makes it possible to run Subgen on low-power hardware (e.g., Intel i5, no GPU) by offloading all transcription to Groq's free tier.

---

## 🎬 What is this?

Subgen transcribes your personal media to create subtitles (`.srt` or `.lrc`) from audio/video files. It can transcribe non-English languages to themselves, or translate foreign languages into English.

It integrates with **Bazarr** (as a Whisper Provider), or runs via webhooks triggered by **Plex, Emby, Jellyfin, or Tautulli** servers.

### Key Differences from Original Subgen

| Feature | Original Subgen | This Fork |
|---|---|---|
| Transcription engine | Local faster-whisper + stable-ts | Groq cloud API |
| GPU required | Recommended (CUDA) | **No** |
| Docker image size | ~8-10 GB | **~200 MB** |
| Model download | Required on first run | Not needed |
| Free tier limits | None (local) | 8 hours audio/day (Groq free) |

---

## 🚀 Quick Start

### 1. Get a Groq API Key

Sign up at [console.groq.com](https://console.groq.com) and create a free API key.

### 2. Docker Compose

```yaml
services:
  subgen:
    container_name: subgen
    image: ghcr.io/digitalzenify/subgen:latest
    environment:
      - "GROQ_API_KEY=gsk_your_key_here"
      - "GROQ_MODEL=whisper-large-v3-turbo"
      - "PROCADDEDMEDIA=True"
      - "JELLYFINTOKEN=your_token"
      - "JELLYFINSERVER=http://jellyfin:8096"
      - "WEBHOOKPORT=9000"
    volumes:
      - /path/to/tv:/tv
      - /path/to/movies:/movies
    ports:
      - "9000:9000"
```

### 3. Pull and Run

```bash
docker pull ghcr.io/digitalzenify/subgen:latest
docker compose up -d
```

---

## ⚙️ Environment Variables

### Groq API Configuration

| Variable | Default | Description |
|---|---|---|
| `GROQ_API_KEY` | *(required)* | Your Groq API key from [console.groq.com](https://console.groq.com) |
| `GROQ_MODEL` | `whisper-large-v3-turbo` | Model to use. Options: `whisper-large-v3`, `whisper-large-v3-turbo` |
| `GROQ_MAX_CHUNK_SIZE_MB` | `20` | Max audio chunk size in MB (must be under 25MB for Groq free tier) |
| `GROQ_RETRY_ATTEMPTS` | `3` | Number of retries on rate limit or transient errors |
| `GROQ_RETRY_DELAY` | `5` | Initial delay in seconds between retries (exponential backoff) |

### Subtitle Configuration

| Variable | Default | Description |
|---|---|---|
| `SUBTITLE_TAG` | *(empty)* | Custom tag in subtitle filename. E.g., `groq` → `Movie.en.groq.srt`. Useful to distinguish AI subs from human subs in Jellyfin/Plex. |
| `SUBTITLE_LANGUAGE_NAME` | *(empty)* | Override subtitle language name (legacy: `NAMESUBLANG`) |
| `SUBTITLE_LANGUAGE_NAMING_TYPE` | `ISO_639_2_B` | Language naming format: `ISO_639_1`, `ISO_639_2_T`, `ISO_639_2_B`, `NAME`, `NATIVE` |
| `SHOW_IN_SUBNAME_SUBGEN` | `True` | Include "subgen" in subtitle filename |

### Media Server Integration

| Variable | Default | Description |
|---|---|---|
| `PLEX_TOKEN` / `PLEXTOKEN` | `token here` | Plex authentication token |
| `PLEX_SERVER` / `PLEXSERVER` | `http://192.168.1.111:32400` | Plex server URL |
| `JELLYFIN_TOKEN` / `JELLYFINTOKEN` | `token here` | Jellyfin authentication token |
| `JELLYFIN_SERVER` / `JELLYFINSERVER` | `http://192.168.1.111:8096` | Jellyfin server URL |

### Processing Control

| Variable | Default | Description |
|---|---|---|
| `PROCESS_ADDED_MEDIA` / `PROCADDEDMEDIA` | `True` | Process media when added to library |
| `PROCESS_MEDIA_ON_PLAY` / `PROCMEDIAONPLAY` | `True` | Process media when playback starts |
| `CONCURRENT_TRANSCRIPTIONS` | `2` | Number of concurrent transcription workers |
| `TRANSCRIBE_OR_TRANSLATE` | `transcribe` | `transcribe` or `translate` (translate to English) |
| `TRANSCRIBE_FOLDERS` | *(empty)* | Pipe-separated folders to scan on startup |
| `MONITOR` | `False` | Watch `TRANSCRIBE_FOLDERS` for new files |

### Skip Configuration

| Variable | Default | Description |
|---|---|---|
| `SKIP_IF_EXTERNAL_SUBTITLES_EXIST` / `SKIPIFEXTERNALSUB` | `False` | Skip if external subtitle files exist |
| `SKIP_IF_TARGET_SUBTITLES_EXIST` | `True` | Skip if subtitles in target language already exist |
| `SKIP_IF_INTERNAL_SUBTITLES_LANGUAGE` / `SKIPIFINTERNALSUBLANG` | *(empty)* | Skip if internal subs in this language exist |
| `SKIP_SUBTITLE_LANGUAGES` / `SKIP_LANG_CODES` | *(empty)* | Pipe-separated language codes to skip |
| `SKIP_IF_AUDIO_LANGUAGES` / `SKIP_IF_AUDIO_TRACK_IS` | *(empty)* | Skip if audio track is in this language |
| `SKIP_UNKNOWN_LANGUAGE` | `False` | Skip files with unknown language |
| `FORCE_DETECTED_LANGUAGE_TO` | *(empty)* | Force detected language to this value |

### Other Settings

| Variable | Default | Description |
|---|---|---|
| `WEBHOOK_PORT` / `WEBHOOKPORT` | `9000` | Port for the webhook server |
| `DEBUG` | `True` | Enable debug logging |
| `USE_PATH_MAPPING` | `False` | Enable path mapping |
| `PATH_MAPPING_FROM` | `/tv` | Source path for mapping |
| `PATH_MAPPING_TO` | `/Volumes/TV` | Destination path for mapping |
| `APPEND` | `False` | Append "Transcribed by" text to subtitles |
| `LRC_FOR_AUDIO_FILES` | `True` | Generate LRC files for audio files |
| `ASR_TIMEOUT` | `18000` | Timeout in seconds for ASR endpoint |
| `WEBHOOK_URL_COMPLETED` | *(empty)* | URL to POST when transcription completes |
| `PLEX_QUEUE_NEXT_EPISODE` | `False` | Auto-queue next Plex episode |
| `PLEX_QUEUE_SEASON` | `False` | Auto-queue entire Plex season |
| `PLEX_QUEUE_SERIES` | `False` | Auto-queue entire Plex series |

---

## 📺 Bazarr Setup

This fork works identically with Bazarr's Whisper Provider:

1. In Bazarr, go to **Settings → Subtitles → Whisper Provider**
2. Set the endpoint to `http://subgen:9000` (or your Subgen IP/port)
3. Bazarr will send audio to Subgen, which forwards it to Groq and returns SRT content

No changes are needed on the Bazarr side.

---

## 🔗 Webhook Setup

### Jellyfin
1. Install the **Webhook** plugin from Jellyfin's plugin catalog
2. Add a new webhook:
   - URL: `http://subgen:9000/jellyfin`
   - Notification Type: `Item Added` and/or `Playback Start`

### Plex
1. Go to **Settings → Webhooks** (requires Plex Pass)
2. Add webhook: `http://subgen:9000/plex`

### Emby
1. Go to **Server → Notifications → Webhooks**
2. Add webhook: `http://subgen:9000/emby`

### Tautulli
1. Go to **Settings → Notification Agents → Add a new notification agent → Webhook**
2. URL: `http://subgen:9000/tautulli`

---

## 📊 Groq Free Tier Limits

| Limit | Value |
|---|---|
| Audio per day | **28,800 seconds** (8 hours) |
| Requests per minute | 20 |
| Requests per day | 2,000 |
| Max file size per request | 25 MB |

Subgen automatically:
- Splits large audio files into chunks under the size limit
- Retries with exponential backoff on rate limit errors
- Tracks daily usage and warns when approaching limits
- Shows usage stats at the `/status` endpoint

---

## 🏷️ Subtitle Tag Feature

Set `SUBTITLE_TAG` to add a custom tag to subtitle filenames:

```
SUBTITLE_TAG=groq
```

This changes the output filename from:
```
Movie (2024).eng.srt  →  Movie (2024).eng.groq.srt
```

This makes it easy to identify AI-generated subtitles in Jellyfin/Plex, similar to how Lingarr handles translated subtitle tagging.

---

## 🐳 Docker Image

The image is automatically built and published to GitHub Container Registry:

```bash
docker pull ghcr.io/digitalzenify/subgen:latest
```

Available tags:
- `latest` - latest build from main branch
- `v1.0.0` - specific version tags
- `sha-abc1234` - specific commit builds

---

## Credits

- Original [Subgen](https://github.com/McCloudS/subgen) by McCloudS
- Powered by [Groq](https://groq.com) Whisper API
