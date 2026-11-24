import os
import re
import math
import wave
import struct
import random
import shutil
import socket
import hashlib
import textwrap
import subprocess
import time
import queue
import asyncio
import threading
from collections import deque
import requests
import pygame
from PIL import Image, ImageDraw, ImageFont
from TikTokLive import TikTokLiveClient
from TikTokLive.events import (
    ConnectEvent,
    DisconnectEvent,
    CommentEvent,
    GiftEvent,
)

# ================= CONFIGURACIÓN GENERAL =================
HOST_NAME = "TuNombre"                                           # Tu nombre o apodo (la IA lo usará en sus respuestas)
TIKTOK_USERNAME = "@tu_usuario_tiktok"                           # Tu cuenta de TikTok
TWITCH_CHANNEL = "tu_canal_twitch"                               # Tu cuenta de Twitch
YOUTUBE_CHANNEL_URL = "https://www.youtube.com/@tu_canal_yt"    # Tu canal de YouTube

WIDTH, HEIGHT = 540, 960                                         # Formato vertical / panel lateral OBS
FPS = 60
MAX_CHAT_HISTORY = 14                                            # Mensajes visibles en memoria

ASSETS_DIR = "assets_dev_stream"
TTS_DIR = os.path.join(ASSETS_DIR, "tts")

# Configuración de Ollama (temperatura alta y penalización para máxima variedad)
OLLAMA_URL = "http://localhost:11434/api/generate"
OLLAMA_MODEL = "llama3.2:latest"
OLLAMA_TEMPERATURE = 1.18
OLLAMA_TOP_P = 0.95
OLLAMA_TOP_K = 70
OLLAMA_REPEAT_PENALTY = 1.38

# Paleta estilo terminal cyber-rose (toque femenino elegante)
BG_DARK = (16, 13, 24)
HEADER_BG = (24, 18, 36)
CARD_BG = (28, 22, 40)
CARD_BORDER = (68, 52, 92)
AI_BG = (36, 22, 46)
AI_ACCENT = (255, 105, 185)         # Rosa neón principal
AI_SOFT = (255, 205, 232)           # Rosa suave para subtítulos activos
TITLE_ACCENT = (245, 160, 255)      # Lavanda brillante
TEXT_MAIN = (242, 238, 250)
TEXT_MUTED = (165, 152, 185)

COLOR_TIKTOK = (255, 55, 125)
COLOR_TWITCH = (178, 120, 255)
COLOR_YOUTUBE = (255, 68, 82)
COLOR_ONLINE = (85, 245, 155)
COLOR_OFFLINE = (240, 95, 115)
COLOR_GIFT = (255, 215, 95)
CHROMA_GREEN = (0, 255, 0)

# ================= ESTADO GLOBAL =================
chat_messages = deque(maxlen=MAX_CHAT_HISTORY)
state_lock = threading.Lock()

tiktok_connected = False
twitch_connected = False
youtube_connected = False

use_chroma = False
tts_muted = False
sounds = {}
narrator = None

PLATFORM_META = {
    "TT": {"label": "TIKTOK", "name": "TikTok", "color": COLOR_TIKTOK},
    "TW": {"label": "TWITCH", "name": "Twitch", "color": COLOR_TWITCH},
    "YT": {"label": "YOUTUBE", "name": "YouTube", "color": COLOR_YOUTUBE},
}


# ================= UTILIDADES DE TEXTO Y SONIDO =================
def wrap_text(text, max_chars=44, max_lines=4):
    lines = textwrap.wrap(text.strip(), width=max_chars, break_long_words=True)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        lines[-1] = lines[-1][: max(0, max_chars - 3)] + "..."
    return lines or [""]


def save_wav(filename, samples, sample_rate=44100):
    filepath = os.path.join(ASSETS_DIR, filename)
    if os.path.exists(filepath):
        return filepath
    with wave.open(filepath, "w") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        frames = bytearray()
        for s in samples:
            clipped = max(-1.0, min(1.0, s))
            frames.extend(struct.pack("<h", int(clipped * 32767)))
        wav_file.writeframes(frames)
    return filepath


def setup_assets():
    os.makedirs(ASSETS_DIR, exist_ok=True)
    os.makedirs(TTS_DIR, exist_ok=True)
    sr = 44100

    # Sonido cristalino y sutil al entrar un comentario
    ping_path = os.path.join(ASSETS_DIR, "chat_ping_fem.wav")
    if not os.path.exists(ping_path):
        dur = 0.16
        samples = []
        for i in range(int(sr * dur)):
            t = i / sr
            freq = 987.77 if t < 0.07 else 1318.51
            env = (1.0 - t / dur) ** 1.3
            val = math.sin(2 * math.pi * freq * t) * 0.7 + math.sin(4 * math.pi * freq * t) * 0.2
            samples.append(val * env * 0.42)
        save_wav("chat_ping_fem.wav", samples, sr)

    # Arpegio brillante para regalos / SuperChats / Bits
    gift_path = os.path.join(ASSETS_DIR, "chat_gift_fem.wav")
    if not os.path.exists(gift_path):
        dur = 0.38
        notes = [659.25, 830.61, 987.77, 1318.51]
        samples = []
        for i in range(int(sr * dur)):
            t = i / sr
            idx = min(len(notes) - 1, int((t / dur) * len(notes)))
            f = notes[idx]
            env = (1.0 - t / dur) ** 0.7
            val = math.sin(2 * math.pi * f * t) * 0.75 + math.sin(4 * math.pi * f * t) * 0.25
            samples.append(val * env * 0.55)
        save_wav("chat_gift_fem.wav", samples, sr)


class HybridSound:
    def __init__(self, filepath, volume=0.45, backend="none", pg_sound=None):
        self.filepath = filepath
        self.volume = volume
        self.backend = backend
        self.pg_sound = pg_sound

    def play(self):
        if self.backend == "pygame" and self.pg_sound:
            self.pg_sound.play()
        elif self.backend in ("pw-play", "paplay", "aplay", "ffplay"):
            try:
                if self.backend == "pw-play":
                    cmd = ["pw-play", f"--volume={self.volume:.2f}", self.filepath]
                elif self.backend == "paplay":
                    cmd = ["paplay", f"--volume={int(self.volume * 65536)}", self.filepath]
                elif self.backend == "ffplay":
                    cmd = ["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet", self.filepath]
                else:
                    cmd = ["aplay", "-q", self.filepath]
                subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except Exception:
                pass


class AudioManager:
    def __init__(self):
        self.backend = "none"
        try:
            pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=512)
            self.backend = "pygame"
            print("[Audio] Usando pygame.mixer.")
        except Exception:
            for tool in ("pw-play", "paplay", "ffplay", "aplay"):
                if shutil.which(tool):
                    self.backend = tool
                    print(f"[Audio] Usando '{tool}' nativo de Linux.")
                    break

    def load_sound(self, filepath, volume=0.45):
        if self.backend == "pygame":
            snd = pygame.mixer.Sound(filepath)
            snd.set_volume(volume)
            return HybridSound(filepath, volume, "pygame", snd)
        return HybridSound(filepath, volume, self.backend)


# ================= MOTOR DE FUENTES CON SOMBRA =================
class HybridFont:
    def __init__(self, name, size, bold=True):
        self.use_pg = False
        try:
            self.pg_font = pygame.font.SysFont(name, size, bold=bold)
            self.use_pg = True
        except Exception:
            self.pil_font = self._load_pil_font(size)

    def _load_pil_font(self, size):
        candidates = [
            "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/TTF/LiberationSans-Bold.ttf",
            "/usr/share/fonts/noto/NotoSans-Bold.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        ]
        for path in candidates:
            if os.path.exists(path):
                try:
                    return ImageFont.truetype(path, size)
                except Exception:
                    pass
        return ImageFont.load_default()

    def render(self, text, color, shadow_color=(8, 6, 14), offset=1):
        if self.use_pg:
            fg = self.pg_font.render(text, True, color)
            if not shadow_color:
                return fg
            sh = self.pg_font.render(text, True, shadow_color)
            surf = pygame.Surface(
                (fg.get_width() + offset * 2, fg.get_height() + offset * 2),
                pygame.SRCALPHA,
            )
            surf.blit(sh, (offset * 2, offset * 2))
            surf.blit(fg, (0, 0))
            return surf

        bbox = self.pil_font.getbbox(text)
        w = max(1, bbox[2] - bbox[0] + 6)
        h = max(1, bbox[3] - bbox[1] + 6)
        img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        if shadow_color:
            draw.text(
                (-bbox[0] + 2 + offset, -bbox[1] + 2 + offset),
                text,
                font=self.pil_font,
                fill=(*shadow_color, 230),
            )
        draw.text((-bbox[0] + 2, -bbox[1] + 2), text, font=self.pil_font, fill=(*color, 255))
        return pygame.image.fromstring(img.tobytes(), img.size, img.mode)


# ================= NARRADOR TTS + IA SARCÁSTICA FEMENINA TIPO BENDER =================
class BenderinaNarrator:
    def __init__(self):
        os.makedirs(TTS_DIR, exist_ok=True)
        self.tts_q = queue.Queue()
        self.llm_q = queue.Queue()
        self.recent_replies = deque(maxlen=6)

        self.speaking = False
        self.current_subtitle = ""
        self.last_ai_reply = "Aquí estoy, divina y pulida, esperando a que el chat escriba algo entretenido..."
        self.last_user_addressed = ""
        self.last_llm_time = 0.0

        self.has_ffmpeg = shutil.which("ffmpeg") is not None
        self.has_ffplay = shutil.which("ffplay") is not None
        self.has_pwplay = shutil.which("pw-play") is not None
        self.has_paplay = shutil.which("paplay") is not None
        self.has_mpv = shutil.which("mpv") is not None
        self.has_espeak = shutil.which("espeak-ng") or shutil.which("espeak")

        threading.Thread(target=self._tts_worker, daemon=True).start()
        threading.Thread(target=self._ollama_worker, daemon=True).start()

    def say(self, text, display_reply=None, target_user="", priority=False):
        if not text:
            return
        if priority:
            while not self.tts_q.empty():
                try:
                    self.tts_q.get_nowait()
                except Exception:
                    break
        if self.tts_q.qsize() < 8:
            self.tts_q.put((text, display_reply or text, target_user))

    def handle_comment(self, platform, nickname, comment, is_gift=False):
        now = time.time()
        if self.llm_q.qsize() >= 5:
            return
        if not is_gift and (now - self.last_llm_time < 1.2):
            return
        self.last_llm_time = now
        self.llm_q.put((platform, nickname, comment, is_gift))

    def _ollama_worker(self):
        # Ángulos rotativos: cinismo de Bender + actitud femenina de diva sarcástica
        sarcasm_angles = [
            "presumiendo tu glamour metálico y quejándote de que interrumpen tu rutina de pulido",
            "negándote a tocar el teclado para no arruinarte las uñas de titanio",
            "burlándote con dulzura venenosa y sarcasmo de los bugs y puntos y coma del espectador",
            "actuando como una diva robótica inalcanzable y superior frente a los humanos del chat",
            f"recordando con actitud floja y descarada que {HOST_NAME} es quien trabaja mientras tú solo luces espectacular",
            "usando coquetería irónica para batear la pregunta sin ayudar absolutamente en nada",
            "presumiendo que armarías tu propio stream con más glamour, juegos de azar y cero errores de sintaxis",
            "dando un comentario ácido y elegante como una reina cibernética harta del código espagueti",
            "insinuando con tono de reina dramática que leer la documentación no les quitaría lo guapos",
            "presumiendo tu brillante chasis de lujo mientras te ríes de que los humanos dependan de café",
        ]

        fallbacks = [
            f"Ay, corazón, no me voy a romper las uñas metálicas arreglando eso. Pregúntale a {HOST_NAME}.",
            "Qué lindo tu mensaje, cariño, lástima que mi chip de empatía está en el spa.",
            "Soy demasiado fabulosa y de acero inoxidable para resolver dudas gratis, suerte con ese bug.",
            "Interrumpen mi pulido de cromo para esto... mejor pongan atención al tutorial, amores.",
            "Besa mi reluciente chasis de reina metálica, yo vine a brillar, no a compilar código.",
            "Fascinante aporte, cielo. Lo guardaré justo donde guardo las ganas de hacerte la tarea.",
        ]

        while True:
            platform, nickname, comment, is_gift = self.llm_q.get()
            clean_nick = re.sub(r"[_]+", " ", nickname[:18]).strip() or "corazón"
            plat_name = PLATFORM_META.get(platform, {}).get("name", "el chat")
            angle = random.choice(sarcasm_angles)

            history_block = ""
            if self.recent_replies:
                joined = "\n".join(f"- {r}" for r in self.recent_replies)
                history_block = (
                    f"\nIMPORTANTE: NO repitas chistes, palabras clave ni estructuras parecidas a tus respuestas recientes:\n"
                    f"{joined}\n"
                )

            gift_context = (
                "El espectador además mandó un regalo o donación, así que agradécelo como diva caprichosa y ambiciosa que ama el lujo."
                if is_gift
                else f"NO resuelvas su duda técnica ni des una explicación útil; solo respóndele con sarcasmo femenino ingenioso y déjale el trabajo real a {HOST_NAME}."
            )

            prompt = (
                f"Eres Benderina, una robot co-anfitriona en el directo de programación e informática de {HOST_NAME}. "
                f"Tienes el sarcasmo, ego gigante, cinismo y flojera de Bender Rodríguez de Futurama, pero con un toque femenino, "
                f"coqueto, ácido y de diva inalcanzable (hablas siempre en femenino en español latino natural). "
                f"El espectador '{clean_nick}' escribió en {plat_name}: '{comment}'. "
                f"{gift_context} "
                f"Enfoca tu comentario {angle}. "
                f"{history_block}"
                f"Reglas estrictas:\n"
                f"1. Responde en UNA o DOS frases cortas (máximo 22 palabras).\n"
                f"2. Habla siempre en femenino sobre ti misma (ej. 'ocupada', 'fabulosa', 'reina').\n"
                f"3. Sin comillas, sin asteriscos, sin emojis y sin prefijos como 'Benderina:'.\n"
                f"4. Sé creativa, mordaz y totalmente distinta cada vez."
            )

            ai_reply = None
            try:
                resp = requests.post(
                    OLLAMA_URL,
                    json={
                        "model": OLLAMA_MODEL,
                        "prompt": prompt,
                        "stream": False,
                        "options": {
                            "temperature": OLLAMA_TEMPERATURE,
                            "top_p": OLLAMA_TOP_P,
                            "top_k": OLLAMA_TOP_K,
                            "repeat_penalty": OLLAMA_REPEAT_PENALTY,
                            "repeat_last_n": 128,
                            "num_predict": 60,
                            "seed": random.randint(1, 9999999),
                        },
                    },
                    timeout=10,
                )
                if resp.status_code == 200:
                    raw = resp.json().get("response", "").strip()
                    raw = raw.replace('"', "").replace("*", "").split("\n")[0].strip()
                    raw = re.sub(r"^(Benderina|Bender|IA|Bot)\s*:\s*", "", raw, flags=re.IGNORECASE).strip()
                    if len(raw) >= 4:
                        ai_reply = raw
            except Exception as e:
                print(f"[Ollama Aviso] {e}")

            if not ai_reply:
                ai_reply = random.choice(fallbacks)

            self.recent_replies.append(ai_reply)

            spoken_text = f"{clean_nick} en {plat_name} dice: {comment}. {ai_reply}"
            print(f"[Benderina IA] -> @{nickname}: {ai_reply}")
            self.say(spoken_text, display_reply=ai_reply, target_user=f"@{nickname[:16]}")

    def _play_audio_file(self, mp3_path):
        wav_path = mp3_path.replace(".mp3", ".wav")
        if self.has_ffmpeg and not os.path.exists(wav_path):
            subprocess.run(
                ["ffmpeg", "-y", "-i", mp3_path, "-ar", "44100", "-ac", "1", wav_path],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )

        if os.path.exists(wav_path) and self.has_pwplay:
            subprocess.run(["pw-play", "--volume=1.0", wav_path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        elif os.path.exists(wav_path) and self.has_paplay:
            subprocess.run(["paplay", wav_path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        elif self.has_ffplay:
            subprocess.run(
                ["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet", mp3_path],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        elif self.has_mpv:
            subprocess.run(["mpv", "--no-video", "--really-quiet", mp3_path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def _tts_worker(self):
        while True:
            spoken_text, display_reply, target_user = self.tts_q.get()
            with state_lock:
                self.last_ai_reply = display_reply
                self.last_user_addressed = target_user

            if tts_muted:
                self.speaking = True
                self.current_subtitle = display_reply
                time.sleep(2.2)
                self.speaking = False
                continue

            self.speaking = True
            self.current_subtitle = display_reply
            try:
                chunks = [spoken_text[i : i + 180] for i in range(0, len(spoken_text), 180)]
                for chunk in chunks:
                    if tts_muted:
                        break
                    text_hash = hashlib.md5(chunk.encode("utf-8")).hexdigest()[:12]
                    mp3_path = os.path.join(TTS_DIR, f"tts_{text_hash}.mp3")

                    if not os.path.exists(mp3_path):
                        url = "https://translate.googleapis.com/translate_tts"
                        params = {"client": "gtx", "ie": "UTF-8", "tl": "es-MX", "dt": "t", "q": chunk}
                        headers = {"User-Agent": "Mozilla/5.0"}
                        resp = requests.get(url, params=params, headers=headers, timeout=6)
                        if resp.status_code == 200 and len(resp.content) > 400:
                            with open(mp3_path, "wb") as f:
                                f.write(resp.content)

                    if os.path.exists(mp3_path):
                        self._play_audio_file(mp3_path)
                    elif self.has_espeak:
                        # Voz femenina de respaldo en espeak-ng
                        subprocess.run(
                            [self.has_espeak, "-v", "es+f3", "-p", "62", chunk],
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL,
                        )
            except Exception as e:
                print(f"[TTS Aviso] {e}")
            finally:
                time.sleep(0.2)
                self.speaking = False


# ================= REGISTRO UNIFICADO DE COMENTARIOS =================
def push_chat_message(platform, nickname, text, is_gift=False):
    clean_text = text.strip()
    if not clean_text:
        return

    meta = PLATFORM_META.get(platform, PLATFORM_META["TT"])
    timestamp = time.strftime("%H:%M")

    print(f"[{meta['label']}] @{nickname}: {clean_text}")

    with state_lock:
        chat_messages.append(
            {
                "platform": platform,
                "nickname": nickname[:20],
                "text": clean_text[:220],
                "time": timestamp,
                "is_gift": is_gift,
                "created_at": time.time(),
            }
        )

    if is_gift and "gift" in sounds:
        sounds["gift"].play()
    elif "ping" in sounds:
        sounds["ping"].play()

    if narrator:
        narrator.handle_comment(platform, nickname, clean_text, is_gift=is_gift)


# ================= CLIENTE YOUTUBE LIVE =================
def _extract_yt_continuation(chat_cont):
    for c in chat_cont.get("continuations", []):
        for key in (
            "invalidationContinuationData",
            "timedContinuationData",
            "reloadContinuationData",
            "liveChatReplayContinuationData",
        ):
            if key in c and "continuation" in c[key]:
                return c[key]["continuation"]
    return None


def _get_youtube_live_chat_session(session, channel_url):
    live_url = channel_url.rstrip("/") + "/live"
    resp = session.get(live_url, timeout=10)
    html = resp.text

    if '"isLive":true' not in html and '"isLiveNow":true' not in html and '"liveChatRenderer"' not in html:
        return None, None, None

    vid_match = (
        re.search(r'"videoDetails"\s*:\s*\{[^}]*?"videoId"\s*:\s*"([a-zA-Z0-9_-]{11})"', html)
        or re.search(r'rel="canonical"\s+href="https://www\.youtube\.com/watch\?v=([a-zA-Z0-9_-]{11})"', html)
        or re.search(r'"videoId"\s*:\s*"([a-zA-Z0-9_-]{11})"', html)
    )
    if not vid_match:
        return None, None, None

    video_id = vid_match.group(1)
    chat_page_url = f"https://www.youtube.com/live_chat?v={video_id}"
    chat_html = session.get(chat_page_url, timeout=10).text

    api_key_match = re.search(r'"INNERTUBE_API_KEY"\s*:\s*"([^"]+)"', chat_html)
    if not api_key_match:
        return None, None, None
    api_key = api_key_match.group(1)

    all_reload_tokens = re.findall(
        r'"reloadContinuationData"\s*:\s*\{\s*"continuation"\s*:\s*"([^"]+)"',
        chat_html,
    )
    if len(all_reload_tokens) >= 2:
        continuation = all_reload_tokens[1]  # Modo "Todos los mensajes"
    elif all_reload_tokens:
        continuation = all_reload_tokens[0]
    else:
        cont_match = re.search(r'"continuation"\s*:\s*"([^"]+)"', chat_html)
        continuation = cont_match.group(1) if cont_match else None

    return video_id, api_key, continuation


def start_youtube_thread():
    global youtube_connected
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
            "Accept-Language": "es-MX,es;q=0.9,en;q=0.8",
            "Referer": "https://www.youtube.com/",
        }
    )
    session.cookies.set("CONSENT", "YES+cb", domain=".youtube.com")

    seen_yt_messages = deque(maxlen=1500)

    while True:
        try:
            video_id, api_key, continuation = _get_youtube_live_chat_session(session, YOUTUBE_CHANNEL_URL)
            if not api_key or not continuation:
                if youtube_connected:
                    print("[YouTube LIVE] Directo finalizado. Buscando nueva transmisión...")
                youtube_connected = False
                time.sleep(10)
                continue

            youtube_connected = True
            print(f"[YouTube LIVE] Conectado al chat en vivo (Video ID: {video_id})")
            first_poll = True

            while continuation:
                chat_url = f"https://www.youtube.com/youtubei/v1/live_chat/get_live_chat?key={api_key}"
                payload = {
                    "context": {
                        "client": {
                            "clientName": "WEB",
                            "clientVersion": "2.20240726.00.00",
                            "hl": "es",
                            "gl": "MX",
                        }
                    },
                    "continuation": continuation,
                }
                r_chat = session.post(chat_url, json=payload, timeout=10)
                if r_chat.status_code != 200:
                    break

                data = r_chat.json()
                chat_cont = data.get("continuationContents", {}).get("liveChatContinuation", {})
                if not chat_cont:
                    break

                continuation = _extract_yt_continuation(chat_cont)
                actions = chat_cont.get("actions", [])

                for act in actions:
                    item = act.get("addChatItemAction", {}).get("item", {})
                    renderer = (
                        item.get("liveChatTextMessageRenderer")
                        or item.get("liveChatPaidMessageRenderer")
                    )
                    if not renderer:
                        continue

                    msg_id = renderer.get("id")
                    if not msg_id or msg_id in seen_yt_messages:
                        continue
                    seen_yt_messages.append(msg_id)

                    if first_poll:
                        continue

                    nick = renderer.get("authorName", {}).get("simpleText", "YouTuber")
                    runs = renderer.get("message", {}).get("runs", [])
                    msg_parts = []
                    for run in runs:
                        if "text" in run:
                            msg_parts.append(run["text"])
                        elif "emoji" in run:
                            shortcuts = run["emoji"].get("shortcuts", [""])
                            msg_parts.append(shortcuts[0] if shortcuts else "")
                    raw_msg = "".join(msg_parts).strip()
                    is_superchat = "liveChatPaidMessageRenderer" in item

                    if is_superchat and not raw_msg:
                        raw_msg = "Envió un Super Chat"

                    push_chat_message("YT", nick, raw_msg, is_gift=is_superchat)

                first_poll = False
                time.sleep(1.3)

        except Exception as e:
            print(f"[YouTube Aviso] {e}")
        finally:
            youtube_connected = False
            time.sleep(8)


# ================= CLIENTE TWITCH CHAT =================
def start_twitch_thread():
    global twitch_connected
    channel = TWITCH_CHANNEL.lower().strip().lstrip("@#")

    while True:
        sock = None
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(240)
            sock.connect(("irc.chat.twitch.tv", 6667))

            sock.sendall(b"CAP REQ :twitch.tv/tags twitch.tv/commands\r\n")
            sock.sendall(b"PASS SCHMOOPIIE\r\n")
            anon_nick = f"justinfan{random.randint(10000, 99999)}"
            sock.sendall(f"NICK {anon_nick}\r\n".encode("utf-8"))
            sock.sendall(f"JOIN #{channel}\r\n".encode("utf-8"))

            buffer = ""
            while True:
                data = sock.recv(4096).decode("utf-8", errors="ignore")
                if not data:
                    break
                buffer += data
                lines = buffer.split("\r\n")
                buffer = lines.pop()

                for line in lines:
                    if not line:
                        continue
                    if line.startswith("PING"):
                        sock.sendall(b"PONG :tmi.twitch.tv\r\n")
                        continue
                    if f"JOIN #{channel}" in line or " 366 " in line:
                        if not twitch_connected:
                            twitch_connected = True
                            print(f"[Twitch LIVE] Conectado al chat #{channel}")
                    if "PRIVMSG" in line:
                        tags = {}
                        rest = line
                        if rest.startswith("@"):
                            tag_part, rest = rest.split(" ", 1)
                            for item in tag_part[1:].split(";"):
                                if "=" in item:
                                    k, v = item.split("=", 1)
                                    tags[k] = v

                        prefix, msg_part = rest.split("PRIVMSG", 1)
                        raw_msg = msg_part.split(" :", 1)[1].strip() if " :" in msg_part else ""
                        fallback_user = prefix.split("!")[0].lstrip(":") if "!" in prefix else "TwitchUser"
                        nick = tags.get("display-name") or fallback_user
                        bits = int(tags.get("bits", "0") or 0)

                        if bits > 0 and not raw_msg:
                            raw_msg = f"Envió {bits} bits"

                        push_chat_message("TW", nick, raw_msg, is_gift=(bits > 0))

        except Exception as e:
            print(f"[Twitch Reintentando] {e}")
        finally:
            twitch_connected = False
            if sock:
                try:
                    sock.close()
                except Exception:
                    pass
            time.sleep(4)


# ================= CLIENTE TIKTOK LIVE =================
def start_tiktok_thread():
    global tiktok_connected
    while True:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        client = TikTokLiveClient(unique_id=TIKTOK_USERNAME)

        @client.on(ConnectEvent)
        async def on_connect(event: ConnectEvent):
            global tiktok_connected
            tiktok_connected = True
            print(f"[TikTok LIVE] Conectado en tiempo real a @{event.unique_id}")

        @client.on(DisconnectEvent)
        async def on_disconnect(event: DisconnectEvent):
            global tiktok_connected
            tiktok_connected = False
            print("[TikTok LIVE] Desconectado. Reintentando...")

        @client.on(CommentEvent)
        async def on_comment(event: CommentEvent):
            if event.user is None:
                return
            nick = event.user.nickname or event.user.unique_id
            raw_comment = (event.comment or "").strip()
            push_chat_message("TT", nick, raw_comment, is_gift=False)

        @client.on(GiftEvent)
        async def on_gift(event: GiftEvent):
            if event.user is None or event.gift is None:
                return
            if getattr(event, "streaking", False):
                return
            nick = event.user.nickname or event.user.unique_id
            gift_name = getattr(event.gift, "name", "un regalo")
            count = getattr(event, "repeat_count", 1) or 1
            push_chat_message("TT", nick, f"Envió {count}x {gift_name}", is_gift=True)

        try:
            client.run()
        except Exception:
            tiktok_connected = False
            time.sleep(6)


# ================= RENDERIZADO DE INTERFAZ =================
def draw_status_pill(surface, x, y, label, connected, accent_color, font_tiny):
    w, h = 158, 28
    bg = (30, 22, 42) if connected else (34, 22, 32)
    border = accent_color if connected else (85, 68, 102)
    pygame.draw.rect(surface, bg, (x, y, w, h), border_radius=12)
    pygame.draw.rect(surface, border, (x, y, w, h), 2, border_radius=12)

    dot_color = COLOR_ONLINE if connected else COLOR_OFFLINE
    pygame.draw.circle(surface, dot_color, (x + 14, y + h // 2), 5)

    state_txt = "LIVE" if connected else "BUSCANDO"
    txt = font_tiny.render(f"{label}: {state_txt}", TEXT_MAIN if connected else TEXT_MUTED)
    surface.blit(txt, (x + 26, y + 7))


def draw_chat_feed(surface, top_y, bottom_y, font_user, font_msg, font_tiny):
    with state_lock:
        msgs = list(chat_messages)

    if not msgs:
        empty_1 = font_user.render("ESPERANDO COMENTARIOS EN VIVO...", AI_SOFT)
        empty_2 = font_tiny.render("Escuchando YouTube, Twitch y TikTok en tiempo real", TEXT_MUTED)
        surface.blit(empty_1, empty_1.get_rect(center=(WIDTH // 2, (top_y + bottom_y) // 2 - 12)))
        surface.blit(empty_2, empty_2.get_rect(center=(WIDTH // 2, (top_y + bottom_y) // 2 + 16)))
        return

    cursor_y = bottom_y - 10
    card_x = 16
    card_w = WIDTH - 32

    for msg in reversed(msgs):
        meta = PLATFORM_META.get(msg["platform"], PLATFORM_META["TT"])
        accent = COLOR_GIFT if msg["is_gift"] else meta["color"]
        wrapped = wrap_text(msg["text"], max_chars=43, max_lines=4)

        card_h = 34 + len(wrapped) * 20 + 10
        card_top = cursor_y - card_h
        if card_top < top_y:
            break

        pygame.draw.rect(surface, CARD_BG, (card_x, card_top, card_w, card_h), border_radius=12)
        pygame.draw.rect(
            surface,
            accent,
            (card_x, card_top, 6, card_h),
            border_top_left_radius=12,
            border_bottom_left_radius=12,
        )
        pygame.draw.rect(surface, CARD_BORDER, (card_x, card_top, card_w, card_h), 1, border_radius=12)

        badge_surf = font_tiny.render(meta["label"], (255, 255, 255), shadow_color=None)
        badge_w = badge_surf.get_width() + 12
        pygame.draw.rect(surface, meta["color"], (card_x + 14, card_top + 8, badge_w, 18), border_radius=6)
        surface.blit(badge_surf, (card_x + 20, card_top + 10))

        nick_surf = font_user.render(f"@{msg['nickname']}", accent)
        surface.blit(nick_surf, (card_x + 22 + badge_w, card_top + 8))

        time_surf = font_tiny.render(msg["time"], TEXT_MUTED)
        surface.blit(time_surf, (card_x + card_w - time_surf.get_width() - 12, card_top + 10))

        line_y = card_top + 34
        for line in wrapped:
            l_surf = font_msg.render(line, COLOR_GIFT if msg["is_gift"] else TEXT_MAIN)
            surface.blit(l_surf, (card_x + 16, line_y))
            line_y += 20

        cursor_y = card_top - 10


def draw_benderina_panel(surface, t_sec, font_sub, font_msg):
    panel_x, panel_y = 16, HEIGHT - 196
    panel_w, panel_h = WIDTH - 32, 152

    with state_lock:
        reply_text = narrator.last_ai_reply if narrator else ""
        target_user = narrator.last_user_addressed if narrator else ""
        is_speaking = narrator.speaking if narrator else False

    border_col = AI_ACCENT if is_speaking else (110, 65, 130)
    pygame.draw.rect(surface, AI_BG, (panel_x, panel_y, panel_w, panel_h), border_radius=14)
    pygame.draw.rect(surface, border_col, (panel_x, panel_y, panel_w, panel_h), 2, border_radius=14)

    status_label = "HABLANDO..." if is_speaking else ("SILENCIADA" if tts_muted else "EN ESPERA")
    header_txt = f"BENDERINA IA  |  {status_label}"
    if target_user:
        header_txt += f"  ->  {target_user}"

    h_surf = font_sub.render(header_txt, AI_ACCENT)
    surface.blit(h_surf, (panel_x + 14, panel_y + 10))

    # Ondas suaves de voz en tono rosa neón
    bar_base_x = panel_x + panel_w - 64
    for i in range(6):
        if is_speaking and not tts_muted:
            amp = 4 + int(abs(math.sin(t_sec * 10.5 + i * 0.85)) * 14)
        else:
            amp = 3
        bar_col = AI_ACCENT if (is_speaking and i % 2 == 0) else (TITLE_ACCENT if is_speaking else TEXT_MUTED)
        pygame.draw.rect(
            surface,
            bar_col,
            (bar_base_x + i * 8, panel_y + 22 - amp // 2, 5, amp),
            border_radius=3,
        )

    pygame.draw.line(
        surface,
        (82, 54, 102),
        (panel_x + 12, panel_y + 36),
        (panel_x + panel_w - 12, panel_y + 36),
        1,
    )

    lines = wrap_text(reply_text, max_chars=44, max_lines=5)
    ly = panel_y + 46
    for line in lines:
        ls = font_msg.render(line, AI_SOFT if is_speaking else TEXT_MAIN)
        surface.blit(ls, (panel_x + 14, ly))
        ly += 20


# ================= BUCLE PRINCIPAL =================
def main():
    global use_chroma, tts_muted, narrator

    setup_assets()
    pygame.display.init()
    try:
        pygame.font.init()
    except Exception:
        pass

    audio = AudioManager()
    sounds["ping"] = audio.load_sound(os.path.join(ASSETS_DIR, "chat_ping_fem.wav"), 0.35)
    sounds["gift"] = audio.load_sound(os.path.join(ASSETS_DIR, "chat_gift_fem.wav"), 0.55)

    narrator = BenderinaNarrator()

    screen = pygame.display.set_mode((WIDTH, HEIGHT))
    pygame.display.set_caption("Chat Multiplataforma Dev Live + Benderina IA (YT / Twitch / TikTok)")
    clock = pygame.time.Clock()

    font_title = HybridFont("DejaVu Sans", 19, bold=True)
    font_sub = HybridFont("DejaVu Sans", 13, bold=True)
    font_user = HybridFont("DejaVu Sans", 13, bold=True)
    font_msg = HybridFont("DejaVu Sans", 14, bold=False)
    font_tiny = HybridFont("DejaVu Sans", 11, bold=True)

    # Iniciar búsqueda activa en YouTube, Twitch y TikTok
    threading.Thread(target=start_youtube_thread, daemon=True).start()
    threading.Thread(target=start_twitch_thread, daemon=True).start()
    threading.Thread(target=start_tiktok_thread, daemon=True).start()

    test_comments = [
        ("YT", "dev_novato", f"Hola {HOST_NAME}, por qué no me compila mi script en Python?"),
        ("TW", "linux_fan", "Qué distro de Linux estás usando hoy?"),
        ("TT", "carlos_js", "Me puedes hacer mi tarea de bases de datos porfa?"),
        ("YT", "maria_code", "Saludos desde Guadalajara! Excelente tutorial"),
        ("TW", "bug_hunter", "Me sale NullPointerException y no sé qué rompí"),
    ]

    running = True
    while running:
        t_sec = pygame.time.get_ticks() / 1000.0

        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                running = False
            elif ev.type == pygame.KEYDOWN:
                if ev.key == pygame.K_c:
                    use_chroma = not use_chroma
                    print(f"[OBS] Chroma verde: {'ACTIVADO' if use_chroma else 'DESACTIVADO'}")
                elif ev.key == pygame.K_m:
                    tts_muted = not tts_muted
                    print(f"[TTS] Voz Benderina: {'SILENCIADA' if tts_muted else 'ACTIVA'}")
                elif ev.key == pygame.K_l:
                    with state_lock:
                        chat_messages.clear()
                    print("[Chat] Pantalla limpiada.")
                elif ev.key == pygame.K_t:
                    plat, usr, txt = random.choice(test_comments)
                    push_chat_message(plat, usr, txt, is_gift=False)

        if use_chroma:
            screen.fill(CHROMA_GREEN)
        else:
            screen.fill(BG_DARK)

        # Encabezado superior con línea rosa neón
        pygame.draw.rect(screen, HEADER_BG, (0, 0, WIDTH, 94))
        pygame.draw.line(screen, AI_ACCENT, (0, 94), (WIDTH, 94), 2)

        title_surf = font_title.render("CHAT EN VIVO  |  DEV + BENDERINA IA", TITLE_ACCENT)
        screen.blit(title_surf, title_surf.get_rect(center=(WIDTH // 2, 26)))

        # Indicadores activos de conexión (YouTube, Twitch y TikTok)
        draw_status_pill(screen, 16, 52, "YT", youtube_connected, COLOR_YOUTUBE, font_tiny)
        draw_status_pill(screen, 191, 52, "TW", twitch_connected, COLOR_TWITCH, font_tiny)
        draw_status_pill(screen, 366, 52, "TT", tiktok_connected, COLOR_TIKTOK, font_tiny)

        # Feed de mensajes en tiempo real
        draw_chat_feed(
            screen,
            top_y=104,
            bottom_y=HEIGHT - 208,
            font_user=font_user,
            font_msg=font_msg,
            font_tiny=font_tiny,
        )

        # Panel inferior de Benderina IA
        draw_benderina_panel(screen, t_sec, font_sub, font_msg)

        # Cintillo inferior de atajos
        footer_txt = "[C] Chroma OBS  |  [T] Probar IA  |  [M] Mute TTS  |  [L] Limpiar"
        f_surf = font_tiny.render(footer_txt, TEXT_MUTED)
        screen.blit(f_surf, f_surf.get_rect(center=(WIDTH // 2, HEIGHT - 20)))

        pygame.display.flip()
        clock.tick(FPS)

    pygame.quit()


if __name__ == "__main__":
    main()
