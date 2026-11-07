import os
import re
import json
import base64
import uuid
import html
import time
import random
import asyncio
import logging
import threading
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone, timedelta
from http.server import HTTPServer, BaseHTTPRequestHandler
from pollinations import Pollinations

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, ContextTypes, MessageHandler, filters, CommandHandler, CallbackQueryHandler

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
# httpx her isteği URL'siyle (içinde bot token'ı var) loglar. Token loglara sızmasın diye sustur.
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
client = Pollinations(api_key=os.getenv("POLLINATIONS_API_KEY"))

# Sadece senin kullanman için kilit. Render'da OWNER_ID ortam değişkenine
# kendi Telegram ID'ni yaz (@userinfobot'tan öğrenebilirsin). Boş bırakırsan herkese açık olur.
OWNER_ID = int(os.getenv("OWNER_ID", "0") or 0)

HAFIZA_LIMITI = 40
TZ = timezone(timedelta(hours=3))  # Türkiye saati

# Kendiliğinden mesaj atma ayarları
PROAKTIF_ACIK = os.getenv("PROAKTIF_ACIK", "1") != "0"
PROAKTIF_SAAT_ARALIGI = ((9, 0), (18, 30))   # sadece 09:00 - 18:30 arasında yazar (Türkiye saati)
PROAKTIF_GUNLUK_LIMIT = 3         # günde en fazla kaç kendiliğinden mesaj
# Kendiliğinden mesajlarda fotoğraf atma ihtimali (yakınlık seviyesine göre: tanışma, ısınma, samimi, yakın).
# Tanışma aşamasında hiç atmaz. Ayrıca en az 24 saatte bir.
PROAKTIF_FOTO_ORANLARI = [0.0, 0.08, 0.15, 0.25]
PROAKTIF_FOTO_ARALIK = 24 * 3600

# Kalıcı hafıza (Upstash Redis, REST). İkisi de doluysa açılır, yoksa hafıza sadece RAM'de tutulur.
UPSTASH_URL = os.getenv("UPSTASH_REDIS_REST_URL", "").strip().rstrip("/")
UPSTASH_TOKEN = os.getenv("UPSTASH_REDIS_REST_TOKEN", "").strip()
DB_AKTIF = bool(UPSTASH_URL and UPSTASH_TOKEN)
DB_ANAHTAR_ONEK = "bot:durum:"

# Daha gerçekçi fotoğraflar için Cloudflare Workers AI (FLUX). İkisi de doluysa önce o denenir,
# olmazsa Pollinations'a düşer.
CF_ACCOUNT_ID = os.getenv("CLOUDFLARE_ACCOUNT_ID", "").strip()
CF_API_TOKEN = os.getenv("CLOUDFLARE_API_TOKEN", "").strip()
CF_AKTIF = bool(CF_ACCOUNT_ID and CF_API_TOKEN)

# Pollinations görsel ayarları. Anahtar chat için kullandığın POLLINATIONS_API_KEY ile aynı.
# Model değiştirmek için Render'a POLLINATIONS_IMAGE_MODEL ekleyebilirsin (örn. flux, gptimage, seedream, nanobanana).
POLL_KEY = os.getenv("POLLINATIONS_API_KEY", "").strip()
POLL_MODEL = os.getenv("POLLINATIONS_IMAGE_MODEL", "flux").strip() or "flux"

# Sohbet modeli ve sıcaklığı (Render'dan değiştirilebilir). Sıcaklık düşükse cümleler daha tutarlı olur.
LLM_MODEL = os.getenv("LLM_MODEL", "openai").strip() or "openai"
try:
    LLM_SICAKLIK = float(os.getenv("LLM_SICAKLIK", "0.45"))
except ValueError:
    LLM_SICAKLIK = None

# --- SES AYARLARI ---
# Ses çıkışı (TTS): edge-tts paketi kuruluysa açılır (requirements.txt'ye `edge-tts` ekle).
# Ses girişi (STT): GROQ_API_KEY varsa açılır (Groq'un ücretsiz Whisper'ı).
try:
    import edge_tts
except Exception:  # paket kurulu değilse ses özelliği sessizce kapalı kalır
    edge_tts = None

TTS_AKTIF = edge_tts is not None and os.getenv("SES_ACIK", "1") != "0"
GROQ_KEY = os.getenv("GROQ_API_KEY", "").strip()
SES_YAZIYI_GOSTER = True      # sesli mesajının metne çevrilmiş halini göster (doğru anlıyor mu diye)
SES_MAX_SANIYE = 90           # bundan uzun sesli mesajlar işlenmez
PROAKTIF_SES_ORANLARI = [0.0, 0.1, 0.25, 0.4]  # kendiliğinden mesajın sesli olma ihtimali (yakınlık seviyesine göre)

# Edge TTS'te Türkçe kadın sesi tek (Emel). Karakterleri hız ve ton farkıyla ayırıyoruz.
TR_SES = "tr-TR-EmelNeural"
SES_AYARLARI = {
    "leyla": (TR_SES, "-10%", "-2Hz"),
    "merve": (TR_SES, "+10%", "+4Hz"),
    "asli": (TR_SES, "+0%", "-3Hz"),
    "dilek": (TR_SES, "-5%", "+0Hz"),
    "ece": (TR_SES, "-8%", "+1Hz"),
    "ayse": (TR_SES, "-5%", "-5Hz"),
    "dondu": (TR_SES, "-3%", "-6Hz"),
