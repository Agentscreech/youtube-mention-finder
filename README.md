# YouTube Mention Finder 🎯

A lightweight, 100% local tool to search for specific names, words, or phrases mentioned in any YouTube video. 

It downloads the audio via [`yt-dlp`](https://github.com/yt-dlp/yt-dlp), transcribes it locally using high-performance Whisper (`whisper.cpp` / [`pywhispercpp`](https://github.com/carloscdias/pywhispercpp)), caches the transcript so subsequent searches are instantaneous, and returns clickable YouTube links taking you directly to the exact second each mention occurs.

---

## ✨ Features

- **100% Local & Private:** No OpenAI API keys or cloud speech services required.
- **⚡ Idempotent & Fast:** Automatically caches transcripts (`.json` / `.txt`). Searching for different names or retrying the same video runs in **milliseconds** without re-downloading or re-transcribing.
- **Direct YouTube Timestamp Links:** Generates ready-to-click URLs (`https://youtube.com/watch?v=...&t=123s`).
- **Context Quotes:** Displays the surrounding sentence with the matched word highlighted.
- **Full Transcripts:** Exports complete timestamped transcripts to text files (`[00:01:23 -> 00:01:28] ...`).
- **Multi-Name Search:** Search for multiple names or phrases at once (comma-separated or multiple arguments).
- **Search Options:** Supports case-insensitive whole-word matching (default) or substring matching (`--partial`).
- **Auto-Discovery:** Automatically detects local models (defaults to `large-v3-turbo` or `large-v2`), `ffmpeg`, and `yt-dlp` paths.
- **Interactive & CLI Modes:** Run with command-line arguments or simply launch and follow interactive prompts.

---

## 📋 Prerequisites

1. **Python 3.8+**
2. **FFmpeg** installed and accessible in your system `PATH` (used by `yt-dlp` to extract MP3 audio and by Whisper to process audio).
   - **Windows:** Install via `winget install Gyan.FFmpeg` or download from [gyan.dev](https://www.gyan.dev/ffmpeg/builds/) and add the `bin/` folder to your environment `PATH`.
   - **macOS:** `brew install ffmpeg`
   - **Linux:** `sudo apt update && sudo apt install ffmpeg`
3. **A Whisper GGML Model:**
   - Pre-converted `.bin` models can be downloaded from [Hugging Face (ggerganov/whisper.cpp)](https://huggingface.co/ggerganov/whisper.cpp/tree/main):
     - [`ggml-large-v3-turbo.bin`](https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-large-v3-turbo.bin) (~1.6 GB - **Recommended:** fast & highly accurate)
     - [`ggml-large-v2.bin`](https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-large-v2.bin) (~3.1 GB - High accuracy)
     - [`ggml-medium.bin`](https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-medium.bin) (~1.5 GB - Good balance)
     - [`ggml-base.bin`](https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-base.bin) (~148 MB - Lightweight)
   - *Tip:* Place any downloaded `.bin` file inside a `models/` directory in this repo, or specify its path with `--model <path>` or `-m turbo` / `-m v2`.

---

## 🚀 Quick Start & Installation

### 1. Clone the repository
```bash
git clone https://github.com/Agentscreech/youtube-mention-finder.git
cd youtube-mention-finder
```

### 2. Set up a virtual environment (optional but recommended)
```bash
python -m venv .venv

# Windows (Command Prompt / PowerShell):
.venv\Scripts\activate

# macOS / Linux:
source .venv/bin/activate
```

### 3. Install dependencies
```bash
pip install -r requirements.txt
```

---

## 🛠️ Usage

### Interactive Mode
Run the script without arguments and you will be prompted for the URL and name:
```bash
python youtube_mention_finder.py
```
*(Windows users can also simply double-click `run.bat`)*

```text
Enter YouTube URL: https://www.youtube.com/watch?v=dQw4w9WgXcQ
Enter name or keyword to search (or multiple comma-separated): Rick, give up
```
In interactive mode, you can continue searching for additional names in the same video in an instant query loop without restarting!

### Command Line Mode
Provide the YouTube URL and the search term(s) directly:
```bash
# Single term:
python youtube_mention_finder.py "https://www.youtube.com/watch?v=dQw4w9WgXcQ" "Rick"

# Multiple terms:
python youtube_mention_finder.py "https://www.youtube.com/watch?v=dQw4w9WgXcQ" "Rick, give up, dessert"
```

### Example Console Output
```text
=== YOUTUBE NAME / KEYWORD TIMESTAMP FINDER ===

Target URL:   https://www.youtube.com/watch?v=jNQXAC9IVRw
Search Names: "elephants"
Output Dir:   C:\Users\...\youtube-mention-finder\yt_transcripts

>> [TRANSCRIPT CACHE HIT]
   Found previously saved transcript for: Me at the zoo
   Skipping audio download and Whisper inference! (Loaded 4 segments instantly)

Searching transcript for "elephants"...

================================================================================
FOUND 1 MENTION(S) OF "elephants":

1. [00:00] https://www.youtube.com/watch?v=jNQXAC9IVRw&t=0s
   Context: "Alright, so here we are in front of the elephants."

================================================================================
Files Generated:
  - Transcript: ...\jNQXAC9IVRw_transcript.txt
  - Mentions:   ...\jNQXAC9IVRw_mentions_elephants.txt
================================================================================
```

---

## ⚙️ Command-Line Options

| Option | Short | Default | Description |
| :--- | :---: | :---: | :--- |
| `url` | `-u` | *Prompt* | YouTube video URL (standard, shortened `youtu.be`, or video ID) |
| `names` | `-n` | *Prompt* | One or more names, keywords, or phrases to search for |
| `--model` | `-m` | Auto-detected | Path to local GGML model file (`.bin`) or alias (`turbo`, `v2`) |
| `--output-dir` | `-o` | `./yt_transcripts` | Directory where transcripts, audio, and reports are saved |
| `--force` | `-f` | *Disabled* | Force re-download and re-transcribe, bypassing cached transcripts |
| `--threads` | `-t` | `6` | Number of CPU threads to allocate for transcription |
| `--language` | `-l` | `auto` | Language code for Whisper (`en`, `es`, `fr`, `auto`, etc.) |
| `--partial` | | *Disabled* | Match substrings rather than requiring whole words |
| `--case-sensitive` | | *Disabled* | Enable case-sensitive search |
| `--no-keep-audio` | | *Disabled* | Delete the downloaded MP3 file after transcription completes |

---

## ⚡ Smart Caching & Idempotency

The tool is completely **idempotent**:
- When you run a search on a video that was previously processed, it detects the cached transcript (`.json` / `.txt`) and **skips both audio downloading and Whisper model transcription**.
- Searching for a new name or phrase on the same video executes in **milliseconds** (`< 0.1s`).
- If you ever need to re-transcribe from scratch (e.g. testing another model), pass the `--force` / `-f` flag.

### Python API Usage
You can also import and use it directly inside your own Python scripts:
```python
from youtube_mention_finder import find_mentions

# Idempotent: reuses existing transcript if already processed
urls = find_mentions("https://www.youtube.com/watch?v=dQw4w9WgXcQ", "never gonna give you up")
for url in urls:
    print(url)
```

---

## 📁 Generated Files

Each run generates the following inside the output directory (default: `yt_transcripts/`):

1. **`<video_id>.mp3`**: The downloaded audio file.
2. **`<video_id>_transcript.txt`**: The complete video transcript with start and end timestamps for every sentence/segment.
3. **`<video_id>_transcript.json`**: Structured JSON cache of all segments with timing metadata.
4. **`<video_id>_mentions_<name>.txt`**: A clean summary report listing every timestamped YouTube URL alongside the exact spoken quote.

---

## 💡 Model Auto-Discovery Order

The script looks for a Whisper GGML model in this order:
1. Path passed via `--model <path>` or aliases (`-m turbo` or `-m v2`)
2. Environment variable `WHISPER_MODEL_PATH`
3. Any `.bin` file in `./models/`
4. Default local WhisperDesktop model path (`ggml-large-v3-turbo.bin` or `ggml-large-v2.bin`)
5. Model name fallback (`large-v3-turbo` / auto-download via `pywhispercpp`)

---

## 📄 License

This project is licensed under the GNU General Public License v3.0 - see the [LICENSE](LICENSE) file for details.
