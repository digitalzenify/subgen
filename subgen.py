subgen_version = '2026.04.9'

"""
ENVIRONMENT VARIABLES DOCUMENTATION

This application supports both new standardized environment variable names and legacy names for backwards compatibility. The new names follow a consistent naming convention: 

STANDARDIZED NAMING CONVENTION:
- Use UPPERCASE with underscores for separation
- Group related variables with consistent prefixes: 
  * PLEX_* for Plex server integration
  * JELLYFIN_* for Jellyfin server integration
  * PROCESS_* for media processing triggers
  * SKIP_* for all skip conditions
  * SUBTITLE_* for subtitle-related settings
  * GROQ_* for Groq API settings

BACKWARDS COMPATIBILITY: 
Legacy environment variable names are still supported. If both new and old names are set,
the new standardized name takes precedence. 

NEW NAME → OLD NAME (for backwards compatibility):
- PLEX_TOKEN → PLEXTOKEN
- PLEX_SERVER → PLEXSERVER
- JELLYFIN_TOKEN → JELLYFINTOKEN
- JELLYFIN_SERVER → JELLYFINSERVER
- PROCESS_ADDED_MEDIA → PROCADDEDMEDIA
- PROCESS_MEDIA_ON_PLAY → PROCMEDIAONPLAY
- SUBTITLE_LANGUAGE_NAME → NAMESUBLANG
- WEBHOOK_PORT → WEBHOOKPORT
- SKIP_IF_EXTERNAL_SUBTITLES_EXIST → SKIPIFEXTERNALSUB
- SKIP_IF_TARGET_SUBTITLES_EXIST → SKIP_IF_TO_TRANSCRIBE_SUB_ALREADY_EXIST
- SKIP_IF_INTERNAL_SUBTITLES_LANGUAGE → SKIPIFINTERNALSUBLANG
- SKIP_SUBTITLE_LANGUAGES → SKIP_LANG_CODES
- SKIP_IF_AUDIO_LANGUAGES → SKIP_IF_AUDIO_TRACK_IS
- SKIP_ONLY_SUBGEN_SUBTITLES → ONLY_SKIP_IF_SUBGEN_SUBTITLE
- SKIP_IF_NO_LANGUAGE_BUT_SUBTITLES_EXIST → SKIP_IF_LANGUAGE_IS_NOT_SET_BUT_SUBTITLES_EXIST

MIGRATION GUIDE:
Users can gradually migrate to the new names. Both will work simultaneously during the
transition period. The old names may be deprecated in future versions. 
"""

from language_code import LanguageCode
from datetime import datetime
from threading import Lock, Event
import os
import json
import re
import xml.etree.ElementTree as ET
import threading
import sys
import time
import queue
import logging
import gc
import hashlib
import asyncio
import shutil
import subprocess
import tempfile
from typing import Union, Any, Optional, List
from fastapi import FastAPI, File, UploadFile, Query, Header, Body, Form, Request
from fastapi.responses import StreamingResponse
import requests
import ffmpeg
import ast
from watchdog.observers.polling import PollingObserver as Observer
from watchdog.events import FileSystemEventHandler
from groq import Groq

def convert_to_bool(in_bool):
    # Convert the input to string and lower case, then check against true values
    return str(in_bool).lower() in ('true', 'on', '1', 'y', 'yes')

def get_env_with_fallback(new_name: str, old_name: str, default_value=None, convert_func=None):
    """
    Get environment variable with backwards compatibility fallback.
    
    Args:
        new_name: The new standardized environment variable name
        old_name: The legacy environment variable name for backwards compatibility
        default_value: Default value if neither variable is set
        convert_func: Optional function to convert the value (e.g., convert_to_bool, int)
    
    Returns:
        The environment variable value, converted if convert_func is provided
    """
    # Try new name first, then fall back to old name
    value = os.getenv(new_name) or os.getenv(old_name)
    
    if value is None:
        value = default_value
    
    # Apply conversion function if provided
    if convert_func and value is not None:
        return convert_func(value)
    
    return value
    
# Server Integration - with backwards compatibility
plextoken = get_env_with_fallback('PLEX_TOKEN', 'PLEXTOKEN', 'token here')
plexserver = get_env_with_fallback('PLEX_SERVER', 'PLEXSERVER', 'http://192.168.1.111:32400')
jellyfintoken = get_env_with_fallback('JELLYFIN_TOKEN', 'JELLYFINTOKEN', 'token here')
jellyfinserver = get_env_with_fallback('JELLYFIN_SERVER', 'JELLYFINSERVER', 'http://192.168.1.111:8096')

# Groq API Configuration
groq_api_key = os.getenv('GROQ_API_KEY', '')
groq_model = os.getenv('GROQ_MODEL', 'whisper-large-v3-turbo')
groq_max_chunk_size_mb = int(os.getenv('GROQ_MAX_CHUNK_SIZE_MB', 20))
groq_retry_attempts = int(os.getenv('GROQ_RETRY_ATTEMPTS', 3))
groq_retry_delay = int(os.getenv('GROQ_RETRY_DELAY', 5))
GROQ_API_MAX_FILE_SIZE_BYTES = 25 * 1024 * 1024  # Groq API 25MB upload limit

# Subtitle Tag Configuration
subtitle_tag = os.getenv('SUBTITLE_TAG', '')

# Processing Control - with backwards compatibility
procaddedmedia = get_env_with_fallback('PROCESS_ADDED_MEDIA', 'PROCADDEDMEDIA', True, convert_to_bool)
procmediaonplay = get_env_with_fallback('PROCESS_MEDIA_ON_PLAY', 'PROCMEDIAONPLAY', True, convert_to_bool)

# Subtitle Configuration - with backwards compatibility
namesublang = get_env_with_fallback('SUBTITLE_LANGUAGE_NAME', 'NAMESUBLANG', '')

# System Configuration - with backwards compatibility
webhookport = get_env_with_fallback('WEBHOOK_PORT', 'WEBHOOKPORT', 9000, int)
concurrent_transcriptions = int(os.getenv('CONCURRENT_TRANSCRIPTIONS', 2))
debug = convert_to_bool(os.getenv('DEBUG', True))
use_path_mapping = convert_to_bool(os.getenv('USE_PATH_MAPPING', False))
path_mapping_from = os.getenv('PATH_MAPPING_FROM', r'/tv')
path_mapping_to = os.getenv('PATH_MAPPING_TO', r'/Volumes/TV')
monitor = convert_to_bool(os.getenv('MONITOR', False))
transcribe_folders = os.getenv('TRANSCRIBE_FOLDERS', '')
transcribe_or_translate = os.getenv('TRANSCRIBE_OR_TRANSLATE', 'transcribe').lower()
append = convert_to_bool(os.getenv('APPEND', False))
reload_script_on_change = convert_to_bool(os.getenv('RELOAD_SCRIPT_ON_CHANGE', False))
lrc_for_audio_files = convert_to_bool(os.getenv('LRC_FOR_AUDIO_FILES', True))
asr_timeout = int(os.getenv('ASR_TIMEOUT', 18000))
webhook_url_completed = os.getenv('WEBHOOK_URL_COMPLETED', '')

# Skip Configuration - with backwards compatibility
skipifexternalsub = get_env_with_fallback('SKIP_IF_EXTERNAL_SUBTITLES_EXIST', 'SKIPIFEXTERNALSUB', False, convert_to_bool)
skip_if_to_transcribe_sub_already_exist = get_env_with_fallback('SKIP_IF_TARGET_SUBTITLES_EXIST', 'SKIP_IF_TO_TRANSCRIBE_SUB_ALREADY_EXIST', True, convert_to_bool)
skipifinternalsublang = LanguageCode.from_string(get_env_with_fallback('SKIP_IF_INTERNAL_SUBTITLES_LANGUAGE', 'SKIPIFINTERNALSUBLANG', ''))
plex_queue_next_episode = convert_to_bool(os.getenv('PLEX_QUEUE_NEXT_EPISODE', False))
plex_queue_season = convert_to_bool(os.getenv('PLEX_QUEUE_SEASON', False))
plex_queue_series = convert_to_bool(os.getenv('PLEX_QUEUE_SERIES', False))
# Language and Skip Configuration - with backwards compatibility
skip_lang_codes_list = ([LanguageCode.from_string(code) for code in get_env_with_fallback('SKIP_SUBTITLE_LANGUAGES', 'SKIP_LANG_CODES', '').split("|")]
        if get_env_with_fallback('SKIP_SUBTITLE_LANGUAGES', 'SKIP_LANG_CODES')
    else[]
)
force_detected_language_to = LanguageCode.from_string(os.getenv('FORCE_DETECTED_LANGUAGE_TO', ''))
preferred_audio_languages =[
    LanguageCode.from_string(code) 
    for code in os.getenv('PREFERRED_AUDIO_LANGUAGES', 'eng').split("|")
]
limit_to_preferred_audio_languages = convert_to_bool(os.getenv('LIMIT_TO_PREFERRED_AUDIO_LANGUAGE', False))
skip_if_audio_track_is_in_list = ([LanguageCode.from_string(code) for code in get_env_with_fallback('SKIP_IF_AUDIO_LANGUAGES', 'SKIP_IF_AUDIO_TRACK_IS', '').split("|")]
    if get_env_with_fallback('SKIP_IF_AUDIO_LANGUAGES', 'SKIP_IF_AUDIO_TRACK_IS')
    else[]
)

# Additional Subtitle Configuration - with backwards compatibility
subtitle_language_naming_type = os.getenv('SUBTITLE_LANGUAGE_NAMING_TYPE', 'ISO_639_2_B')
only_skip_if_subgen_subtitle = get_env_with_fallback('SKIP_ONLY_SUBGEN_SUBTITLES', 'ONLY_SKIP_IF_SUBGEN_SUBTITLE', False, convert_to_bool)
skip_unknown_language = convert_to_bool(os.getenv('SKIP_UNKNOWN_LANGUAGE', False))
skip_if_language_is_not_set_but_subtitles_exist = get_env_with_fallback('SKIP_IF_NO_LANGUAGE_BUT_SUBTITLES_EXIST', 'SKIP_IF_LANGUAGE_IS_NOT_SET_BUT_SUBTITLES_EXIST', False, convert_to_bool)
show_in_subname_subgen = convert_to_bool(os.getenv('SHOW_IN_SUBNAME_SUBGEN', True))

VIDEO_EXTENSIONS = (
    ".mp4", ".mkv", ".avi", ".mov", ".wmv", ".flv", ".webm", ".mpg", ".mpeg", 
    ".3gp", ".ogv", ".vob", ".rm", ".rmvb", ".ts", ".m4v", ".f4v", ".svq3", 
    ".asf", ".m2ts", ".divx", ".xvid"
)

AUDIO_EXTENSIONS = (
    ".mp3", ".wav", ".aac", ".flac", ".ogg", ".wma", ".alac", ".m4a", ".opus", 
    ".aiff", ".aif", ".pcm", ".ra", ".ram", ".mid", ".midi", ".ape", ".wv", 
    ".amr", ".vox", ".tak", ".spx", ".m4b", ".mka"
)

app = FastAPI()

@app.on_event("startup")
async def startup_event():
    if transcribe_folders:
        threading.Thread(target=transcribe_existing, args=(transcribe_folders,), daemon=True).start()

in_docker = os.path.exists('/.dockerenv')
docker_status = "Docker" if in_docker else "Standalone"

# ============================================================================
# GROQ API CLIENT & RATE LIMIT TRACKING
# ============================================================================

groq_client = None

# Daily usage tracking
_daily_audio_seconds = 0.0
_daily_request_count = 0
_daily_reset_date = None
_daily_lock = Lock()

GROQ_DAILY_AUDIO_LIMIT = 28800  # 8 hours in seconds
GROQ_DAILY_REQUEST_LIMIT = 2000

def _reset_daily_counters_if_needed():
    """Reset daily counters if the date has changed."""
    global _daily_audio_seconds, _daily_request_count, _daily_reset_date
    today = datetime.now().date()
    if _daily_reset_date != today:
        _daily_audio_seconds = 0.0
        _daily_request_count = 0
        _daily_reset_date = today
        logging.info("Daily Groq usage counters reset.")

def _track_usage(audio_seconds: float):
    """Track daily Groq API usage."""
    global _daily_audio_seconds, _daily_request_count
    with _daily_lock:
        _reset_daily_counters_if_needed()
        _daily_audio_seconds += audio_seconds
        _daily_request_count += 1
        remaining_seconds = GROQ_DAILY_AUDIO_LIMIT - _daily_audio_seconds
        remaining_requests = GROQ_DAILY_REQUEST_LIMIT - _daily_request_count
        if remaining_seconds < 3600:
            logging.warning(f"Groq daily limit approaching: {remaining_seconds:.0f}s audio remaining ({_daily_request_count} requests used)")
        elif _daily_request_count % 50 == 0:
            logging.info(f"Groq daily usage: {_daily_audio_seconds:.0f}s audio, {_daily_request_count} requests")

def init_groq_client():
    """Initialize the Groq client."""
    global groq_client
    if not groq_api_key:
        logging.error("GROQ_API_KEY is not set! Cannot transcribe audio. Please set it and restart.")
        sys.exit(1)
    groq_client = Groq(api_key=groq_api_key)
    logging.info(f"Groq client initialized with model: {groq_model}")

def transcribe_with_groq(audio_file_path: str, language: str = None) -> str:
    """
    Transcribe an audio file using Groq API, handling chunking for large files.
    
    Args:
        audio_file_path: Path to the audio file
        language: Optional ISO 639-1 language code
        
    Returns:
        SRT content as a string
    """
    global groq_client
    if groq_client is None:
        init_groq_client()
    
    try:
        file_size_mb = os.path.getsize(audio_file_path) / (1024 * 1024)
    except OSError as e:
        logging.error(f"Cannot access audio file {audio_file_path}: {e}")
        raise
    
    if file_size_mb <= groq_max_chunk_size_mb:
        # Single file, send directly
        return _transcribe_single_chunk(audio_file_path, language, chunk_offset=0.0)
    else:
        # Split into chunks and transcribe each
        logging.info(f"File is {file_size_mb:.1f}MB, splitting into chunks (max {groq_max_chunk_size_mb}MB)")
        return _transcribe_chunked(audio_file_path, language)

def _transcribe_single_chunk(audio_file_path: str, language: str = None, chunk_offset: float = 0.0) -> str:
    """Transcribe a single audio chunk via Groq API with retry logic."""
    for attempt in range(groq_retry_attempts):
        try:
            start_time = time.time()
            
            with open(audio_file_path, "rb") as f:
                kwargs = {
                    "file": (os.path.basename(audio_file_path), f),
                    "model": groq_model,
                    "response_format": "verbose_json",
                }
                if language:
                    kwargs["language"] = language
                
                result = groq_client.audio.transcriptions.create(**kwargs)
            
            elapsed = time.time() - start_time
            
            # Track usage
            duration = getattr(result, 'duration', 0) or 0
            _track_usage(duration)
            
            logging.info(f"Groq API response: {duration:.1f}s audio in {elapsed:.1f}s (offset={chunk_offset:.1f}s)")
            
            # Convert verbose_json to SRT with offset
            return _verbose_json_to_srt(result, chunk_offset)
            
        except Exception as e:
            error_str = str(e)
            if '429' in error_str or 'rate_limit' in error_str.lower():
                delay = groq_retry_delay * (2 ** attempt)
                logging.warning(f"Groq rate limit hit, retrying in {delay}s (attempt {attempt + 1}/{groq_retry_attempts})")
                time.sleep(delay)
            elif attempt < groq_retry_attempts - 1:
                delay = groq_retry_delay * (2 ** attempt)
                logging.warning(f"Groq API error: {e}, retrying in {delay}s (attempt {attempt + 1}/{groq_retry_attempts})")
                time.sleep(delay)
            else:
                logging.error(f"Groq API failed after {groq_retry_attempts} attempts: {e}")
                raise

def transcribe_bytes_with_groq(audio_bytes: bytes, language: str = None, filename: str = "audio.wav") -> str:
    """
    Transcribe in-memory audio bytes using Groq API.
    Writes to a temp file, handles chunking if needed, returns SRT content.
    """
    with tempfile.NamedTemporaryFile(suffix=os.path.splitext(filename)[1] or '.wav', delete=False) as tmp:
        tmp.write(audio_bytes)
        tmp_path = tmp.name
    
    try:
        return transcribe_with_groq(tmp_path, language)
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)

def _transcribe_chunked(audio_file_path: str, language: str = None) -> str:
    """Split audio into chunks, transcribe each, and stitch SRT together."""
    chunk_dir = tempfile.mkdtemp(prefix="subgen_chunks_")
    
    try:
        chunk_files = _split_audio_into_chunks(audio_file_path, chunk_dir)
        
        if not chunk_files:
            raise ValueError("Failed to split audio file into chunks")
        
        logging.info(f"Split into {len(chunk_files)} chunks")
        
        # Transcribe each chunk and accumulate SRT entries
        all_srt_entries = []
        cumulative_offset = 0.0
        
        for i, chunk_path in enumerate(chunk_files):
            logging.info(f"Transcribing chunk {i + 1}/{len(chunk_files)}")
            
            # Get chunk duration using ffprobe
            chunk_duration = _get_audio_duration(chunk_path)
            
            srt_content = _transcribe_single_chunk(chunk_path, language, chunk_offset=cumulative_offset)
            
            if srt_content.strip():
                all_srt_entries.append(srt_content)
            
            cumulative_offset += chunk_duration
        
        # Merge all SRT entries and renumber
        return _merge_srt_entries(all_srt_entries)
        
    finally:
        shutil.rmtree(chunk_dir, ignore_errors=True)

def _split_audio_into_chunks(audio_file_path: str, chunk_dir: str) -> list:
    """
    Split audio into chunks using ffmpeg with codec fallback.
    
    Tries codecs in order of preference:
    1. FLAC: native ffmpeg encoder, good compression, no external library needed
    2. WAV/PCM: uncompressed but universally available, uses shorter segments to stay under API limit
    
    Returns a list of chunk file paths.
    """
    # Codec configurations in order of preference
    codec_options = [
        {"codec": "flac", "ext": "flac", "extra_args": [], "segment_time": 600},
        {"codec": "pcm_s16le", "ext": "wav", "extra_args": [], "segment_time": 450},
    ]
    
    last_error = None
    
    for config in codec_options:
        try:
            chunk_files = _run_ffmpeg_segment(audio_file_path, chunk_dir, config)
            
            if not chunk_files:
                logging.warning(f"ffmpeg with codec '{config['codec']}' produced no chunks")
                continue
            
            # Validate chunk sizes against Groq API limit
            oversized = [f for f in chunk_files if os.path.getsize(f) > GROQ_API_MAX_FILE_SIZE_BYTES]
            if oversized:
                logging.warning(
                    f"{len(oversized)} chunk(s) exceed Groq API 25MB limit "
                    f"(largest: {max(os.path.getsize(f) for f in oversized) / (1024*1024):.1f}MB), "
                    f"re-splitting with shorter segments"
                )
                _clear_chunk_dir(chunk_dir)
                
                # Retry with halved segment time
                retry_config = dict(config)
                retry_config["segment_time"] = config["segment_time"] // 2
                chunk_files = _run_ffmpeg_segment(audio_file_path, chunk_dir, retry_config)
                
                if not chunk_files:
                    continue
                
                # Check again after re-split
                still_oversized = [f for f in chunk_files if os.path.getsize(f) > GROQ_API_MAX_FILE_SIZE_BYTES]
                if still_oversized:
                    logging.warning(
                        f"Chunks still too large after halving segment time to {retry_config['segment_time']}s, "
                        f"trying next codec"
                    )
                    _clear_chunk_dir(chunk_dir)
                    continue
            
            return chunk_files
            
        except subprocess.CalledProcessError as e:
            stderr_msg = (e.stderr or "").strip()
            logging.warning(
                f"ffmpeg chunking with codec '{config['codec']}' failed "
                f"(exit code {e.returncode}): {stderr_msg or 'no error output'}"
            )
            last_error = e
            _clear_chunk_dir(chunk_dir)
            continue
    
    # All codecs failed
    if last_error:
        stderr_msg = (last_error.stderr or "").strip()
        raise RuntimeError(
            f"All audio codecs failed for chunking. "
            f"Last error (exit code {last_error.returncode}): {stderr_msg or 'no error output'}"
        )
    raise RuntimeError("Failed to split audio into chunks - no codec produced valid output")

def _run_ffmpeg_segment(audio_file_path: str, chunk_dir: str, config: dict) -> list:
    """Run ffmpeg segment command and return sorted list of chunk file paths."""
    ext = config["ext"]
    chunk_pattern = os.path.join(chunk_dir, f"chunk_%03d.{ext}")
    
    cmd = [
        "ffmpeg", "-i", audio_file_path,
        "-f", "segment", "-segment_time", str(config["segment_time"]),
        "-c:a", config["codec"],
        "-ac", "1", "-ar", "16000",
        *config.get("extra_args", []),
        chunk_pattern,
        "-y", "-loglevel", "warning"
    ]
    
    logging.debug(f"Running ffmpeg segment: {' '.join(cmd)}")
    subprocess.run(cmd, check=True, capture_output=True, text=True)
    
    chunk_files = sorted([
        os.path.join(chunk_dir, f) for f in os.listdir(chunk_dir)
        if f.startswith("chunk_") and f.endswith(f".{ext}")
    ])
    
    for chunk_path in chunk_files:
        size_mb = os.path.getsize(chunk_path) / (1024 * 1024)
        logging.debug(f"Chunk {os.path.basename(chunk_path)}: {size_mb:.1f}MB")
    
    return chunk_files

def _clear_chunk_dir(chunk_dir: str):
    """Remove all files in the chunk directory."""
    for f in os.listdir(chunk_dir):
        filepath = os.path.join(chunk_dir, f)
        if os.path.isfile(filepath):
            os.unlink(filepath)

def _get_audio_duration(file_path: str) -> float:
    """Get audio duration in seconds using ffprobe."""
    try:
        probe = ffmpeg.probe(file_path)
        return float(probe['format']['duration'])
    except Exception as e:
        logging.warning(f"Could not get duration for {file_path}: {e}, estimating 600s")
        return 600.0

def _verbose_json_to_srt(result, offset: float = 0.0) -> str:
    """Convert Groq verbose_json response to SRT format with time offset."""
    segments = getattr(result, 'segments', None)
    if not segments:
        return ""
    
    srt_lines = []
    for i, seg in enumerate(segments, 1):
        # Groq SDK returns segment objects with attributes (not dicts)
        start = getattr(seg, 'start', 0) + offset
        end = getattr(seg, 'end', 0) + offset
        text = getattr(seg, 'text', '').strip()
        
        if not text:
            continue
        
        start_ts = _seconds_to_srt_time(start)
        end_ts = _seconds_to_srt_time(end)
        
        srt_lines.append(f"{i}")
        srt_lines.append(f"{start_ts} --> {end_ts}")
        srt_lines.append(text)
        srt_lines.append("")
    
    return "\n".join(srt_lines)

def _seconds_to_srt_time(seconds: float) -> str:
    """Convert seconds to SRT timestamp format HH:MM:SS,mmm"""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int((seconds % 1) * 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"

def _merge_srt_entries(srt_entries: list) -> str:
    """Merge multiple SRT strings and renumber entries sequentially."""
    merged_lines = []
    counter = 1
    
    for srt_content in srt_entries:
        blocks = srt_content.strip().split("\n\n")
        for block in blocks:
            lines = block.strip().split("\n")
            if len(lines) >= 3:
                # Replace the sequence number
                merged_lines.append(str(counter))
                merged_lines.extend(lines[1:])  # timestamp + text
                merged_lines.append("")
                counter += 1
    
    return "\n".join(merged_lines)

# ============================================================================
# TASK RESULT STORAGE (for blocking endpoints)
# ============================================================================

class TaskResult:
    """Stores the result of a queued task for blocking retrieval"""
    def __init__(self):
        self.result = None
        self.error = None
        self.done = Event()
    
    def set_result(self, result):
        self.result = result
        self.done.set()
    
    def set_error(self, error):
        self.error = error
        self.done.set()
    
    def wait(self, timeout=None):
        """Block until result is ready. Returns True if completed, False if timeout."""
        return self.done.wait(timeout)

# Dictionary to store task results keyed by task_id
task_results = {}
task_results_lock = Lock()

# ============================================================================
# HASH GENERATION FOR DEDUPLICATION
# ============================================================================

def generate_audio_hash(audio_content: bytes, task: str = None, language: str = None) -> str:
    """
    Generate a deterministic hash from audio content and optional parameters. 
    """
    hash_input = audio_content
    if task:
        hash_input += task.encode('utf-8')
    if language:
        hash_input += language.encode('utf-8')
    
    full_hash = hashlib.sha256(hash_input).hexdigest()
    return full_hash[:16]

# ============================================================================
# DEDUPLICATED QUEUE
# ============================================================================

class DeduplicatedQueue(queue.PriorityQueue):
    """Queue that prevents duplicates, handles priority, and tracks status."""
    def __init__(self):
        super().__init__()
        self._queued = set()
        self._processing = set()
        self._lock = Lock()

    def put(self, item, block=True, timeout=None):
        with self._lock:
            task_id = item["path"]
            if task_id not in self._queued and task_id not in self._processing:
                task_type = item.get("type", "transcribe")
                priority = 0 if task_type == "detect_language" else (1 if task_type == "asr" else 2)
                super().put((priority, time.time(), item), block, timeout)
                self._queued.add(task_id)
                return True
            return False

    def get(self, block=True, timeout=None):
        priority, timestamp, item = super().get(block, timeout)
        with self._lock:
            task_id = item["path"]
            self._queued.discard(task_id)
            self._processing.add(task_id)
        return item

    def mark_done(self, item):
        with self._lock:
            task_id = item["path"]
            self._processing.discard(task_id)

    def is_idle(self):
        with self._lock:
            return self.empty() and len(self._processing) == 0

    def is_active(self, task_id):
        with self._lock:
            return task_id in self._queued or task_id in self._processing

    def get_queued_tasks(self):
        with self._lock:
            return list(self._queued)

    def get_processing_tasks(self):
        with self._lock:
            return list(self._processing)

# Start queue
task_queue = DeduplicatedQueue()

# ============================================================================
# TRANSCRIPTION WORKER
# ============================================================================

def transcription_worker():
    """Main worker thread with centralized logging and status tracking."""
    while True:
        task = None
        next_task = None
        try:
            task = task_queue.get(block=True, timeout=1)
            task_type = task.get("type", "transcribe")
            path = task.get("path", "unknown")
            display_name = os.path.basename(path) if ("/" in str(path) or "\\" in str(path)) else path
            
            proc_count = len(task_queue.get_processing_tasks())
            queue_count = len(task_queue.get_queued_tasks())
            logging.info(f"WORKER START :[{task_type.upper():<10}] {display_name:^40} | Jobs: {proc_count} processing, {queue_count} queued")
            
            start_time = time.time()
            if task_type == "detect_language": 
                next_task = detect_language_task(task['path'], original_task_data=task)
            elif task_type == "asr":
                asr_task_worker(task)
            else:
                gen_subtitles(task['path'], task['transcribe_or_translate'], task['force_language'])
                
                if 'plex_item_id' in task:
                    try:
                        logging.info(f"Refreshing Plex Metadata for item {task['plex_item_id']}")
                        refresh_plex_metadata(task['plex_item_id'], task['plex_server'], task['plex_token'])
                    except Exception as e:
                        logging.error(f"Failed to refresh Plex metadata: {e}")
                
                if 'jellyfin_item_id' in task:
                    try:
                        logging.info(f"Refreshing Jellyfin Metadata for item {task['jellyfin_item_id']}")
                        refresh_jellyfin_metadata(task['jellyfin_item_id'], task['jellyfin_server'], task['jellyfin_token'])
                    except Exception as e:
                        logging.error(f"Failed to refresh Jellyfin metadata: {e}")
            
            elapsed = time.time() - start_time
            m, s = divmod(int(elapsed), 60)
            remaining_queued = len(task_queue.get_queued_tasks())
            logging.info(f"WORKER FINISH: [{task_type.upper():<10}] {display_name:^40} in {m}m {s}s | Remaining: {remaining_queued} queued")

        except queue.Empty:
            continue
        except Exception as e:
            logging.error(f"Error processing task: {e}", exc_info=True)
        finally:
            if task:
                task_queue.task_done()
                task_queue.mark_done(task)
                
                if next_task:
                    if task_queue.put(next_task):
                        logging.debug(f"Queued transcription for detected language: {next_task['path']}")
                    else:
                        logging.debug(f"Transcription already queued/processing for: {next_task['path']}")
         
# Create worker threads
for _ in range(concurrent_transcriptions):
    threading.Thread(target=transcription_worker, daemon=True).start()

# Define a filter class to hide common logging we don't want to see
class MultiplePatternsFilter(logging.Filter):
    def filter(self, record):
        patterns =[
            "Compression ratio threshold is not met",
            "Processing segment at",
            "Log probability threshold is",
            "Reset prompt",
            "header parsing failed",
            "timescale not set",
            "misdetection possible",
            "srt was added",
            "doesn't have any audio to transcribe",
            "Calling on_"
        ]
        return not any(pattern in record.getMessage() for pattern in patterns)

# Configure logging
if debug:
    level = logging.DEBUG
else:
    level = logging.INFO

logging.basicConfig(
    stream=sys.stderr, 
    level=level, 
    format="%(asctime)s %(levelname)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)

logger = logging.getLogger()
logger.setLevel(level)

for handler in logger.handlers:
    handler.addFilter(MultiplePatternsFilter())

logging.getLogger("multipart").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)
logging.getLogger("watchfiles").setLevel(logging.WARNING)
logging.getLogger("asyncio").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)

TIME_OFFSET = 5

def appendLine(srt_content: str) -> str:
    """Append a 'Transcribed by' line to SRT content if APPEND is enabled."""
    if not append:
        return srt_content
    
    # Parse the last timestamp to add offset
    blocks = srt_content.strip().split("\n\n")
    if not blocks:
        return srt_content
    
    last_block = blocks[-1]
    lines = last_block.strip().split("\n")
    if len(lines) >= 2:
        # Parse end time from last entry
        match = re.search(r'(\d{2}:\d{2}:\d{2},\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2},\d{3})', lines[1])
        if match:
            end_time_str = match.group(2)
            # Parse end time and add offset
            parts = end_time_str.replace(',', ':').split(':')
            end_seconds = int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2]) + int(parts[3]) / 1000
            
            new_start = end_seconds + TIME_OFFSET
            new_end = new_start + TIME_OFFSET
            
            date_time_str = datetime.now().strftime("%d %b %Y - %H:%M:%S")
            appended_text = f"Transcribed by Subgen (Groq {groq_model}) on {date_time_str}"
            
            # Count entries to get next number
            next_num = len(blocks) + 1
            
            new_block = f"{next_num}\n{_seconds_to_srt_time(new_start)} --> {_seconds_to_srt_time(new_end)}\n{appended_text}"
            srt_content = srt_content.rstrip() + "\n\n" + new_block + "\n"
    
    return srt_content

@app.get("/plex")
@app.get("/webhook")
@app.get("/jellyfin")
@app.get("/asr")
@app.get("/emby")
@app.get("/detect-language")
@app.get("/tautulli")
def handle_get_request(request: Request):
    return {"You accessed this request incorrectly via a GET request. See https://github.com/McCloudS/subgen for proper configuration"}

@app.get("/")
def webui():
    return {"The webui for configuration was removed on 1 October 2024, please configure via environment variables or in your Docker settings. "}

@app.get("/status")
def status():
    with _daily_lock:
        _reset_daily_counters_if_needed()
        usage_info = f"{_daily_audio_seconds:.0f}s/{GROQ_DAILY_AUDIO_LIMIT}s audio, {_daily_request_count}/{GROQ_DAILY_REQUEST_LIMIT} requests today"
    return {
        "version": f"Subgen {subgen_version} (Groq: {groq_model}) ({docker_status})",
        "groq_usage": usage_info,
    }

@app.post("/tautulli")
def receive_tautulli_webhook(
        source: Union[str, None] = Header(None),
        event: str = Body(None),
        file: str = Body(None),
):
    if source == "Tautulli":
        logging.debug(f"Tautulli event detected is: {event}")
        if((event == "added" and procaddedmedia) or (event == "played" and procmediaonplay)):
            fullpath = file
            logging.debug(f"Full file path: {fullpath}")

            gen_subtitles_queue(path_mapping(fullpath), transcribe_or_translate)
    else:
        return {
            "message": "This doesn't appear to be a properly configured Tautulli webhook, please review the instructions again!"}

    return ""

@app.post("/plex")
@app.post("/plex")
def receive_plex_webhook(
        user_agent: Union[str] = Header(None),
        payload: Union[str] = Form(),
):
    try:
        plex_json = json.loads(payload)

        if "PlexMediaServer" not in user_agent:
            return {"message": "This doesn't appear to be a properly configured Plex webhook, please review the instructions again"}

        event = plex_json["event"]
        logging.debug(f"Plex event detected is: {event}")

        if (event == "library.new" and procaddedmedia) or (event == "media.play" and procmediaonplay):
            rating_key = plex_json['Metadata']['ratingKey']
            fullpath = get_plex_file_name(rating_key, plexserver, plextoken)
            logging.debug(f"Full file path: {fullpath}")

            gen_subtitles_queue(
                path_mapping(fullpath), 
                transcribe_or_translate, 
                plex_item_id=rating_key, 
                plex_server=plexserver, 
                plex_token=plextoken
            )

            if plex_queue_next_episode:
                next_key = get_next_plex_episode(plex_json['Metadata']['ratingKey'], stay_in_season=False)
                if next_key:
                    next_file = get_plex_file_name(next_key, plexserver, plextoken)
                    gen_subtitles_queue(
                        path_mapping(next_file), 
                        transcribe_or_translate,
                        plex_item_id=next_key,
                        plex_server=plexserver,
                        plex_token=plextoken
                    )

            if plex_queue_series or plex_queue_season:
                current_rating_key = plex_json['Metadata']['ratingKey']
                stay_in_season = plex_queue_season

                while current_rating_key is not None:
                    try:
                        file_path = path_mapping(get_plex_file_name(current_rating_key, plexserver, plextoken))
                        
                        gen_subtitles_queue(
                            file_path, 
                            transcribe_or_translate,
                            plex_item_id=current_rating_key,
                            plex_server=plexserver,
                            plex_token=plextoken
                        )
                        
                        logging.debug(f"Queued episode with ratingKey {current_rating_key}")

                        next_episode_rating_key = get_next_plex_episode(current_rating_key, stay_in_season=stay_in_season)
                        if next_episode_rating_key is None:
                            break
                        current_rating_key = next_episode_rating_key

                    except Exception as e:
                        logging.error(f"Error processing episode with ratingKey {current_rating_key} or reached end of series: {e}")
                        break

                logging.info("All episodes in the series (or season) have been queued.")

    except Exception as e:
        logging.error(f"Failed to process Plex webhook: {e}")

    return ""
 
@app.post("/jellyfin")
def receive_jellyfin_webhook(
        user_agent: str = Header(None),
        NotificationType: str = Body(None),
        file: str = Body(None),
        ItemId: str = Body(None),
):
    if "Jellyfin-Server" in user_agent:
        logging.debug(f"Jellyfin event detected is: {NotificationType}")
        logging.debug(f"itemid is: {ItemId}")

        if (NotificationType == "ItemAdded" and procaddedmedia) or (NotificationType == "PlaybackStart" and procmediaonplay):
            fullpath = get_jellyfin_file_name(ItemId, jellyfinserver, jellyfintoken)
            logging.debug(f"Full file path: {fullpath}")

            gen_subtitles_queue(
                path_mapping(fullpath), 
                transcribe_or_translate,
                jellyfin_item_id=ItemId,
                jellyfin_server=jellyfinserver,
                jellyfin_token=jellyfintoken
            )
    else:
        return {
            "message": "This doesn't appear to be a properly configured Jellyfin webhook, please review the instructions again!"}

    return ""

@app.post("/emby")
def receive_emby_webhook(
        user_agent: Union[str, None] = Header(None),
        data: Union[str, None] = Form(None),
):
    if not data:
        return ""

    data_dict = json.loads(data)
    event = data_dict['Event']
    logging.debug("Emby event detected is: " + event)

    if event == "system.notificationtest":
        logging.info("Emby test message received!")
        return {"message": "Notification test received successfully!"}

    if (event == "library.new" and procaddedmedia) or (event == "playback.start" and procmediaonplay):
        fullpath = data_dict['Item']['Path']
        logging.debug(f"Full file path: {fullpath}")
        gen_subtitles_queue(path_mapping(fullpath), transcribe_or_translate)

    return ""
    
@app.post("/batch")
def batch(
        directory: str = Query(...),
        forceLanguage: Union[str, None] = Query(default=None)
):
    transcribe_existing(directory, LanguageCode.from_string(forceLanguage))

# ============================================================================
# /ASR ENDPOINT - Bazarr Whisper Provider Interface
# ============================================================================

@app.post("/asr")
async def asr(
    task: Union[str, None] = Query(default="transcribe", enum=["transcribe", "translate"]),
    language: Union[str, None] = Query(default=None),
    video_file: Union[str, None] = Query(default=None),
    initial_prompt: Union[str, None] = Query(default=None),
    audio_file: UploadFile = File(...),
    encode: bool = Query(default=True, description="Encode audio first through ffmpeg"),
    output: Union[str, None] = Query(default="srt", enum=["txt", "vtt", "srt", "tsv", "json"]),
    word_timestamps: bool = Query(default=False, description="Word-level timestamps"),
):
    """
    ASR endpoint that uses audio content hash for deduplication. 
    BLOCKS until processing is complete, then returns the result.
    """
    task_id = None
    
    try:
        logging.info(
            f"ASR {task.capitalize()} received for file '{video_file}'" 
            if video_file 
            else f"ASR {task.capitalize()} received"
        )
        
        file_content = await audio_file.read()
        
        if not file_content:
            await audio_file.close()
            return {
                "status": "error",
                "message": "Audio file is empty"
            }
        
        audio_hash = generate_audio_hash(file_content, task, language)
        task_id = f"asr-{audio_hash}"
        
        logging.debug(f"Generated audio hash: {audio_hash} for ASR request")
        
        final_language = language
        if force_detected_language_to: 
            final_language = force_detected_language_to.to_iso_639_1()
            logging.info(f"Forcing detected language to {force_detected_language_to}")
        
        with task_results_lock:
            if task_id not in task_results:
                task_results[task_id] = TaskResult()
            task_result = task_results[task_id]
        
        asr_task_data = {
            'path': task_id,
            'type': 'asr',
            'task': task,
            'language': final_language,
            'video_file': video_file,
            'initial_prompt': initial_prompt,
            'audio_content': file_content,
            'encode': encode,
            'output': output,
            'word_timestamps': word_timestamps,
            'result_container': task_result,
        }
        
        if task_queue.put(asr_task_data):
            logging.info(f"ASR task {task_id} queued")
        else:
            logging.info(f"ASR task {task_id} already queued/processing - waiting for result")
        
        if await asyncio.to_thread(task_result.wait, asr_timeout):
            if task_result.error:
                logging.error(f"ASR task {task_id} failed: {task_result.error}")
                return {
                    "status": "error",
                    "task_id": task_id,
                    "message": f"ASR processing failed: {task_result.error}"
                }
            else: 
                logging.info(f"ASR task {task_id} completed")
                return StreamingResponse(
                    iter(task_result.result),
                    media_type="text/plain",
                    headers={'Source': 'Transcribed using Groq Whisper API from Subgen!'}
                )
        else:
            logging.error(f"ASR task {task_id} timed out")
            return {
                "status": "timeout",
                "task_id": task_id,
                "message": f"ASR processing timed out after {asr_timeout} seconds"
            }
            
    except Exception as e: 
        logging.error(f"Error in ASR endpoint: {e}", exc_info=True)
        return {"status": "error", "message": f"Error: {str(e)}"}
    finally:
        await audio_file.close()
        with task_results_lock:
            if task_id in task_results:
                del task_results[task_id]
                logging.debug(f"Cleaned up task_results entry for {task_id}")

# ============================================================================
# ASR WORKER FUNCTION
# ============================================================================

def asr_task_worker(task_data: dict) -> None:
    """
    Worker function that processes ASR tasks from the queue. 
    Called by transcription_worker when task type is 'asr'.
    """
    task_id = task_data.get('path', 'unknown')
    result_container = task_data.get('result_container')
    
    try:
        language = task_data.get('language')
        file_content = task_data['audio_content']
        
        # Write audio content to temp file for Groq API
        srt_content = transcribe_bytes_with_groq(file_content, language=language)
        srt_content = appendLine(srt_content)
        
        if result_container:
            result_container.set_result([srt_content])

    except Exception as e:
        logging.error(f"Error processing ASR (ID: {task_id}): {e}", exc_info=True)
        if result_container: 
            result_container.set_error(str(e))

# ============================================================================
# /DETECT-LANGUAGE ENDPOINT
# ============================================================================

@app.post("/detect-language")
async def detect_language(
    audio_file: UploadFile = File(...),
    encode: bool = Query(default=True),
    video_file: Union[str, None] = Query(default=None),
    detect_lang_length: int = Query(default=30),
    detect_lang_offset: int = Query(default=0)
):
    if force_detected_language_to: 
        await audio_file.close()
        return {"detected_language": force_detected_language_to.to_name(), "language_code": force_detected_language_to.to_iso_639_1()}
    
    try:
        file_content = await audio_file.read()
        if not file_content:
            return {"detected_language": "Unknown", "language_code": "und", "status": "error"}
            
        logging.info(f"Language detection via Groq" + (f" for {video_file}" if video_file else ""))
        
        # Extract a short segment for language detection
        audio_segment = await asyncio.to_thread(
            _extract_audio_segment_bytes, file_content, detect_lang_offset, detect_lang_length
        )
        
        # Send to Groq for transcription - it will auto-detect the language
        srt_result = await asyncio.to_thread(
            transcribe_bytes_with_groq, audio_segment, None, "detect.wav"
        )
        
        # Groq returns language in verbose_json - we need to detect it from a small sample
        # Use Groq with verbose_json to detect
        detected = await asyncio.to_thread(_detect_language_via_groq, audio_segment)
        
        logging.info(f"Detect Language Result: {detected.to_name()} ({detected.to_iso_639_1()})")
        
        return {
            "detected_language": detected.to_name(),
            "language_code": detected.to_iso_639_1()
        }

    except Exception as e: 
        logging.error(f"Error in API detect-language: {e}", exc_info=True)
        return {"detected_language": "Unknown", "language_code": "und", "status": "error"}
    finally: 
        await audio_file.close()

def _detect_language_via_groq(audio_bytes: bytes) -> LanguageCode:
    """Detect language by sending a short audio sample to Groq."""
    global groq_client
    if groq_client is None:
        init_groq_client()
    
    with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as tmp:
        tmp.write(audio_bytes)
        tmp_path = tmp.name
    
    try:
        with open(tmp_path, "rb") as f:
            result = groq_client.audio.transcriptions.create(
                file=("detect.wav", f),
                model=groq_model,
                response_format="verbose_json",
            )
        
        detected_lang = getattr(result, 'language', None)
        if detected_lang:
            return LanguageCode.from_string(detected_lang)
        return LanguageCode.NONE
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)

def _extract_audio_segment_bytes(audio_content: bytes, start_time: int, duration: int) -> bytes:
    """Extract a segment of audio from in-memory content using FFmpeg."""
    try:
        logging.info(f"Extracting audio segment: start_time={start_time}s, duration={duration}s")
        
        out, _ = (
            ffmpeg
            .input('pipe:0', ss=start_time, t=duration)
            .output('pipe:1', format='wav', acodec='pcm_s16le', ar=16000)
            .run(input=audio_content, capture_stdout=True, capture_stderr=True)
        )
        
        if not out:
            raise ValueError("FFmpeg output is empty")
        
        return out

    except ffmpeg.Error as e:
        logging.error(f"FFmpeg error: {e.stderr.decode()}")
        return audio_content
    except Exception as e:
        logging.error(f"Error extracting audio segment: {str(e)}")
        return audio_content

def detect_language_task(path, original_task_data=None):
    """
    Worker function that detects language for a local file.
    Returns the task data to be queued for transcription.
    """
    detected_language = LanguageCode.NONE
    
    try:
        logging.info(f"Detecting language of file: {path}")
        
        # Extract a short audio segment for language detection
        audio_segment = _extract_audio_segment_from_file(path, 0, 30)
        
        if audio_segment:
            detected_language = _detect_language_via_groq(audio_segment)
            logging.info(f"Detected language: {detected_language.to_name()}")

    except Exception as e:
        logging.error(f"Error detecting language for file: {e}", exc_info=True)
        
    task_data = {
        'path': path,
        'type': 'transcribe',
        'transcribe_or_translate': transcribe_or_translate,
        'force_language': detected_language
    }
    
    if original_task_data:
        for key, value in original_task_data.items():
            if key not in task_data:
                task_data[key] = value
                
    return task_data

def _extract_audio_segment_from_file(input_file: str, start_time: int, duration: int) -> bytes:
    """Extract a segment of audio from a file using FFmpeg."""
    try:
        out, _ = (
            ffmpeg
            .input(input_file, ss=start_time, t=duration)
            .output('pipe:1', format='wav', acodec='pcm_s16le', ar=16000)
            .run(capture_stdout=True, capture_stderr=True)
        )
        if not out:
            raise ValueError("FFmpeg output is empty")
        return out
    except ffmpeg.Error as e:
        logging.error(f"FFmpeg error: {e.stderr.decode()}")
        return None
    except Exception as e:
        logging.error(f"Error: {str(e)}")
        return None

def isAudioFileExtension(file_extension):
    return file_extension.casefold() in AUDIO_EXTENSIONS

def write_lrc(srt_content: str, file_path: str):
    """Convert SRT content to LRC format and write to file."""
    with open(file_path, "w") as file:
        blocks = srt_content.strip().split("\n\n")
        for block in blocks:
            lines = block.strip().split("\n")
            if len(lines) >= 3:
                match = re.search(r'(\d{2}):(\d{2}):(\d{2}),(\d{3})', lines[1])
                if match:
                    h, m, s, ms = int(match.group(1)), int(match.group(2)), int(match.group(3)), int(match.group(4))
                    total_minutes = h * 60 + m
                    fraction = ms // 10
                    text = " ".join(lines[2:]).replace('\n', '')
                    file.write(f"[{total_minutes:02d}:{s:02d}.{fraction:02d}]{text}\n")

def send_completion_webhook(source_file_path: str, subtitle_file_path: str, language: LanguageCode, task_type: str):
    """Sends a JSON POST request to a configured webhook URL upon task completion."""
    if not webhook_url_completed:
        return
        
    event_status = f"{task_type}d" if task_type in["transcribe", "translate"] else task_type
        
    payload = {
        "event": event_status,
        "file": os.path.abspath(source_file_path),
        "subtitle": os.path.abspath(subtitle_file_path),
        "language": language.to_iso_639_1()
    }
    
    try:
        logging.info(f"Sending completion webhook ({event_status}) to {webhook_url_completed}")
        response = requests.post(webhook_url_completed, json=payload, timeout=10)
        response.raise_for_status()
        logging.debug(f"Webhook successfully delivered. Status code: {response.status_code}")
    except Exception as e:
        logging.error(f"Failed to send completion webhook: {e}")

def gen_subtitles(file_path: str, transcription_type: str, force_language: LanguageCode = LanguageCode.NONE) -> None:
    """Generates subtitles for a video file using Groq API."""
    try:
        file_name, file_extension = os.path.splitext(file_path)
        is_audio_file = isAudioFileExtension(file_extension)
        
        # Extract audio to a temp file for Groq API
        audio_file_path = _prepare_audio_for_groq(file_path, force_language)
        
        language_code = force_language.to_iso_639_1() if force_language else None
        
        srt_content = transcribe_with_groq(audio_file_path, language=language_code)
        srt_content = appendLine(srt_content)
        
        # Determine output language from force_language or detect from content
        output_language = force_language if force_language else LanguageCode.NONE
        
        # Clean up temp audio file if we created one
        if audio_file_path != file_path and os.path.exists(audio_file_path):
            os.unlink(audio_file_path)
        
        subtitle_file_path = ""

        if is_audio_file and lrc_for_audio_files:
            subtitle_file_path = file_name + '.lrc'
            write_lrc(srt_content, subtitle_file_path)
        else:
            subtitle_file_path = name_subtitle(file_path, output_language)
            with open(subtitle_file_path, 'w', encoding='utf-8') as f:
                f.write(srt_content)
            
        send_completion_webhook(file_path, subtitle_file_path, output_language, transcription_type)

    except Exception as e:
        logging.info(f"Error processing or transcribing {file_path} in {force_language}: {e}")

def _prepare_audio_for_groq(file_path: str, language: LanguageCode = None) -> str:
    """
    Prepare an audio file for Groq API. 
    Extracts audio track from video files, handles multiple audio tracks.
    Returns path to the audio file ready for Groq.
    """
    file_name, file_extension = os.path.splitext(file_path)
    
    # If it's already an audio file, just return it
    if isAudioFileExtension(file_extension):
        return file_path
    
    # Extract audio from video to a temp mp3 file  
    try:
        audio_tracks = get_audio_tracks(file_path)
        track_index = None
        
        if len(audio_tracks) > 1:
            logging.debug(f"Multiple audio tracks in {file_path}, selecting best match")
            if language:
                track = get_audio_track_by_language(audio_tracks, language)
                if track:
                    track_index = track['index']
            if track_index is None and audio_tracks:
                track_index = audio_tracks[0]['index']
        elif audio_tracks:
            track_index = audio_tracks[0]['index']
        
        # Extract to temp mp3
        tmp_fd, tmp_path = tempfile.mkstemp(suffix='.mp3', prefix='subgen_audio_')
        os.close(tmp_fd)
        
        try:
            input_stream = ffmpeg.input(file_path)
            if track_index is not None:
                output_stream = input_stream.output(
                    tmp_path,
                    map=f"0:{track_index}",
                    acodec='libmp3lame',
                    ab='64k',
                    ac=1,
                    ar=16000,
                    loglevel='warning'
                )
            else:
                output_stream = input_stream.output(
                    tmp_path,
                    acodec='libmp3lame',
                    ab='64k',
                    ac=1,
                    ar=16000,
                    loglevel='warning'
                )
            
            output_stream.overwrite_output().run(capture_stdout=True, capture_stderr=True)
            return tmp_path
        except Exception:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
            raise
        
    except Exception as e:
        logging.error(f"Error extracting audio from {file_path}: {e}")
        return file_path

def define_subtitle_language_naming(language: LanguageCode, type):
    """
    Determines the naming format for a subtitle language based on the given type. 
    """
    if namesublang: 
        return namesublang
    switch_dict = {
        "ISO_639_1": language.to_iso_639_1,
        "ISO_639_2_T": language.to_iso_639_2_t,
        "ISO_639_2_B": language.to_iso_639_2_b,
        "NAME": language.to_name,
        "NATIVE": lambda: language.to_name(in_english=False)
    }
    if transcribe_or_translate == 'translate':
        language = LanguageCode.ENGLISH
    return switch_dict.get(type, language.to_name)()

def name_subtitle(file_path: str, language: LanguageCode) -> str:
    """
    Name the subtitle file to be written, based on the source file and the language of the subtitle.
    Supports SUBTITLE_TAG for custom tagging (e.g., "groq" -> "Movie.en.groq.srt").
    """
    subgen_part = ".subgen" if show_in_subname_subgen else ""
    lang_part = define_subtitle_language_naming(language, subtitle_language_naming_type)
    tag_part = f".{subtitle_tag}" if subtitle_tag else ""
    
    return f"{os.path.splitext(file_path)[0]}{subgen_part}.{lang_part}{tag_part}.srt"

def get_audio_track_by_language(audio_tracks, language):
    """Returns the first audio track with the given language."""
    for track in audio_tracks: 
        if track['language'] == language:
            return track
    return None

def choose_transcribe_language(file_path, forced_language):
    """Determines the language to be used for transcription."""
    if forced_language: 
        logger.debug(f"ENV FORCE_LANGUAGE is set: Forcing language to {forced_language}") 
        return forced_language

    if force_detected_language_to: 
        logger.debug(f"ENV FORCE_DETECTED_LANGUAGE_TO is set: Forcing detected language to {force_detected_language_to}")
        return force_detected_language_to

    audio_tracks = get_audio_tracks(file_path)
    
    preferred_track_language = find_language_audio_track(audio_tracks, preferred_audio_languages)

    if preferred_track_language: 
        return preferred_track_language
    
    default_language = find_default_audio_track_language(audio_tracks)
    if default_language: 
        logger.debug(f"Default language found: {default_language}")
        return default_language

    return LanguageCode.NONE
    
def get_audio_tracks(video_file):
    """Extracts information about the audio tracks in a file."""
    try:
        probe = ffmpeg.probe(video_file, select_streams='a')
        audio_streams = probe.get('streams',[])
        
        audio_tracks =[]
        for stream in audio_streams:
            audio_track = {
                "index": int(stream.get("index", None)),
                "codec": stream.get("codec_name", "Unknown"),
                "channels": int(stream.get("channels", None)),
                "language": LanguageCode.from_iso_639_2(stream.get("tags", {}).get("language", "Unknown")),
                "title": stream.get("tags", {}).get("title", "None"),
                "default": stream.get("disposition", {}).get("default", 0) == 1,
                "forced": stream.get("disposition", {}).get("forced", 0) == 1,
                "original": stream.get("disposition", {}).get("original", 0) == 1,
                "commentary": "commentary" in stream.get("tags", {}).get("title", "").lower()
            }
            audio_tracks.append(audio_track) 
        return audio_tracks

    except ffmpeg.Error as e:
        logging.error(f"FFmpeg error: {e.stderr}")
        return[]
    except Exception as e:
        logging.error(f"An error occurred while reading audio track information: {str(e)}")
        return[]

def find_language_audio_track(audio_tracks, find_languages):
    """Returns the first language from `find_languages` that matches an audio track."""
    for language in find_languages:
        for track in audio_tracks:
            if track['language'] == language:
                return language
    return None

def find_default_audio_track_language(audio_tracks): 
    """Finds the language of the default audio track."""
    for track in audio_tracks:
        if track['default'] is True:
            return track['language']
    return None
    
def gen_subtitles_queue(file_path: str, transcription_type: str, force_language: LanguageCode = LanguageCode.NONE, **kwargs) -> None:
    global task_queue
    
    if task_queue.is_active(file_path):
        logging.debug(f"Ignored: {os.path.basename(file_path)} is already queued or processing.")
        return
    
    if not has_audio(file_path):
        logging.debug(f"{file_path} doesn't have any audio to transcribe!")
        return
    
    force_language = choose_transcribe_language(file_path, force_language)

    if should_skip_file(file_path, force_language):
        return

    task = {
        'path': file_path,
        'transcribe_or_translate': transcription_type,
        'force_language': force_language
    }
    task.update(kwargs)
    
    task_queue.put(task)

def should_skip_file(file_path: str, target_language: LanguageCode) -> bool:
    """Determines if subtitle generation should be skipped for a file."""
    base_name = os.path.basename(file_path)
    file_name, file_ext = os.path.splitext(base_name)
    if transcribe_or_translate == 'translate': 
        target_language = LanguageCode.ENGLISH
    
    if isAudioFileExtension(file_ext) and lrc_for_audio_files:
        lrc_path = os.path.join(os.path.dirname(file_path), f"{file_name}.lrc")
        if os.path.exists(lrc_path):
            logging.info(f"Skipping {base_name}: LRC file already exists.")
            return True

    if skip_unknown_language and target_language == LanguageCode.NONE:
        logging.info(f"Skipping {base_name}: Unknown language and skip_unknown_language is enabled.")
        return True

    if skip_if_to_transcribe_sub_already_exist:
        if has_subtitle_language(file_path, target_language):
            lang_name = target_language.to_name()
            logging.info(f"Skipping {base_name}: Subtitles already exist in {lang_name}.")
            return True
            
        if namesublang and LanguageCode.is_valid_language(namesublang):
            external_lang = LanguageCode.from_string(namesublang)
            if has_subtitle_of_language_in_folder(file_path, external_lang, recursion=True, only_skip_if_subgen_subtitle=only_skip_if_subgen_subtitle):
                logging.info(f"Skipping {base_name}: Subtitles already exist in custom name '{namesublang}'.")
                return True
                
        expected_output = name_subtitle(file_path, target_language)
        if os.path.exists(expected_output):
            logging.info(f"Skipping {base_name}: Generated subtitle '{os.path.basename(expected_output)}' already exists.")
            return True

    if skipifinternalsublang and has_subtitle_language_in_file(file_path, skipifinternalsublang):
        lang_name = skipifinternalsublang.to_name()
        logging.info(f"Skipping {base_name}: Internal subtitles in {lang_name} already exist.")
        return True

    if skipifexternalsub and namesublang and LanguageCode.is_valid_language(namesublang):
        external_lang = LanguageCode.from_string(namesublang)
        if has_subtitle_of_language_in_folder(file_path, external_lang, recursion=True, only_skip_if_subgen_subtitle=only_skip_if_subgen_subtitle):
            lang_name = external_lang.to_name()
            logging.info(f"Skipping {base_name}: External subtitles in {lang_name} already exist.")
            return True

    if any(lang in skip_lang_codes_list for lang in get_subtitle_languages(file_path)):
        logging.info(f"Skipping {base_name}: Contains a skipped subtitle language.")
        return True

    audio_langs = get_audio_languages(file_path)

    if limit_to_preferred_audio_languages:
        if not any(lang in preferred_audio_languages for lang in audio_langs):
            preferred_names =[lang.to_name() for lang in preferred_audio_languages]
            logging.info(f"Skipping {base_name}: No preferred audio tracks found (looking for {', '.join(preferred_names)})")
            return True

    if any(lang in skip_if_audio_track_is_in_list for lang in audio_langs):
        logging.info(f"Skipping {base_name}: Contains a skipped audio language.")
        return True

    return False
    
def get_subtitle_languages(video_path):
    """Extract language codes from each subtitle stream in the video file."""
    languages = []

    try:
        probe = ffmpeg.probe(video_path, select_streams='s')
        for stream in probe.get('streams', []):
            lang_code = stream.get('tags', {}).get('language')
            if lang_code:
                languages.append(LanguageCode.from_iso_639_2(lang_code))
            else:
                languages.append(LanguageCode.NONE)
    except Exception:
        pass
    
    return languages

def get_file_name_without_extension(file_path):
    file_name, file_extension = os.path.splitext(file_path)
    return file_name

def get_audio_languages(video_path):
    """Extract language codes from each audio stream in the video file."""
    audio_tracks = get_audio_tracks(video_path)
    return [track['language'] for track in audio_tracks] 

def has_subtitle_language(video_file, target_language: LanguageCode):
    """Determines if a subtitle file with the target language is available."""
    return has_subtitle_language_in_file(video_file, target_language) or has_subtitle_of_language_in_folder(video_file, target_language, recursion=True, only_skip_if_subgen_subtitle=only_skip_if_subgen_subtitle)

def has_subtitle_language_in_file(video_file: str, target_language: Union[LanguageCode, None]):
    """Checks if a video file contains subtitles with a specific language."""
    try:
        probe = ffmpeg.probe(video_file, select_streams='s')
        subtitle_streams = [
            stream for stream in probe.get('streams', [])
            if stream.get('tags', {}).get('language')
        ]

        if target_language is LanguageCode.NONE:
            if skip_if_language_is_not_set_but_subtitles_exist and subtitle_streams:
                logging.debug("Language is not set, but internal subtitles exist.")
                return True
            if only_skip_if_subgen_subtitle:
                return False

        for stream in subtitle_streams:
            stream_language = LanguageCode.from_string(stream.get('tags', {}).get('language', '').lower())
            if stream_language == target_language:
                return True

        return False

    except Exception as e:
        logging.error(f"An error occurred while checking the file: {type(e).__name__}: {e}")
        return False

def has_subtitle_of_language_in_folder(video_file: str, target_language: LanguageCode, recursion: bool = True, only_skip_if_subgen_subtitle: bool = False) -> bool:
    """Checks if the given folder has a subtitle file with the given language."""
    subtitle_extensions = {'.srt', '.vtt', '.sub', '.ass', '.ssa', '.idx', '.sbv', '.pgs', '.ttml', '.lrc'}

    video_folder = os.path.dirname(video_file)
    video_name = os.path.splitext(os.path.basename(video_file))[0]

    for file_name in os.listdir(video_folder):
        file_path = os.path.join(video_folder, file_name)

        if os.path.isfile(file_path) and file_path.endswith(tuple(subtitle_extensions)):
            subtitle_name, ext = os.path.splitext(file_name)

            if not subtitle_name.startswith(video_name):
                continue

            subtitle_parts = subtitle_name[len(video_name):].lstrip(".").split(".")

            has_subgen = "subgen" in subtitle_parts

            if target_language == LanguageCode.NONE:
                if only_skip_if_subgen_subtitle:
                    if has_subgen:
                        logging.debug("Skipping subtitles because they are auto-generated ('subgen').")
                        return False
                logging.debug("Skipping subtitles because language is NONE.")
                return True

            if is_valid_subtitle_language(subtitle_parts, target_language):
                if only_skip_if_subgen_subtitle and not has_subgen:
                    continue
                logging.debug(f"Found matching subtitle: {file_name} for language {target_language.name} (subgen={has_subgen})")
                return True

        elif os.path.isdir(file_path) and recursion:
            if has_subtitle_of_language_in_folder(os.path.join(file_path, os.path.basename(video_file)), target_language, False, only_skip_if_subgen_subtitle):
                return True

    return False

def is_valid_subtitle_language(subtitle_parts: List[str], target_language: LanguageCode) -> bool:
    """Checks if any part of the subtitle name matches the target language."""
    return any(LanguageCode.from_string(part) == target_language for part in subtitle_parts)

def get_next_plex_episode(current_episode_rating_key, stay_in_season: bool = False):
    """
    Get the next episode's ratingKey based on the current episode in Plex.
    """
    try:
        url = f"{plexserver}/library/metadata/{current_episode_rating_key}"
        headers = {"X-Plex-Token": plextoken}
        response = requests.get(url, headers=headers)
        response.raise_for_status()

        root = ET.fromstring(response.content)

        grandparent_rating_key = root.find(".//Video").get("grandparentRatingKey")
        if grandparent_rating_key is None:
            logging.debug(f"Show not found for episode {current_episode_rating_key}")
            return None

        parent_rating_key = root.find(".//Video").get("parentRatingKey")
        if parent_rating_key is None:
            logging.debug(f"Parent season not found for episode {current_episode_rating_key}")
            return None

        url = f"{plexserver}/library/metadata/{grandparent_rating_key}/children"
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        seasons = ET.fromstring(response.content).findall(".//Directory[@type='season']")

        url = f"{plexserver}/library/metadata/{parent_rating_key}/children"
        response = requests.get(url, headers=headers)
        response.raise_for_status()

        episodes = ET.fromstring(response.content).findall(".//Video")
        episodes_in_season = len(episodes)

        current_episode_number = None
        current_season_number = None
        next_season_number = None
        for episode in episodes:
            if episode.get("ratingKey") == current_episode_rating_key:
                current_episode_number = int(episode.get("index"))
                current_season_number = episode.get("parentIndex")
                break

        if stay_in_season:
          if current_episode_number == episodes_in_season:
              return None
          for episode in episodes:
            if int(episode.get("index")) == int(current_episode_number)+1:
                return episode.get("ratingKey")
        else:
          for season in seasons:
              if int(season.get("index")) == int(current_season_number)+1:
                  next_season_number = season.get("ratingKey")
                  break

          if current_episode_number == episodes_in_season:
              if next_season_number is not None:
                logging.debug("At end of season, try to find next season and first episode.")
                url = f"{plexserver}/library/metadata/{next_season_number}/children"
                response = requests.get(url, headers=headers)
                response.raise_for_status()
                episodes = ET.fromstring(response.content).findall(".//Video")
                current_episode_number = 0
              else:
                return None
          for episode in episodes:
            if int(episode.get("index")) == int(current_episode_number)+1:
                return episode.get("ratingKey")

        logging.debug(f"No next episode found for {get_plex_file_name(current_episode_rating_key, plexserver, plextoken)}, possibly end of season or series")
        return None

    except requests.exceptions.RequestException as e:
        logging.error(f"Error fetching data from Plex: {e}")
        return None
    except Exception as e:
        logging.error(f"An unexpected error occurred: {e}")
        return None

def get_plex_file_name(itemid: str, server_ip: str, plex_token: str) -> str:
    """Gets the full path to a file from the Plex server."""
    url = f"{server_ip}/library/metadata/{itemid}"
    headers = {"X-Plex-Token": plex_token}
    response = requests.get(url, headers=headers)

    if response.status_code == 200:
        root = ET.fromstring(response.content)
        fullpath = root.find(".//Part").attrib['file']
        return fullpath
    else:
        raise Exception(f"Error: {response.status_code}")

def refresh_plex_metadata(itemid: str, server_ip: str, plex_token: str) -> None:
    """Refreshes the metadata of a Plex library item."""
    url = f"{server_ip}/library/metadata/{itemid}/refresh"
    headers = {"X-Plex-Token": plex_token}
    response = requests.put(url, headers=headers)

    if response.status_code == 200:
        logging.info("Metadata refresh initiated successfully.")
    else:
        raise Exception(f"Error refreshing metadata: {response.status_code}")

def refresh_jellyfin_metadata(itemid: str, server_ip: str, jellyfin_token: str) -> None:
    """Refreshes the metadata of a Jellyfin library item."""
    url = f"{server_ip}/Items/{itemid}/Refresh?MetadataRefreshMode=FullRefresh"
    headers = {"Authorization": f"MediaBrowser Token={jellyfin_token}"}

    users = json.loads(requests.get(f"{server_ip}/Users", headers=headers).content)
    jellyfin_admin = get_jellyfin_admin(users)

    response = requests.get(f"{server_ip}/Users/{jellyfin_admin}/Items/{itemid}/Refresh", headers=headers)
    response = requests.post(url, headers=headers)

    if response.status_code == 204:
        logging.info("Metadata refresh queued successfully.")
    else:
        raise Exception(f"Error refreshing metadata: {response.status_code}")


def get_jellyfin_file_name(item_id: str, jellyfin_url: str, jellyfin_token: str) -> str:
    """Gets the full path to a file from the Jellyfin server."""
    headers = {"Authorization": f"MediaBrowser Token={jellyfin_token}"}
    users = json.loads(requests.get(f"{jellyfin_url}/Users", headers=headers).content)
    jellyfin_admin = get_jellyfin_admin(users)

    response = requests.get(f"{jellyfin_url}/Users/{jellyfin_admin}/Items/{item_id}", headers=headers)

    if response.status_code == 200:
        file_name = json.loads(response.content)['Path']
        return file_name
    else:
        raise Exception(f"Error: {response.status_code}")

def get_jellyfin_admin(users):
    for user in users:
        if user["Policy"]["IsAdministrator"]:
            return user["Id"]

    raise Exception("Unable to find administrator user in Jellyfin")

def has_audio(file_path):
    try:
        if not is_valid_path(file_path):
            return False

        if not (has_video_extension(file_path) or has_audio_extension(file_path)):
            return False

        probe = ffmpeg.probe(file_path, select_streams='a')
        return len(probe.get('streams', [])) > 0

    except Exception:
        logging.debug(f"Error processing file {file_path}")
        return False

def is_valid_path(file_path):
    if not os.path.isfile(file_path):
        if not os.path.isdir(file_path):
            logging.warning(f"{file_path} is neither a file nor a directory. Are your volumes correct?")
            return False
        else:
            logging.debug(f"{file_path} is a directory, skipping processing as a file.")
            return False
    else:
        return True    

def has_video_extension(file_name):
    file_extension = os.path.splitext(file_name)[1].lower()
    return file_extension in VIDEO_EXTENSIONS

def has_audio_extension(file_name):
    file_extension = os.path.splitext(file_name)[1].lower()
    return file_extension in AUDIO_EXTENSIONS


def path_mapping(fullpath):
    if use_path_mapping:
        logging.debug("Updated path: " + fullpath.replace(path_mapping_from, path_mapping_to))
        return fullpath.replace(path_mapping_from, path_mapping_to)
    return fullpath

def is_file_stable(file_path, wait_time=2, check_intervals=3):
    """Returns True if the file size is stable for a given number of checks."""
    if not os.path.exists(file_path):
        return False

    previous_size = -1
    for _ in range(check_intervals):
        try:
            current_size = os.path.getsize(file_path)
        except OSError:
            return False

        if current_size == previous_size:
            return True
        previous_size = current_size
        time.sleep(wait_time)

    return False

if monitor:
    class NewFileHandler(FileSystemEventHandler):
        def create_subtitle(self, event):
            if not event.is_directory:
                file_path = event.src_path
                if has_audio(file_path):
                    logging.info(f"File: {path_mapping(file_path)} was added")
                    gen_subtitles_queue(path_mapping(file_path), transcribe_or_translate)

        def handle_event(self, event):
            file_path = event.src_path
            if is_file_stable(file_path):
                self.create_subtitle(event)

        def on_created(self, event):
            time.sleep(5)
            self.handle_event(event)

        def on_modified(self, event):
            self.handle_event(event)

def transcribe_existing(transcribe_folders, forceLanguage : LanguageCode | None = None):
    transcribe_folders = transcribe_folders.split("|")
    logging.info("Starting to search folders to see if we need to create subtitles.")
    logging.debug("The folders are:")
    for path in transcribe_folders:
        logging.debug(path)
        for root, dirs, files in os.walk(path):
            for file in files:
                file_path = os.path.join(root, file)
                gen_subtitles_queue(path_mapping(file_path), transcribe_or_translate, forceLanguage)
    if os.path.isfile(path):
        if has_audio(path):
            gen_subtitles_queue(path_mapping(path), transcribe_or_translate, forceLanguage) 
    if monitor:
        observer = Observer()
        for path in transcribe_folders:
            if os.path.isdir(path):
                handler = NewFileHandler()
                observer.schedule(handler, path, recursive=True)
        observer.start()
        logging.info("Finished searching and queueing files for transcription. Now watching for new files.")


if __name__ == "__main__":
    import uvicorn
    
    # Validate Groq API key on startup
    if not groq_api_key:
        logging.error("GROQ_API_KEY is not set! Please set this environment variable and restart.")
        sys.exit(1)
    
    init_groq_client()
    
    logging.info(f"Subgen v{subgen_version}")
    logging.info(f"Groq model: {groq_model}, Max chunk size: {groq_max_chunk_size_mb}MB")
    logging.info(f"Concurrent transcriptions: {concurrent_transcriptions}")
    if subtitle_tag:
        logging.info(f"Subtitle tag: {subtitle_tag}")
    uvicorn.run("__main__:app", host="0.0.0.0", port=int(webhookport), reload=reload_script_on_change, use_colors=True)
