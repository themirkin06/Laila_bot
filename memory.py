"""Laila sohbet hafızası, kullanıcı profili, uzun süreli anılar ve günlük kayıtları.

Telegram akışı main.py'de kalır. Bu modül:
- Karakter başına ayrı kısa sohbet geçmişi tutar.
- Kullanıcı profilini karakterlerden bağımsız saklar.
- Karaktere özel uzun süreli anıları ve günlük kayıtlarını yönetir.
- Upstash Redis üzerinden kullanıcı durumunu kalıcılaştırır.

Mevcut main.py ile geriye dönük uyumluluk için eski fonksiyon adları korunmuştur.
"""

import asyncio
import json
import logging
import re
import time
import urllib.request
from datetime import datetime, timezone
from typing import Any

from config import (
    DB_AKTIF,
    DB_ANAHTAR_ONEK,
    HAFIZA_LIMITI,
    UPSTASH_TOKEN,
    UPSTASH_URL,
)

kullanici_durumu: dict[int, dict] = {}

# Her karakter için tutulabilecek uzun süreli anı sayısı.
UZUN_HAFIZA_LIMITI = 100
GUNLUK_LIMITI = 100
PROFIL_BILGI_LIMITI = 20
REDIS_TIMEOUT = 15


def redis_komut(*args):
    """Upstash Redis REST üzerinden tek komut çalıştırır."""
    if not UPSTASH_URL or not UPSTASH_TOKEN:
        raise RuntimeError("Upstash URL veya token ayarlanmamış.")

    req = urllib.request.Request(
        UPSTASH_URL,
        data=json.dumps(list(args), ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {UPSTASH_TOKEN}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=REDIS_TIMEOUT) as response:
        cevap = json.loads(response.read().decode("utf-8"))

    if isinstance(cevap, dict) and cevap.get("error"):
        raise RuntimeError(cevap["error"])
    return cevap.get("result") if isinstance(cevap, dict) else cevap


def durumlari_yukle_sync(durum_tamamla_fn) -> dict:
    """Redis kullanıcı durumlarını SCAN ile yükler; eski kayıtları tamamlar."""
    if not DB_AKTIF:
        return {}

    sonuc: dict[int, dict] = {}
    cursor = "0"
    onek = f"{DB_ANAHTAR_ONEK}*"

    try:
        while True:
            cevap = redis_komut("SCAN", cursor, "MATCH", onek, "COUNT", 100)
            if not isinstance(cevap, (list, tuple)) or len(cevap) != 2:
                logging.error("Redis SCAN beklenmeyen cevap döndürdü.")
                break

            cursor, anahtarlar = str(cevap[0]), cevap[1] or []
            for anahtar in anahtarlar:
                try:
                    veri = redis_komut("GET", anahtar)
                    if not veri:
                        continue
                    user_id = int(str(anahtar).rsplit(":", 1)[-1])
                    durum = json.loads(veri)
                    if isinstance(durum, dict):
                        sonuc[user_id] = durum_tamamla_fn(durum)
                except Exception:
                    logging.exception("Kullanıcı hafızası yüklenemedi: %s", anahtar)

            if cursor == "0":
                break
    except Exception:
        logging.exception("Redis hafızaları yüklenirken hata oluştu.")

    return sonuc


async def durum_kaydet(user_id: int):
    """Kullanıcının güncel durumunu Redis'e kaydeder."""
    if not DB_AKTIF:
        return

    durum = kullanici_durumu.get(user_id)
    if not isinstance(durum, dict):
        return

    try:
        veri = json.dumps(durum, ensure_ascii=False, separators=(",", ":"))
        await asyncio.to_thread(
            redis_komut, "SET", f"{DB_ANAHTAR_ONEK}{user_id}", veri
        )
    except Exception:
        logging.exception("Hafıza kaydedilemedi (user_id=%s).", user_id)


def hafiza_al(durum: dict) -> list:
    """Seçili karakterin ayrı kısa sohbet geçmişini döndürür."""
    hafizalar = durum.setdefault("hafizalar", {})
    if not isinstance(hafizalar, dict):
        hafizalar = {}
        durum["hafizalar"] = hafizalar

    karakter = str(durum.get("karakter") or "leyla")
    gecmis = hafizalar.setdefault(karakter, [])
    if not isinstance(gecmis, list):
        gecmis = []
        hafizalar[karakter] = gecmis
    return gecmis


def hafiza_kaydi(dusunce: str, cevap: str) -> str:
    """Geriye dönük uyumluluk: sohbet geçmişine gönderilen cevabı döndürür."""
    return str(cevap or "")


def hafizayi_kirp(hafiza: list):
    """Kısa sohbet geçmişini yapılandırılmış sınırda tutar."""
    try:
        limit = max(2, int(HAFIZA_LIMITI))
    except (TypeError, ValueError):
        limit = 40

    if len(hafiza) > limit:
        del hafiza[:-limit]


def sahne_olayi_ekle(durum: dict, karakter: str, kullanici_mesaji: str, karakter_cevabi: str, limit: int = 5) -> str:
    """Son etkileşimleri karaktere özel sahne devamlılığı olarak saklar.

    Bu kayıtlar kesin konum/eylem iddiası üretmez; konuşmada gerçekten geçen
    ifadeleri kısa alıntılar halinde korur. Böylece model sahneyi yeniden
    başlatmak yerine son ortak bağlamı görebilir.
    """
    karakter = _karakter_anahtari(durum, karakter)
    alan = durum.setdefault("sahne_olaylari", {})
    if not isinstance(alan, dict):
        alan = {}
        durum["sahne_olaylari"] = alan
    olaylar = alan.setdefault(karakter, [])
    if not isinstance(olaylar, list):
        olaylar = []
        alan[karakter] = olaylar

    kullanici = " ".join(str(kullanici_mesaji or "").split()).strip()[:170]
    cevap = " ".join(str(karakter_cevabi or "").split()).strip()[:230]
    if kullanici or cevap:
        olaylar.append({
            "zaman": datetime.now(timezone.utc).astimezone().isoformat(),
            "kullanici": kullanici,
            "karakter": cevap,
        })
        del olaylar[:-max(1, int(limit))]

    satirlar = ["[OTOMATİK SAHNE DEVAMLILIĞI — SON ETKİLEŞİMLER]"]
    for olay in olaylar:
        if not isinstance(olay, dict):
            continue
        if olay.get("kullanici"):
            satirlar.append(f"Kullanıcı: {olay['kullanici']}")
        if olay.get("karakter"):
            satirlar.append(f"Karakter: {olay['karakter']}")
    satirlar.append(
        "Bu kayıtlar son konuşmada geçen olaylardır. Açıkça ayrılma, zaman atlaması "
        "veya mekân değişikliği söylenmedikçe mevcut sahneyi ve birlikte bulunma "
        "durumunu sebepsiz yere sıfırlama. Kullanıcının yanında olmadığını varsayma; "
        "kayıtlar çelişiyorsa en yeni açık ifadeyi esas al. Kayıtlarda olmayan ayrıntıyı uydurma."
    )
    notu = "\n".join(satirlar)
    durum.setdefault("sahne_hafizasi", {})[karakter] = notu[:2400]
    return durum["sahne_hafizasi"][karakter]


def kullanici_profili_al(durum: dict) -> dict:
    """Kullanıcının açıkça söylediği, hassas olmayan bilgileri döndürür."""
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
    """Açık öz tanıtım ve düşük hassasiyetli tercihleri kaydeder; tahmin etmez."""
    profil = kullanici_profili_al(durum)
    metin = str(mesaj or "").strip()
    if not metin:
        return profil

    # İsim yalnızca açık tanıtım kalıplarıyla alınır; "ben mutluyum" ad sayılmaz.
    ad_eslesme = re.search(
        r"\b(?:benim adım|adım|ismim)\s+"
        r"([A-ZÇĞİÖŞÜ][a-zçğıöşü]+(?:\s+[A-ZÇĞİÖŞÜ][a-zçğıöşü]+)?)\b",
        metin,
        re.IGNORECASE,
    )
    if ad_eslesme:
        aday = ad_eslesme.group(1).strip()
        if aday.casefold() not in {
            "iyiyim", "bilmiyorum", "buradayım", "geldim", "sadece",
            "mutluyum", "üzgünüm",
        }:
            profil["ad"] = aday

    yas_eslesme = re.search(
        r"\b(?:ben\s+)?(\d{1,2})\s+yaş(?:ındayım|indayım|ındayim|im)?\b"
        r"|\byaşım\s+(\d{1,2})\b",
        metin,
        re.IGNORECASE,
    )
    if yas_eslesme:
        sayi = next((x for x in yas_eslesme.groups() if x), None)
        if sayi:
            yas = int(sayi)
            if 18 <= yas <= 100:
                profil["yas"] = yas

    hassas = (
        "şifre", "sifre", "parola", "tc kimlik", "kimlik numarası",
        "telefon numaram", "adresim", "maaşım", "maasim", "borcum",
        "kredi kartı", "kredi kartim", "hastalığım", "hastaligim",
        "ilaçlarım", "ilaclarim", "teşhis", "teshis", "depresyon",
        "intihar", "cinsel", "siyasi görüş", "siyasi gorus",
    )

    if not any(terim in metin.casefold() for terim in hassas):
        kaliplar = (
            r"(?:en sevdiğim|en sevdigim|favorim)\s+([^.!?\n]{2,60})",
            r"(?:hobim|ilgi alanım|ilgi alanlarım)\s+(?:ise\s+)?([^.!?\n]{2,60})",
            r"([\wçğıöşüÇĞİÖŞÜ'’-]+(?:\s+[\wçğıöşüÇĞİÖŞÜ'’-]+){0,5}?)"
            r"\s+(?:çok\s+)?(?:seviyorum|severim|tercih ederim|tercih ediyorum)\b",
        )
        for kalip in kaliplar:
            eslesme = re.search(kalip, metin, re.IGNORECASE)
            if not eslesme:
                continue
            bilgi = " ".join(eslesme.group(1).split()).strip(" \t,;:-")
            if not bilgi or bilgi.casefold() in {
                "seni", "onu", "bunu", "kendimi", "çok",
            }:
                continue
            bilgiler = profil["bilgiler"]
            if not any(str(k).casefold() == bilgi.casefold() for k in bilgiler):
                bilgiler.append(bilgi)
                del bilgiler[:-PROFIL_BILGI_LIMITI]
            break

    return profil


def kullanici_profili_prompt(durum: dict, telegram_adi: str = "") -> str:
    """Modele doğrulanmış kullanıcı bilgisini ve bilinmeyenleri bildirir."""
    profil = kullanici_profili_al(durum)
    ad = profil.get("ad") or "henüz öğrenilmedi"
    yas = profil.get("yas") or "henüz öğrenilmedi"
    bilgiler = profil.get("bilgiler", [])
    gorunen_ad = str(telegram_adi or "").strip() or "yok"
    bilinenler = "; ".join(str(x) for x in bilgiler[-PROFIL_BILGI_LIMITI:]) or "henüz öğrenilmedi"

    return (
        "[KULLANICI PROFİLİ — GERÇEK BİLGİLER]\n"
        f"Kullanıcının açıkça söylediği tercih ettiği ad: {ad}. Yaş: {yas}. "
        f"Açıkça belirttiği ilgi ve tercihler: {bilinenler}. "
        f"Telegram görünen adı: {gorunen_ad} (tercih edilen ad olduğu varsayılmaz).\n"
        "Henüz öğrenilmedi yazan alanlarda tahmin yürütme. Kullanıcının düzeltmesini "
        "esas al. Hatırlanan tercihleri yalnızca konuya uyduğunda doğal biçimde kullan; "
        "liste gibi sayma ve aynı bilgiyi tekrar tekrar sorma."
    )


def _karakter_anahtari(durum: dict, karakter: str | None = None) -> str:
    return str(karakter or durum.get("karakter") or "leyla")


def uzun_hafiza_al(durum: dict, karakter: str | None = None) -> list:
    """Karaktere özel uzun süreli anı listesini döndürür."""
    karakter = _karakter_anahtari(durum, karakter)
    alan = durum.setdefault("uzun_hafiza", {})
    if not isinstance(alan, dict):
        alan = {}
        durum["uzun_hafiza"] = alan
    kayitlar = alan.setdefault(karakter, [])
    if not isinstance(kayitlar, list):
        kayitlar = []
        alan[karakter] = kayitlar
    return kayitlar


def uzun_hafiza_ekle(
    durum: dict,
    icerik: str,
    karakter: str | None = None,
    tur: str = "olay",
    kaynak: str = "sohbet",
    limit: int = UZUN_HAFIZA_LIMITI,
) -> bool:
    """Tekrarlı kayıtları azaltarak karakterin uzun süreli hafızasına not ekler."""
    icerik = " ".join(str(icerik or "").split()).strip()
    if len(icerik) < 4:
        return False

    kayitlar = uzun_hafiza_al(durum, karakter)
    norm = icerik.casefold()
    if any(
        isinstance(k, dict)
        and str(k.get("icerik", "")).casefold() == norm
        for k in kayitlar[-30:]
    ):
        return False

    kayitlar.append({
        "zaman": datetime.now(timezone.utc).astimezone().isoformat(),
        "tur": str(tur or "olay")[:30],
        "kaynak": str(kaynak or "sohbet")[:30],
        "icerik": icerik[:500],
    })
    del kayitlar[:-max(1, int(limit))]
    return True


def uzun_hafiza_prompt(durum: dict, karakter: str | None = None, limit: int = 12) -> str:
    """Modele seçili karakterin en yeni uzun süreli anılarını verir."""
    kayitlar = uzun_hafiza_al(durum, karakter)
    secilen = [
        k for k in kayitlar[-max(1, limit):]
        if isinstance(k, dict) and k.get("icerik")
    ]
    if not secilen:
        return ""

    satirlar = ["[KARAKTERİN UZUN SÜRELİ HAFIZASI]"]
    for kayit in secilen:
        zaman = str(kayit.get("zaman", ""))[:16]
        tur = str(kayit.get("tur", "olay"))
        satirlar.append(f"- ({tur}, {zaman}) {kayit['icerik']}")
    satirlar.append(
        "Bu kayıtları geçmişte yaşanmış bilgiler olarak değerlendir. "
        "Kayıtlarda olmayan ayrıntıları uydurma; uygun olduğunda doğal biçimde hatırla."
    )
    return "\n".join(satirlar)


def gunluk_al(durum: dict, karakter: str | None = None) -> list:
    """Bir karakterin günlük kayıt listesini döndürür."""
    karakter = _karakter_anahtari(durum, karakter)
    gunluk = durum.setdefault("gunluk", {})
    if not isinstance(gunluk, dict):
        gunluk = {}
        durum["gunluk"] = gunluk
    kayitlar = gunluk.setdefault(karakter, [])
    if not isinstance(kayitlar, list):
        kayitlar = []
        gunluk[karakter] = kayitlar
    return kayitlar


def gunluk_ekle(
    durum: dict,
    icerik: str,
    karakter: str | None = None,
    limit: int = GUNLUK_LIMITI,
):
    """Karakter günlüğüne zaman damgalı not ekler; aynı notu aynı gün tekrarlamaz."""
    icerik = " ".join(str(icerik or "").split()).strip()
    if not icerik:
        return False

    kayitlar = gunluk_al(durum, karakter)
    bugun = datetime.now().astimezone().date().isoformat()
    if any(
        isinstance(k, dict)
        and str(k.get("zaman", "")).startswith(bugun)
        and str(k.get("icerik", "")).casefold() == icerik.casefold()
        for k in kayitlar[-20:]
    ):
        return False

    kayitlar.append({
        "zaman": datetime.now().astimezone().isoformat(),
        "icerik": icerik[:500],
    })
    del kayitlar[:-max(1, int(limit))]
    return True


def gunluk_prompt(durum: dict, karakter: str | None = None, limit: int = 8) -> str:
    """Son günlük kayıtlarını modele bağlam olarak verir."""
    kayitlar = gunluk_al(durum, karakter)
    secilen = [k for k in kayitlar[-max(1, limit):] if isinstance(k, dict) and k.get("icerik")]
    if not secilen:
        return ""
    return "[SON GÜNLÜK KAYITLARI]\n" + "\n".join(
        f"- {str(k.get('zaman', ''))[:16]}: {k['icerik']}"
        for k in secilen
    )



def karakter_hafizasini_temizle(durum: dict, karakter: str | None = None) -> None:
    """Tek karakterin sohbet, uzun hafıza ve günlük kayıtlarını temizler."""
    karakter = _karakter_anahtari(durum, karakter)
    for alan_adi in ("hafizalar", "uzun_hafiza", "gunluk", "sahneler", "sahne_hafizasi", "sahne_olaylari"):
        alan = durum.setdefault(alan_adi, {})
        if isinstance(alan, dict):
            alan[karakter] = [] if alan_adi in ("hafizalar", "uzun_hafiza", "gunluk", "sahne_olaylari") else ""


def tum_hafizayi_temizle(durum: dict) -> None:
    """Tüm karakter hafızalarını, profili ve ilişki ilerlemesini sıfırlar.

    Seçili karakter, Telegram sohbeti ve kullanıcının görünüm/stil tercihi korunur.
    """
    sifir_liste_alanlari = (
        "hafizalar", "uzun_hafiza", "gunluk", "tanismalar", "yakinlik",
        "iliski", "duygular", "karakter_sirlari", "dunya", "yan_karakterler",
        "son_olaylar", "sahneler", "sahne_hafizasi", "sahne_olaylari", "seviye_foto_gonderildi",
    )
    for alan_adi in sifir_liste_alanlari:
        durum[alan_adi] = {}

    durum["kullanici_profili"] = {"ad": "", "yas": None, "bilgiler": []}
    durum["cevapsiz"] = 0
    durum["son_kullanici"] = time.time()
    durum["son_etkilesim"] = time.time()
    durum["son_proaktif_foto"] = 0
    durum["proaktif_foto_gun"] = ""
    durum["proaktif_foto_sayi"] = 0
    durum["proaktif_gun"] = ""
    durum["proaktif_sayi"] = 0

def hafiza_istatistigi(durum: dict) -> dict:
    """Hafızanın boyutunu ve karakter bazında kayıt sayılarını raporlar."""
    kisa = durum.get("hafizalar", {})
    uzun = durum.get("uzun_hafiza", {})
    gunluk = durum.get("gunluk", {})
    return {
        "kisa_hafiza": {
            str(k): len(v) for k, v in kisa.items()
            if isinstance(kisa, dict) and isinstance(v, list)
        } if isinstance(kisa, dict) else {},
        "uzun_hafiza": {
            str(k): len(v) for k, v in uzun.items()
            if isinstance(uzun, dict) and isinstance(v, list)
        } if isinstance(uzun, dict) else {},
        "gunluk": {
            str(k): len(v) for k, v in gunluk.items()
            if isinstance(gunluk, dict) and isinstance(v, list)
        } if isinstance(gunluk, dict) else {},
    }
