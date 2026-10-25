# YouTube Mention Finder 🎯

A lightweight, 100% local tool to search for specific names, words, or phrases mentioned in any YouTube video. 

It downloads the audio via [`yt-dlp`](https://github.com/yt-dlp/yt-dlp), transcribes it locally using high-performance Whisper (`whisper.cpp` / [`pywhispercpp`](https://github.com/carloscdias/pywhispercpp)), saves the complete timestamped transcript, and returns clickable YouTube links taking you directly to the exact second each mention occurs.

---

## ✨ Features

- **100% Local & Private:** No OpenAI API keys or cloud speech services required.
- **Direct YouTube Timestamp Links:** Generates ready-to-click URLs (`https://youtu.be/...&t=123s`).
- **Context Quotes:** Displays the surrounding sentence with the matched word highlighted.
- **Full Transcripts:** Exports complete timestamped transcripts to text files (`[00:01:23 -> 00:01:28] ...`).
- **Search Options:** Supports case-insensitive whole-word matching (default) or substring matching (`--partial`).
- **Auto-Discovery:** Automatically detects local models, `ffmpeg`, and `yt-dlp` paths.
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
     - [`ggml-base.bin`](https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-base.bin) (~148 MB - Fast)
     - [`ggml-medium.bin`](https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-medium.bin) (~1.5 GB - Great balance)
     - [`ggml-large-v2.bin`](https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-large-v2.bin) (~3.1 GB - High accuracy)
     - [`ggml-large-v3-turbo.bin`](https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-large-v3-turbo.bin) (~1.6 GB - Very fast & accurate)
   - *Tip:* Place any downloaded `.bin` file inside a `models/` directory in this repo, or specify its path with `--model <path>`.

---

## 🚀 Quick Start & Installation

### 1. Clone the repository
```bash
git clone https://github.com/<your-username>/youtube-mention-finder.git
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
Enter name or keyword to search: Rick
```

### Command Line Mode
Provide the YouTube URL and the search term directly:
```bash
python youtube_mention_finder.py "https://www.youtube.com/watch?v=dQw4w9WgXcQ" "Rick"
```

### Example Console Output
```text
=== YOUTUBE NAME / KEYWORD TIMESTAMP FINDER ===

Target URL:  https://www.youtube.com/watch?v=jNQXAC9IVRw
Target Name: "elephants"
Output Dir:  C:\Users\...\youtube-mention-finder\yt_transcripts

[1/4] Retrieving video information...
      Title: Me at the zoo
      Video ID: jNQXAC9IVRw
      Duration: 00:19
[2/4] Downloading audio with yt-dlp...
      Audio saved to: ...\jNQXAC9IVRw.mp3
[3/4] Transcribing audio with Whisper local model...
      Model: ggml-large-v2.bin
      Threads: 6
      Transcription complete!
      Full transcript written to: ...\jNQXAC9IVRw_transcript.txt

[4/4] Searching transcript for "elephants"...

================================================================================
FOUND 1 MENTION(S) OF "elephants":

1. [00:00] https://www.youtube.com/watch?v=jNQXAC9IVRw&t=0s
   Context: "Alright, so here we are in front of the elephants."

================================================================================
Files Generated:
  - Transcript: ...\jNQXAC9IVRw_transcript.txt
  - Mentions:   ...\jNQXAC9IVRw_mentions_elephants.txt
  - Audio:      ...\jNQXAC9IVRw.mp3
================================================================================
```

---

## ⚙️ Command-Line Options

| Option | Short | Default | Description |
| :--- | :---: | :---: | :--- |
| `url` | `-u` | *Prompt* | YouTube video URL (standard, shortened `youtu.be`, or video ID) |
| `name` | `-n` | *Prompt* | Name, keyword, or phrase to search for |
| `--model` | `-m` | Auto-detected | Path to local GGML model file (`.bin`) or standard model name |
| `--output-dir` | `-o` | `./yt_transcripts` | Directory where transcripts, audio, and reports are saved |
| `--threads` | `-t` | `6` | Number of CPU threads to allocate for transcription |
| `--language` | `-l` | `auto` | Language code for Whisper (`en`, `es`, `fr`, `auto`, etc.) |
| `--partial` | | *Disabled* | Match substrings rather than requiring whole words |
| `--case-sensitive` | | *Disabled* | Enable case-sensitive search |
| `--no-keep-audio` | | *Disabled* | Delete the downloaded MP3 file after transcription completes |

---

## 📁 Generated Files

Each run generates the following inside the output directory (default: `yt_transcripts/`):

1. **`<video_id>.mp3`**: The downloaded audio file.
2. **`<video_id>_transcript.txt`**: The complete video transcript with start and end timestamps for every sentence/segment.
3. **`<video_id>_mentions_<name>.txt`**: A clean summary report listing every timestamped YouTube URL alongside the exact spoken quote.

---

## 💡 Model Auto-Discovery Order

The script looks for a Whisper GGML model in this order:
1. Path passed via `--model <path>`
2. Environment variable `WHISPER_MODEL_PATH`
3. Any `.bin` file in `./models/`
4. Default local WhisperDesktop model path (if installed on Windows)
5. Model name fallback (`large-v2` / auto-download via `pywhispercpp`)

---

## 📄 License

This project is licensed under the GNU General Public License v3.0 - see the [LICENSE](LICENSE) file for details.
