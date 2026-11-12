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



def kullanici_profili_al(durum: dict) -> dict:
    """Kullanıcının kendi söylediği bilgileri karakterlerden bağımsız saklar."""
    profil = durum.setdefault("kullanici_profili", {})
    if not isinstance(profil, dict):
        profil = {}
        durum["kullanici_profili"] = profil
    profil.setdefault("ad", "")
    profil.setdefault("yas", None)
    profil.setdefault("bilgiler", [])
    if not isinstance(profil["bilgiler"], list):
        profil["bilgiler"] = []
    return profil


def kullanici_bilgisi_ogren(durum: dict, mesaj: str):
    """Açık öz tanıtım, yaş ve basit ilgi/tercih ifadelerini kaydeder; tahmin yürütmez."""
    import re

    profil = kullanici_profili_al(durum)
    metin = str(mesaj or "").strip()

    ad_eslesme = re.search(
        r"\b(?:benim adım|adım|ismim|ben)\s+([A-ZÇĞİÖŞÜ][a-zçğıöşü]+(?:\s+[A-ZÇĞİÖŞÜ][a-zçğıöşü]+)?)\b",
        metin, re.IGNORECASE,
    )
    if ad_eslesme:
        aday = ad_eslesme.group(1).strip()
        if aday.lower() not in {"iyiyim", "bilmiyorum", "buradayım", "geldim", "sadece"}:
            profil["ad"] = aday

    yas_eslesme = re.search(r"\b(?:ben\s+)?(\d{1,2})\s+yaş(?:ındayım|ındayım|ındayim|im)?\b|\byaşım\s+(\d{1,2})\b", metin, re.IGNORECASE)
    if yas_eslesme:
        sayi = next((x for x in yas_eslesme.groups() if x), None)
        if sayi:
            yas = int(sayi)
            if 18 <= yas <= 100:
                profil["yas"] = yas

    # Yalnızca açıkça ifade edilmiş ve düşük hassasiyetli ilgi/tercih cümlelerini sakla.
    # Kişisel, finansal, sağlıkla ilgili veya başka hassas konuları kalıcı profile alma.
    hassas = (
        "şifre", "sifre", "parola", "tc kimlik", "kimlik numarası", "telefon numaram",
        "adresim", "maaşım", "maasim", "borcum", "kredi kartı", "kredi kartim",
        "hastalığım", "hastaligim", "ilaçlarım", "ilaclarim", "teşhis", "teshis",
        "depresyon", "intihar", "cinsel", "siyasi görüş", "siyasi gorus",
    )
    if not any(terim in metin.casefold() for terim in hassas):
        kaliplar = (
            r"(?:en sevdiğim|en sevdigim|favorim)\s+([^.!?\n]{2,60})",
            r"(?:hobim|ilgi alanım|ilgi alanlarım)\s+(?:ise\s+)?([^.!?\n]{2,60})",
            r"(?:ben\s+)?([\wçğıöşüÇĞİÖŞÜ'’-]+(?:\s+[\wçğıöşüÇĞİÖŞÜ'’-]+){0,5}?)\s+(?:çok\s+)?(?:seviyorum|severim|tercih ederim|tercih ediyorum)\b",
        )
        for kalip in kaliplar:
            eslesme = re.search(kalip, metin, re.IGNORECASE)
            if not eslesme:
                continue
            bilgi = " ".join(eslesme.group(1).split()).strip(" \t,;:-")
            if not bilgi or bilgi.casefold() in {"seni", "onu", "bunu", "kendimi"}:
                continue
            bilgiler = profil["bilgiler"]
            if not any(str(kayit).casefold() == bilgi.casefold() for kayit in bilgiler):
                bilgiler.append(bilgi)
                del bilgiler[:-12]
            break

    return profil


def kullanici_profili_prompt(durum: dict, telegram_adi: str = "") -> str:
    """Modele doğrulanmış kullanıcı bilgisini ve bilinmeyenleri bildirir."""
    profil = kullanici_profili_al(durum)
    ad = profil.get("ad") or "henüz öğrenilmedi"
    yas = profil.get("yas") or "henüz öğrenilmedi"
    bilgiler = profil.get("bilgiler", [])
    gorunen_ad = telegram_adi.strip() or "yok"
    bilinenler = "; ".join(str(bilgi) for bilgi in bilgiler[-12:]) or "henüz öğrenilmedi"
    return (
        "[KULLANICI PROFİLİ — GERÇEK BİLGİLER]\n"
        f"Kullanıcının açıkça söylediği tercih ettiği ad: {ad}. Yaş: {yas}. "
        f"Açıkça belirttiği ilgi ve tercihler: {bilinenler}. "
        f"Telegram görünen adı: {gorunen_ad} (bu, tercih ettiği ad olduğu anlamına gelmez).\n"
        "Bu alanlarda 'henüz öğrenilmedi' yazıyorsa tahmin etme veya uydurma. "
        "Kullanıcıyı doğal sohbet içinde tanımaya çalış; adını bilmiyorsan nasıl hitap etmeni istediğini sor. "
        "Yaşını yalnızca sohbetin akışına uygunsa sor; sorguya çevirme. "
        "Hatırlanan ilgi ve tercihleri yalnızca konuya uyduğunda doğal biçimde kullan; liste gibi sayma veya aynı şeyi tekrar tekrar sorma. "
        "Bunlar değişmiş olabilir; kullanıcı düzeltirse yeni söylediğini esas al. Kullanıcının söylemediği çıkarımları gerçek gibi kaydetme."
    )


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
