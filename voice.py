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
MAX_TEXT_LENGTH = 1200
MIN_SEND_INTERVAL = 30
_semaphore = asyncio.Semaphore(2)
_last_sent = {}


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
        rate, pitch = VOICE_STYLE.get(character_key, ("+0%", "+0Hz"))
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
