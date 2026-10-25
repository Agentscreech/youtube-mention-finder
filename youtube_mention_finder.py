#!/usr/bin/env python3
"""
YouTube Name / Keyword Timestamp Finder
=======================================
Downloads audio from a YouTube video using yt-dlp, transcribes it locally using
Whisper (ggml models via pywhispercpp), saves the transcript to a text & JSON file,
caches transcriptions so subsequent searches on the same video are instantaneous,
and outputs clickable timestamped YouTube URLs with context quotes.

Usage:
  python youtube_mention_finder.py "<youtube_url>" "<name>"
  python youtube_mention_finder.py "<youtube_url>" "Name1, Name2"
  python youtube_mention_finder.py --url "<youtube_url>" --name "<name>"
  python youtube_mention_finder.py  (interactive multi-search mode)
"""

import sys
import os
import re
import json
import shutil
import argparse
import subprocess
from pathlib import Path
from typing import List, Dict, Any, Optional, Union

# Configure UTF-8 output if possible
if sys.platform == "win32" and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass
HOST_FFMPEG_DIR = r"C:\Users\exoti\ffmpeg-4.3.1-2020-11-19-full_build\bin"
HOST_YTDLP_PATH = r"C:\Users\exoti\Downloads\yt-dlp.exe"
HOST_MODEL_V3_TURBO = r"C:\Users\exoti\Downloads\WhisperDesktop\ggml-large-v3-turbo.bin"
HOST_MODEL_V2 = r"C:\Users\exoti\Downloads\WhisperDesktop\ggml-large-v2.bin"

# Inject ffmpeg into PATH if needed
if not shutil.which("ffmpeg") and os.path.isdir(HOST_FFMPEG_DIR):
    os.environ["PATH"] = HOST_FFMPEG_DIR + os.pathsep + os.environ.get("PATH", "")


class CachedSegment:
    """Represents a transcript segment loaded from cache."""
    def __init__(self, t0: int, t1: int, text: str):
        self.t0 = int(t0)  # in centiseconds (10ms units)
        self.t1 = int(t1)  # in centiseconds
        self.text = text.strip()

    def __str__(self):
        return f"[{self.t0/100:.2f}s -> {self.t1/100:.2f}s] {self.text}"


def resolve_model_path(requested: Optional[str] = None) -> str:
    """Resolves model path from alias ('turbo', 'v2'), environment, or defaults."""
    if requested:
        key = requested.strip().lower()
        if key in ("turbo", "large-v3-turbo", "v3-turbo"):
            if os.path.isfile(HOST_MODEL_V3_TURBO):
                return HOST_MODEL_V3_TURBO
            return "large-v3-turbo"
        if key in ("v2", "large-v2"):
            if os.path.isfile(HOST_MODEL_V2):
                return HOST_MODEL_V2
            return "large-v2"
        if os.path.isfile(requested):
            return requested
        return requested

    # 1. Environment variable
    env_path = os.environ.get("WHISPER_MODEL_PATH")
    if env_path:
        return resolve_model_path(env_path)

    # 2. Local ./models/ directory
    local_models_dir = Path("./models")
    if local_models_dir.is_dir():
        bins = list(local_models_dir.glob("*.bin"))
        if bins:
            for b in bins:
                if "turbo" in b.name.lower() or "large-v2" in b.name.lower():
                    return str(b.resolve())
            return str(bins[0].resolve())

    # 3. Known host download location (prefer turbo if available, fallback to v2)
    if os.path.isfile(HOST_MODEL_V3_TURBO):
        return HOST_MODEL_V3_TURBO
    if os.path.isfile(HOST_MODEL_V2):
        return HOST_MODEL_V2

    return "large-v3-turbo"


def get_default_model_path() -> str:
    """Finds the best available Whisper model path or model identifier."""
    return resolve_model_path()


# ANSI Color codes for styled console output
class Colors:
    HEADER = "\033[95m"
    BLUE = "\033[94m"
    CYAN = "\033[96m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    BOLD = "\033[1m"
    UNDERLINE = "\033[4m"
    RESET = "\033[0m"

    @classmethod
    def enable_windows_colors(cls):
        if sys.platform == "win32":
            try:
                import ctypes
                kernel32 = ctypes.windll.kernel32
                handle = kernel32.GetStdHandle(-11)  # STD_OUTPUT_HANDLE
                mode = ctypes.c_ulong()
                kernel32.GetConsoleMode(handle, ctypes.byref(mode))
                kernel32.SetConsoleMode(handle, mode.value | 0x0004)  # ENABLE_VIRTUAL_TERMINAL_PROCESSING
            except Exception:
                pass


def find_executable(name: str, fallback_path: Optional[str] = None) -> str:
    """Finds an executable in PATH or fallback path."""
    found = shutil.which(name)
    if found:
        return found
    if fallback_path and os.path.isfile(fallback_path):
        return fallback_path
    return name


def sanitize_filename(name: str) -> str:
    """Removes invalid filesystem characters."""
    return re.sub(r'[\\/*?:"<>|]', "_", name).strip()


def format_timestamp(seconds: float) -> str:
    """Formats seconds into HH:MM:SS or MM:SS."""
    total_seconds = int(seconds)
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    secs = total_seconds % 60
    if hours > 0:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def parse_timestamp_str(ts_str: str) -> float:
    """Parses a timestamp string like '01:23' or '01:05:23' into seconds."""
    parts = ts_str.strip().split(":")
    if len(parts) == 3:
        return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
    elif len(parts) == 2:
        return int(parts[0]) * 60 + float(parts[1])
    return float(parts[0])


def extract_video_id(url: str) -> Optional[str]:
    """Extracts YouTube 11-character video ID from common URL patterns."""
    patterns = [
        r"(?:v=|\/v\/|youtu\.be\/|\/embed\/|\/live\/|\/shorts\/)([a-zA-Z0-9_-]{11})",
        r"^([a-zA-Z0-9_-]{11})$",
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return None


def get_video_metadata(ytdlp_bin: str, url: str) -> Dict[str, Any]:
    """Retrieves video title and ID using yt-dlp without downloading."""
    try:
        cmd = [
            ytdlp_bin,
            "--skip-download",
            "--print", "%(id)s",
            "--print", "%(title)s",
            "--print", "%(duration)s",
            url
        ]
        res = subprocess.run(cmd, capture_output=True, text=True, check=True)
        lines = [line.strip() for line in res.stdout.strip().splitlines() if line.strip()]
        vid_id = lines[0] if len(lines) > 0 else extract_video_id(url)
        title = lines[1] if len(lines) > 1 else (vid_id or "youtube_video")
        duration = float(lines[2]) if len(lines) > 2 and lines[2].replace('.', '', 1).isdigit() else 0.0
        return {"id": vid_id, "title": title, "duration": duration}
    except Exception:
        vid_id = extract_video_id(url) or "video"
        return {"id": vid_id, "title": vid_id, "duration": 0.0}


def load_cached_transcript(output_dir: Path, video_id: str) -> Optional[Dict[str, Any]]:
    """
    Checks if a cached transcript already exists for this video_id.
    Reads either structured JSON cache or parses the text transcript.
    """
    json_path = output_dir / f"{video_id}_transcript.json"
    txt_path = output_dir / f"{video_id}_transcript.txt"

    # 1. Prefer JSON cache (fast & lossless)
    if json_path.is_file():
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            segments = [
                CachedSegment(s["t0"], s["t1"], s["text"])
                for s in data.get("segments", [])
            ]
            if segments:
                return {
                    "segments": segments,
                    "metadata": {
                        "id": data.get("video_id", video_id),
                        "title": data.get("title", f"Video {video_id}"),
                        "duration": data.get("duration", 0.0),
                        "model": data.get("model", "cached")
                    },
                    "transcript_file": txt_path if txt_path.exists() else json_path,
                    "cache_type": "json"
                }
        except Exception:
            pass

    # 2. Fallback: Parse existing .txt transcript
    if txt_path.is_file():
        try:
            segments = []
            title = f"Video {video_id}"
            with open(txt_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("TRANSCRIPT:"):
                        title = line.split("TRANSCRIPT:", 1)[1].strip()
                    # Match line format: [00:00 -> 00:04] text
                    m = re.match(r"^\[(\d{2}:\d{2}(?::\d{2})?)\s*->\s*(\d{2}:\d{2}(?::\d{2})?)\]\s*(.*)$", line)
                    if m:
                        t0_sec = parse_timestamp_str(m.group(1))
                        t1_sec = parse_timestamp_str(m.group(2))
                        text = m.group(3)
                        segments.append(CachedSegment(int(t0_sec * 100), int(t1_sec * 100), text))

            if segments:
                return {
                    "segments": segments,
                    "metadata": {
                        "id": video_id,
                        "title": title,
                        "duration": segments[-1].t1 / 100.0,
                        "model": "cached"
                    },
                    "transcript_file": txt_path,
                    "cache_type": "txt"
                }
        except Exception:
            pass

    return None


def download_youtube_audio(
    url: str,
    output_dir: Path,
    ytdlp_bin: str,
    ffmpeg_dir: Optional[str] = None
) -> Dict[str, Any]:
    """
    Downloads YouTube audio as MP3 using:
    yt-dlp -x --audio-format mp3 <url>
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"{Colors.CYAN}[1/4] Retrieving video information...{Colors.RESET}")
    meta = get_video_metadata(ytdlp_bin, url)
    video_id = meta["id"] or "audio"

    output_template = str(output_dir / f"{video_id}.%(ext)s")
    final_mp3_path = output_dir / f"{video_id}.mp3"

    print(f"      {Colors.BOLD}Title:{Colors.RESET} {meta['title']}")
    print(f"      {Colors.BOLD}Video ID:{Colors.RESET} {video_id}")
    if meta.get("duration"):
        print(f"      {Colors.BOLD}Duration:{Colors.RESET} {format_timestamp(meta['duration'])}")

    # Check if audio already exists
    if final_mp3_path.is_file():
        print(f"      {Colors.GREEN}[Audio Cache Hit] Found existing audio at:{Colors.RESET} {final_mp3_path}")
        return {
            "audio_path": str(final_mp3_path),
            "video_id": video_id,
            "title": meta["title"],
            "duration": meta.get("duration", 0.0)
        }

    print(f"{Colors.CYAN}[2/4] Downloading audio with yt-dlp...{Colors.RESET}")
    cmd = [
        ytdlp_bin,
        "-x",
        "--audio-format", "mp3",
        "--windows-filenames",
        "-o", output_template,
        url
    ]
    if ffmpeg_dir and os.path.isdir(ffmpeg_dir):
        cmd.extend(["--ffmpeg-location", ffmpeg_dir])

    # Run yt-dlp
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        if not final_mp3_path.exists():
            print(f"{Colors.RED}yt-dlp download failed:{Colors.RESET}\n{result.stderr}")
            sys.exit(1)

    if not final_mp3_path.exists():
        candidates = list(output_dir.glob(f"*{video_id}*.mp3")) or list(output_dir.glob("*.mp3"))
        if candidates:
            final_mp3_path = max(candidates, key=os.path.getmtime)
        else:
            raise FileNotFoundError(f"Expected audio file {final_mp3_path} not found after download.")

    print(f"      {Colors.GREEN}Audio saved to:{Colors.RESET} {final_mp3_path}")
    return {
        "audio_path": str(final_mp3_path),
        "video_id": video_id,
        "title": meta["title"],
        "duration": meta.get("duration", 0.0)
    }


def transcribe_audio(
    audio_path: str,
    model_path: str,
    output_txt_path: Path,
    output_json_path: Path,
    metadata: Dict[str, Any],
    n_threads: int = 6,
    language: str = "auto"
) -> List[Any]:
    """
    Transcribes audio using pywhispercpp with local GGML Whisper model,
    and writes both formatted .txt and structured .json transcript cache files.
    """
    try:
        from pywhispercpp.model import Model
    except ImportError:
        print(f"{Colors.RED}Error: pywhispercpp is not installed.{Colors.RESET}")
        print("Please install requirements: pip install -r requirements.txt")
        sys.exit(1)

    print(f"{Colors.CYAN}[3/4] Transcribing audio with Whisper local model...{Colors.RESET}")
    print(f"      {Colors.BOLD}Model:{Colors.RESET} {model_path}")
    print(f"      {Colors.BOLD}Threads:{Colors.RESET} {n_threads}")
    print("      Transcribing, please wait (progress logged below)...")

    model_kwargs = {"n_threads": n_threads}
    if language and language != "auto":
        model_kwargs["language"] = language

    whisper_model = Model(model_path, **model_kwargs)

    # Callback to display live progress
    def on_new_segment(seg):
        start_fmt = format_timestamp(seg.t0 / 100.0)
        end_fmt = format_timestamp(seg.t1 / 100.0)
        sys.stdout.write(f"\r  [{start_fmt} -> {end_fmt}] {seg.text[:70]:<70}")
        sys.stdout.flush()

    segments = whisper_model.transcribe(audio_path, new_segment_callback=on_new_segment)
    print("\n      " + Colors.GREEN + "Transcription complete!" + Colors.RESET)

    model_display_name = Path(model_path).name if os.path.exists(model_path) else model_path

    # 1. Write transcript text file
    output_txt_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_txt_path, "w", encoding="utf-8") as f:
        f.write("=" * 80 + "\n")
        f.write(f"TRANSCRIPT: {metadata.get('title', 'YouTube Video')}\n")
        f.write(f"Video ID:   {metadata.get('video_id', '')}\n")
        f.write(f"Model:      {model_display_name}\n")
        f.write("=" * 80 + "\n\n")

        for seg in segments:
            start_sec = seg.t0 / 100.0
            end_sec = seg.t1 / 100.0
            line = f"[{format_timestamp(start_sec)} -> {format_timestamp(end_sec)}] {seg.text.strip()}\n"
            f.write(line)

    # 2. Write structured JSON cache
    json_data = {
        "video_id": metadata.get("video_id", ""),
        "title": metadata.get("title", ""),
        "duration": metadata.get("duration", 0.0),
        "model": model_display_name,
        "segments": [
            {"t0": seg.t0, "t1": seg.t1, "text": seg.text.strip()}
            for seg in segments
        ]
    }
    with open(output_json_path, "w", encoding="utf-8") as f:
        json.dump(json_data, f, indent=2, ensure_ascii=False)

    print(f"      {Colors.GREEN}Full transcript written to:{Colors.RESET} {output_txt_path}")
    print(f"      {Colors.GREEN}Structured cache saved to:{Colors.RESET} {output_json_path}")
    return segments


def search_name_in_transcript(
    segments: List[Any],
    name: str,
    video_id: str,
    case_sensitive: bool = False,
    exact_word: bool = True
) -> List[Dict[str, Any]]:
    """
    Parses transcript segments for occurrences of the name/keyword.
    Returns a list of match dictionaries with timestamps and YouTube URLs.
    """
    escaped_name = re.escape(name.strip())
    pattern_str = rf"\b{escaped_name}\b" if exact_word else escaped_name
    flags = 0 if case_sensitive else re.IGNORECASE
    regex = re.compile(pattern_str, flags)

    matches = []

    for seg in segments:
        text = seg.text.strip()
        found = list(regex.finditer(text))
        if found:
            start_sec = int(seg.t0 / 100.0)
            end_sec = int(seg.t1 / 100.0)

            # Construct timestamp YouTube URL
            yt_url = f"https://www.youtube.com/watch?v={video_id}&t={start_sec}s"

            # Create highlighted text for terminal and clean text for file
            highlighted = regex.sub(lambda m: f"{Colors.YELLOW}{Colors.BOLD}{m.group(0)}{Colors.RESET}", text)
            plain_highlighted = regex.sub(lambda m: f">>>{m.group(0)}<<<", text)

            matches.append({
                "timestamp_seconds": start_sec,
                "timestamp_str": format_timestamp(start_sec),
                "end_timestamp_str": format_timestamp(end_sec),
                "url": yt_url,
                "text": text,
                "highlighted_terminal": highlighted,
                "highlighted_plain": plain_highlighted,
                "count_in_segment": len(found)
            })

    return matches


def save_mentions_report(
    report_path: Path,
    name: str,
    metadata: Dict[str, Any],
    matches: List[Dict[str, Any]],
    transcript_file: Path
):
    """Saves a summary report of all timestamped URLs to a text file."""
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("=" * 80 + "\n")
        f.write(f"MENTIONS REPORT FOR: \"{name}\"\n")
        f.write(f"Video Title: {metadata.get('title', '')}\n")
        f.write(f"Video URL:   https://www.youtube.com/watch?v={metadata.get('video_id', '')}\n")
        f.write(f"Transcript:  {transcript_file.resolve()}\n")
        f.write(f"Total Mentions Found: {len(matches)}\n")
        f.write("=" * 80 + "\n\n")

        if not matches:
            f.write(f"No mentions of \"{name}\" were found in the transcript.\n")
        else:
            f.write("LIST OF TIMESTAMPED URLS:\n")
            f.write("-" * 80 + "\n")
            for idx, m in enumerate(matches, 1):
                f.write(f"{idx}. [{m['timestamp_str']}] {m['url']}\n")
                f.write(f"   Context: \"{m['highlighted_plain']}\"\n\n")


def display_and_save_search_results(
    segments: List[Any],
    name: str,
    video_id: str,
    metadata: Dict[str, Any],
    transcript_file: Path,
    output_dir: Path,
    case_sensitive: bool = False,
    exact_word: bool = True
) -> List[str]:
    """Searches segments for a name, displays results, and writes the report."""
    print(f"\n{Colors.CYAN}Searching transcript for \"{name}\"...{Colors.RESET}")
    matches = search_name_in_transcript(
        segments=segments,
        name=name,
        video_id=video_id,
        case_sensitive=case_sensitive,
        exact_word=exact_word
    )

    safe_name = sanitize_filename(name.replace(" ", "_"))
    report_file = output_dir / f"{video_id}_mentions_{safe_name}.txt"
    save_mentions_report(report_file, name, metadata, matches, transcript_file)

    # Display Results
    print(f"\n" + "=" * 80)
    if matches:
        print(f"{Colors.GREEN}{Colors.BOLD}FOUND {len(matches)} MENTION(S) OF \"{name}\":{Colors.RESET}\n")
        for idx, m in enumerate(matches, 1):
            print(f"{Colors.BOLD}{idx}. [{m['timestamp_str']}]{Colors.RESET} {Colors.BLUE}{Colors.UNDERLINE}{m['url']}{Colors.RESET}")
            print(f"   Context: \"{m['highlighted_terminal']}\"\n")
    else:
        print(f"{Colors.YELLOW}No mentions of \"{name}\" were found in the transcript.{Colors.RESET}")
        print(f"Tip: Try --partial or check spelling in the transcript file:")
        print(f"     {transcript_file}\n")

    print("=" * 80)
    print(f"{Colors.BOLD}Files Generated:{Colors.RESET}")
    print(f"  - Transcript: {transcript_file}")
    print(f"  - Mentions:   {report_file}")
    print("=" * 80 + "\n")

    return [m["url"] for m in matches]


def process_youtube_name_finder(
    url: str,
    names: Union[str, List[str]],
    model_path: Optional[str] = None,
    output_dir_str: str = "./yt_transcripts",
    case_sensitive: bool = False,
    exact_word: bool = True,
    keep_audio: bool = True,
    n_threads: int = 6,
    language: str = "auto",
    force_transcribe: bool = False
) -> Dict[str, List[str]]:
    """
    Main pipeline function with automatic transcript caching:
    1. Checks if video transcript was already generated and cached.
    2. If cached, skips download & transcription completely!
    3. If not cached, downloads audio and transcribes with Whisper.
    4. Searches transcript for the given name(s).
    5. Returns dictionary of name -> list of timestamped URLs.
    """
    Colors.enable_windows_colors()
    output_dir = Path(output_dir_str).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    # Normalize names list (splits comma-separated strings even if in a list)
    name_list = []
    raw_items = [names] if isinstance(names, str) else names
    for item in raw_items:
        for sub in item.split(","):
            sub = sub.strip()
            if sub and sub not in name_list:
                name_list.append(sub)

    video_id = extract_video_id(url)
    model_path = resolve_model_path(model_path)

    formatted_names = ", ".join(f'"{n}"' for n in name_list)
    print(f"\n{Colors.BOLD}{Colors.HEADER}=== YOUTUBE NAME / KEYWORD TIMESTAMP FINDER ==={Colors.RESET}\n")
    print(f"Target URL:   {url}")
    print(f"Search Names: {formatted_names}")
    print(f"Output Dir:   {output_dir}\n")

    cached_data = None
    if not force_transcribe and video_id:
        cached_data = load_cached_transcript(output_dir, video_id)

    if cached_data:
        # Cache hit!
        segments = cached_data["segments"]
        meta = cached_data["metadata"]
        transcript_file = cached_data["transcript_file"]
        print(f"{Colors.GREEN}{Colors.BOLD}>> [TRANSCRIPT CACHE HIT]{Colors.RESET}")
        print(f"   Found previously saved transcript for: {Colors.BOLD}{meta.get('title', video_id)}{Colors.RESET}")
        print(f"   Skipping audio download and Whisper inference! (Loaded {len(segments)} segments instantly)")
    else:
        # Locate tools for fresh download & transcription
        ytdlp_bin = find_executable("yt-dlp", HOST_YTDLP_PATH)
        ffmpeg_dir = HOST_FFMPEG_DIR if os.path.isdir(HOST_FFMPEG_DIR) else None

        # Step 1 & 2: Download Audio
        meta = download_youtube_audio(url, output_dir, ytdlp_bin, ffmpeg_dir)
        audio_path = meta["audio_path"]
        video_id = meta["video_id"]

        # Step 3: Transcribe
        transcript_file = output_dir / f"{video_id}_transcript.txt"
        transcript_json = output_dir / f"{video_id}_transcript.json"
        segments = transcribe_audio(
            audio_path=audio_path,
            model_path=model_path,
            output_txt_path=transcript_file,
            output_json_path=transcript_json,
            metadata=meta,
            n_threads=n_threads,
            language=language
        )

        # Clean up audio if requested
        if not keep_audio and os.path.exists(audio_path):
            try:
                os.remove(audio_path)
                print(f"      {Colors.YELLOW}Audio file cleaned up.{Colors.RESET}")
            except Exception:
                pass

    # Search for all requested names
    all_results = {}
    for target_name in name_list:
        urls = display_and_save_search_results(
            segments=segments,
            name=target_name,
            video_id=video_id,
            metadata=meta,
            transcript_file=transcript_file,
            output_dir=output_dir,
            case_sensitive=case_sensitive,
            exact_word=exact_word
        )
        all_results[target_name] = urls

    return {
        "results": all_results,
        "segments": segments,
        "video_id": video_id,
        "metadata": meta,
        "transcript_file": transcript_file,
        "output_dir": output_dir
    }


def find_mentions(
    url: str,
    name: str,
    model_path: Optional[str] = None,
    output_dir: str = "./yt_transcripts",
    case_sensitive: bool = False,
    exact_word: bool = True,
    force_transcribe: bool = False,
    **kwargs
) -> List[str]:
    """
    Idempotent search function:
    Takes a YouTube URL and phrase/name, reuses existing transcript if video
    has already been processed, and returns a list of timestamped YouTube URLs.
    """
    res = process_youtube_name_finder(
        url=url,
        names=name,
        model_path=model_path,
        output_dir_str=output_dir,
        case_sensitive=case_sensitive,
        exact_word=exact_word,
        force_transcribe=force_transcribe,
        **kwargs
    )
    all_res = res.get("results", {})
    if name in all_res:
        return all_res[name]
    if len(all_res) == 1:
        return list(all_res.values())[0]
    urls = []
    for u_list in all_res.values():
        for u in u_list:
            if u not in urls:
                urls.append(u)
    return urls


def main():
    default_model = get_default_model_path()
    parser = argparse.ArgumentParser(
        description="Download YouTube audio, transcribe with local Whisper model, and find timestamped URLs where a name is mentioned (with smart caching for instant retries)."
    )
    parser.add_argument("url", nargs="?", help="YouTube video URL")
    parser.add_argument("names", nargs="*", help="One or more names or phrases to search for")
    parser.add_argument("-u", "--url-opt", dest="url_opt", help="YouTube video URL (flag option)")
    parser.add_argument("-n", "--name-opt", dest="name_opt", help="Name or phrase to search for (flag option)")
    parser.add_argument("-m", "--model", default=default_model, help=f"Path or alias ('turbo', 'v2') of GGML Whisper model (default: {default_model})")
    parser.add_argument("-o", "--output-dir", default="./yt_transcripts", help="Directory for output files (default: ./yt_transcripts)")
    parser.add_argument("-t", "--threads", type=int, default=6, help="Number of CPU threads for Whisper (default: 6)")
    parser.add_argument("-l", "--language", default="auto", help="Language code (e.g. 'en', 'auto')")
    parser.add_argument("-f", "--force", action="store_true", help="Force re-download and re-transcribe, ignoring any existing cached transcript")
    parser.add_argument("--case-sensitive", action="store_true", help="Enable case-sensitive matching")
    parser.add_argument("--partial", dest="partial", action="store_true", help="Allow substring matching instead of whole word")
    parser.add_argument("--no-keep-audio", action="store_true", help="Delete the downloaded MP3 after transcription")

    args = parser.parse_args()

    url = args.url or args.url_opt
    names = args.names or ([args.name_opt] if args.name_opt else [])

    interactive = False
    if not url:
        interactive = True
        try:
            url = input("Enter YouTube URL: ").strip()
        except (KeyboardInterrupt, EOFError):
            sys.exit(0)

    if not names:
        interactive = True
        try:
            n_input = input("Enter name or keyword to search (or multiple comma-separated): ").strip()
            names = [x.strip() for x in n_input.split(",") if x.strip()]
        except (KeyboardInterrupt, EOFError):
            sys.exit(0)

    if not url:
        print(f"{Colors.RED}Error: A YouTube URL is required.{Colors.RESET}")
        sys.exit(1)
    if not names:
        print(f"{Colors.RED}Error: At least one name or search term is required.{Colors.RESET}")
        sys.exit(1)

    # Process first search
    res = process_youtube_name_finder(
        url=url,
        names=names,
        model_path=args.model,
        output_dir_str=args.output_dir,
        case_sensitive=args.case_sensitive,
        exact_word=not args.partial,
        keep_audio=not args.no_keep_audio,
        n_threads=args.threads,
        language=args.language,
        force_transcribe=args.force
    )

    # If launched interactively, allow searching for additional names instantly in a loop!
    if interactive:
        while True:
            try:
                print(f"{Colors.CYAN}Search for another name in this video?{Colors.RESET} (Press Enter to exit, or type a new name): ", end="")
                next_name = input().strip()
                if not next_name:
                    break
                display_and_save_search_results(
                    segments=res["segments"],
                    name=next_name,
                    video_id=res["video_id"],
                    metadata=res["metadata"],
                    transcript_file=res["transcript_file"],
                    output_dir=res["output_dir"],
                    case_sensitive=args.case_sensitive,
                    exact_word=not args.partial
                )
            except (KeyboardInterrupt, EOFError):
                break


if __name__ == "__main__":
    main()
