<div align="center">

# 💖 Multi-Platform Live Chat Overlay + Benderina AI 🤖✨

**A sleek, vertical live chat overlay for YouTube Live, Twitch, and TikTok Live—powered by Python, Pygame, and a sarcastic local AI co-host running on Ollama.**

[![Python](https://img.shields.io/badge/Python-3.9%2B-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![Pygame](https://img.shields.io/badge/Pygame-UI%20Engine-00C853?style=for-the-badge&logo=python&logoColor=white)](https://www.pygame.org/)
[![Ollama](https://img.shields.io/badge/Ollama-Local%20LLM-000000?style=for-the-badge&logo=ollama&logoColor=white)](https://ollama.com/)
[![OBS Studio](https://img.shields.io/badge/OBS%20Studio-Chroma%20Ready-302E31?style=for-the-badge&logo=obsstudio&logoColor=white)](https://obsproject.com/)
[![License: MIT](https://img.shields.io/badge/License-MIT-FF69B9?style=for-the-badge)](LICENSE)

<br />

📺 **YouTube Live** • 💜 **Twitch** • 🎵 **TikTok Live** • 🎙️ **Real-Time TTS** • 🧠 **100% Local AI**

[✨ Features](#-features) • [📦 Installation](#-installation) • [⚙️ Configuration](#%EF%B8%8F-configuration) • [⌨️ Controls](#%EF%B8%8F-keyboard-shortcuts) • [🎥 OBS Setup](#-obs-studio-integration)

</div>

---

## 🌟 Overview

Designed as a dedicated **`540×960` vertical side panel** for **OBS Studio**, this tool unifies all your live stream chats into one stylish **cyber-rose dark UI**—complete with animated audio waveforms, procedural alert sounds, and **Benderina AI**, a witty robotic co-host that roasts your chat in real time with zero cloud API fees.

---

## ✨ Features

| Feature | Description |
| :--- | :--- |
| 🌐 **Unified Multi-Platform Chat** | Aggregates **YouTube Live**, **Twitch**, and **TikTok Live** simultaneously with color-coded badges and live status pills (`LIVE` / `BUSCANDO`). |
| 🔓 **Zero-Auth Streaming Setup** | Connect immediately—no Google API keys for YouTube and no OAuth tokens for Twitch IRC. |
| 🤖 **Local AI Co-Host (Ollama)** | Powered by `llama3.2:latest` with rotating comedic angles, high creativity settings, and anti-repetition memory so replies stay fresh. |
| 🗣️ **Built-In TTS & Sound FX** | Reads incoming comments and AI roasts aloud with smart local MP3/WAV caching, plus synthesized chime & arpeggio alerts for messages, Gifts, Bits, and Super Chats. |
| 🎨 **OBS-Ready Cyber-Rose UI** | Crisp dark interface with neon pink accents, smooth voice equalizer bars, and a 1-key **Chroma Key Green** toggle (`C`). |
| 🐧 **Linux Audio Resilient** | Seamlessly adapts across `pygame.mixer`, `pw-play` (PipeWire), `paplay` (PulseAudio), `ffplay`, `mpv`, and `espeak-ng`. |

---

## 📋 Prerequisites

Before launching the overlay, make sure you have:

1. 🐍 **Python 3.9+** installed.
2. 🦙 **Ollama** installed and running locally with your preferred model:
   ```bash
   ollama pull llama3.2:latest
   ollama serve
   ```
3. 🔊 **Linux Audio Tools *(Recommended)*:** `ffmpeg` plus a native player (`pipewire` / `pulseaudio` / `mpv` / `espeak-ng`) for rock-solid TTS playback.

---

## 📦 Installation

### 1. Clone the repository
```bash
git clone https://github.com/your-username/your-repo-name.git
cd your-repo-name
```

### 2. Create and activate a virtual environment *(recommended)*
```bash
python3 -m venv venv

# Linux / macOS
source venv/bin/activate

# Windows
venv\Scripts\activate
```

### 3. Install Python dependencies
```bash
pip install pygame requests pillow TikTokLive
```

---

## ⚙️ Configuration

Open the main script (e.g., `main.py`) and update the **General Configuration** block at the top with your channels:

```python
# ================= CONFIGURACIÓN GENERAL =================
HOST_NAME = "YourName"                                        # Your name/nickname used by the AI
TIKTOK_USERNAME = "@your_tiktok_user"                         # Your TikTok username
TWITCH_CHANNEL = "your_twitch_channel"                        # Your Twitch channel name
YOUTUBE_CHANNEL_URL = "https://www.youtube.com/@your_channel" # Your YouTube channel URL
```

> [!TIP]
> **Want to switch models or languages?**
> - 🧠 **LLM Model:** Change `OLLAMA_MODEL = "llama3.2:latest"` to any model pulled in Ollama.
> - 🌍 **Language & Voice:** The AI persona and TTS (`tl="es-MX"`) default to Latin American Spanish. Edit the `prompt` inside `BenderinaNarrator._ollama_worker` and the `tl` parameter in `BenderinaNarrator._tts_worker` to customize it for any language.

---

## 🚀 Usage

Make sure Ollama is running in the background, then launch the overlay:

```bash
python main.py
```

On the first launch, the app automatically creates an `assets_dev_stream/` directory containing synthesized `.wav` alert sounds and a `tts/` cache folder.

### ⌨️ Keyboard Shortcuts

| Key | Action |
| :---: | :--- |
| **`C`** | 🟢 Toggle **Chroma Key Green** background for OBS Studio |
| **`T`** | 🧪 Send a **simulated test comment** to preview UI, AI, and TTS |
| **`M`** | 🔇 **Mute / Unmute** TTS voice output *(on-screen subtitles stay active)* |
| **`L`** | 🧹 **Clear** all chat messages from the feed |

---

## 🎥 OBS Studio Integration

Follow these steps to blend the overlay seamlessly into your stream:

1. ▶️ Run `python main.py` and press **`C`** to switch the background to pure green (`#00FF00`).
2. ➕ In **OBS Studio**, add a **Window Capture** source and select `Chat Multiplataforma Dev Live + Benderina IA`.
3. 🎛️ Right-click the source → **Filters** → Add a **Chroma Key** filter *(Key Color Type: **Green**)*.
4. 📐 Resize and dock the vertical panel along the edge of your coding or streaming scene.

---

## 🛠️ Troubleshooting

> [!NOTE]
> **YouTube badge stays on `BUSCANDO`?**
> This is normal when offline—the YouTube connector automatically switches to `LIVE` as soon as an active broadcast is detected on your channel URL.

* **🤖 AI only replies with fallback lines:** Verify Ollama is running at `http://localhost:11434` and that `OLLAMA_MODEL` matches an installed model (`ollama list`).
* **🔇 No TTS audio on Linux:** Install `ffmpeg` and verify that `pw-play` (PipeWire) or `paplay` (PulseAudio) is available in your system `PATH`.
* **🎵 TikTok fails to connect:** Make sure your TikTok account is currently live and that `TIKTOK_USERNAME` is spelled accurately.

---

## 📄 License

Distributed under the **MIT License**. See [`LICENSE`](LICENSE) for more details.

<div align="center">
  <br />
  <sub>Built with 💖, Python, and a healthy dose of robotic sarcasm.</sub>
</div>
