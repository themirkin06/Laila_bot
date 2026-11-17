"""Temporary Turkish voice messages using the free Edge TTS endpoint."""
import asyncio
import logging
import os
import tempfile
import time

import edge_tts


VOICE_PROFILES = {
    "leyla": "tr-TR-EmelNeural",
    "merve": "tr-TR-EmelNeural",
    "asli": "tr-TR-EmelNeural",
    "dilek": "tr-TR-EmelNeural",
    "ece": "tr-TR-EmelNeural",
    "ayse": "tr-TR-EmelNeural",
    "dondu": "tr-TR-EmelNeural",
}
# Voice pitch/rate nudges provide distinct character delivery with Turkish voices.
VOICE_STYLE = {
    "leyla": ("-5%", "+0Hz"), "merve": ("+8%", "+2Hz"),
    "asli": ("+0%", "+0Hz"), "dilek": ("-8%", "-1Hz"),
    "ece": ("-3%", "+1Hz"), "ayse": ("+2%", "+0Hz"),
    "dondu": ("-10%", "-2Hz"),
}
# Edge-TTS exposes rate and pitch controls but not per-word acting for this
# Turkish neural voice. Emotion changes stay intentionally subtle.
EMOTION_STYLE = {
    "bright": (5, 1), "sad": (-7, -1), "angry": (3, -1),
    "flirty": (-2, 2), "calm": (-3, -1),
}
EMOTION_CUES = {
    "bright": ("sevindim", "harika", "çok güzel", "yaşasın", "heyecan", "😂", "😊", "🥰", "✨"),
    "sad": ("üzgünüm", "üzüldüm", "kırıldım", "özledim", "yalnızım", "🥺", "😔"),
    "angry": ("sinirliyim", "kızgınım", "bıktım", "yeter artık", "lanet", "😠", "😡"),
    "flirty": ("öp", "öpücük", "özledim seni", "çekicisin", "tatlısın", "😘", "😉", "😏", "❤️"),
    "calm": ("sakin ol", "derin nefes", "dinlen", "yavaşça", "merak etme"),
}
MAX_TEXT_LENGTH = 1200
MIN_SEND_INTERVAL = 30
_semaphore = asyncio.Semaphore(2)
_last_sent = {}


def resolve_voice_style(character_key: str, text: str) -> tuple[str, str, str | None]:
    """Combine a character's baseline delivery with one subtle emotion cue."""
    base_rate, base_pitch = VOICE_STYLE.get(character_key, ("+0%", "+0Hz"))
    lowered = (text or "").casefold()
    emotion = next((name for name, cues in EMOTION_CUES.items() if any(cue in lowered for cue in cues)), None)
    rate_delta, pitch_delta = EMOTION_STYLE.get(emotion, (0, 0))
    rate = max(-18, min(18, int(base_rate.rstrip("%+")) + rate_delta))
    pitch = max(-3, min(3, int(base_pitch.rstrip("Hz+")) + pitch_delta))
    return f"{rate:+d}%", f"{pitch:+d}Hz", emotion


async def send_voice(bot, chat_id: int, character_key: str, text: str):
    """Synthesize and send a short voice note, always deleting its temporary file."""
    text = (text or "").strip()
    if not text or len(text) > MAX_TEXT_LENGTH:
        raise ValueError("Voice text is empty or too long")
    async with _semaphore:
        now = time.monotonic()
        if now - _last_sent.get(chat_id, 0) < MIN_SEND_INTERVAL:
            raise RuntimeError("Voice rate limit reached")
        _last_sent[chat_id] = now
        rate, pitch, _ = resolve_voice_style(character_key, text)
        path = None
        try:
            with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as audio:
                path = audio.name
            communicate = edge_tts.Communicate(
                text, VOICE_PROFILES.get(character_key, "tr-TR-EmelNeural"), rate=rate, pitch=pitch
            )
            await communicate.save(path)
            with open(path, "rb") as audio:
                await bot.send_voice(chat_id=chat_id, voice=audio)
        finally:
            if path and os.path.exists(path):
                os.unlink(path)

