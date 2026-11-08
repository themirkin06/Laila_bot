"""Laila sohbet hafızası, kullanıcı durumları ve günlük kayıtları.

Telegram akışı main.py'de kalır. Bu modül konuşma geçmişini ve kullanıcı
verilerini RAM/Upstash üzerinde saklar; günlük kayıtları için de ortak yapı sağlar.
"""
import asyncio
import json
import logging
import time
import urllib.request
from datetime import datetime

from config import (
    DB_AKTIF,
    DB_ANAHTAR_ONEK,
    HAFIZA_LIMITI,
    UPSTASH_TOKEN,
    UPSTASH_URL,
)

# Main ve diğer modüller aynı kullanıcı durumu sözlüğünü kullanır.
kullanici_durumu: dict[int, dict] = {}


def redis_komut(*args):
    """Upstash Redis REST üzerinden tek bir komut çalıştırır."""
    req = urllib.request.Request(
        UPSTASH_URL,
        data=json.dumps(list(args)).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {UPSTASH_TOKEN}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=15) as response:
        cevap = json.loads(response.read().decode("utf-8"))
    if isinstance(cevap, dict) and cevap.get("error"):
        raise RuntimeError(cevap["error"])
    return cevap.get("result") if isinstance(cevap, dict) else cevap


def durumlari_yukle_sync(durum_tamamla_fn) -> dict:
    """Redis'teki kullanıcı durumlarını yükler ve eski kayıtları tamamlar."""
    sonuc = {}
    for anahtar in redis_komut("KEYS", DB_ANAHTAR_ONEK + "*") or []:
        veri = redis_komut("GET", anahtar)
        if veri:
            sonuc[int(anahtar.split(":")[-1])] = durum_tamamla_fn(json.loads(veri))
    return sonuc


async def durum_kaydet(user_id: int):
    """Bir kullanıcının güncel durumunu Redis'e kaydeder."""
    if not DB_AKTIF:
        return
    durum = kullanici_durumu.get(user_id)
    if not durum:
        return
    try:
        veri = json.dumps(durum, ensure_ascii=False)
        await asyncio.to_thread(
            redis_komut, "SET", f"{DB_ANAHTAR_ONEK}{user_id}", veri
        )
    except Exception as e:
        logging.error(f"Hafıza kaydedilemedi: {e}")


def hafiza_al(durum: dict) -> list:
    """Seçili karakterin ayrı konuşma geçmişini döndürür."""
    durum.setdefault("hafizalar", {})
    return durum["hafizalar"].setdefault(durum.get("karakter", "leyla"), [])


def hafiza_kaydi(dusunce: str, cevap: str) -> str:
    """Sohbet geçmişine yalnızca kullanıcıya gönderilen cevabı kaydeder."""
    return cevap


def hafizayi_kirp(hafiza: list):
    """Model bağlamı için konuşma geçmişini tanımlı sınırda tutar."""
    if len(hafiza) > HAFIZA_LIMITI:
        hafiza[:] = hafiza[-HAFIZA_LIMITI:]


def gunluk_al(durum: dict, karakter: str | None = None) -> list:
    """Bir karakterin günlük kayıt listesini döndürür (eski kayıtlarla uyumlu)."""
    karakter = karakter or durum.get("karakter", "leyla")
    gunluk = durum.setdefault("gunluk", {})
    if not isinstance(gunluk, dict):
        gunluk = {}
        durum["gunluk"] = gunluk
    kayitlar = gunluk.setdefault(karakter, [])
    if not isinstance(kayitlar, list):
        kayitlar = []
        gunluk[karakter] = kayitlar
    return kayitlar


def gunluk_ekle(durum: dict, icerik: str, karakter: str | None = None, limit: int = 50):
    """Karakter günlüğüne zaman damgalı bir not ekler.

    Bu yardımcı şu an otomatik olarak çağrılmıyor; günlük yazma kuralları
    netleştirildiğinde sohbet akışına bağlanabilir.
    """
    icerik = str(icerik).strip()
    if not icerik:
        return
    kayitlar = gunluk_al(durum, karakter)
    kayitlar.append({"zaman": datetime.now().astimezone().isoformat(), "icerik": icerik})
    if len(kayitlar) > limit:
        del kayitlar[:-limit]
