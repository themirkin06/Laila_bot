"""Laila fotoğraf üretim sağlayıcısı.

Fotoğraf üretim fonksiyonları burada tutulur. Telegram havuzu ve Redis kayıtları
main.py içinde kalır; böylece mevcut havuz komutlarının davranışı değişmez.
"""
import asyncio
import base64
import json
import logging
import urllib.parse
import urllib.request

from config import CF_ACCOUNT_ID, CF_API_TOKEN, CF_AKTIF, POLL_KEY, POLL_MODEL
from characters import foto_promptu


def gorsel_indir(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=90) as r:
        return r.read()


def cloudflare_gorsel_sync(prompt: str, seed: int) -> bytes:
    url = (
        f"https://api.cloudflare.com/client/v4/accounts/{CF_ACCOUNT_ID}"
        "/ai/run/@cf/black-forest-labs/flux-1-schnell"
    )
    req = urllib.request.Request(
        url,
        data=json.dumps({"prompt": prompt, "steps": 6, "seed": seed}).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {CF_API_TOKEN}",
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=90) as r:
        cevap = json.loads(r.read().decode("utf-8"))
    resim = (cevap.get("result") or {}).get("image")
    if not resim:
        raise RuntimeError(f"Cloudflare görsel döndürmedi: {cevap.get('errors')}")
    return base64.b64decode(resim)


async def foto_uret_bytes(
    karakter: dict, seed: int, yakinlik: int = 0, surpriz: bool = False
) -> bytes:
    """Önce Cloudflare FLUX, başarısızsa Pollinations ile fotoğraf üretir."""
    prompt = foto_promptu(karakter, yakinlik=yakinlik, surpriz=surpriz)

    if CF_AKTIF:
        try:
            return await asyncio.to_thread(cloudflare_gorsel_sync, prompt, seed)
        except Exception as e:
            logging.warning(f"Cloudflare görsel hatası, Pollinations'a düşülüyor: {e}")

    encoded = urllib.parse.quote(prompt)
    adresler = []
    if POLL_KEY:
        adresler.append(
            f"https://gen.pollinations.ai/image/{encoded}"
            f"?model={POLL_MODEL}&width=768&height=1024&nologo=true&seed={seed}"
            f"&key={urllib.parse.quote(POLL_KEY)}"
        )
    adresler.append(
        f"https://image.pollinations.ai/prompt/{encoded}"
        f"?width=768&height=1024&nologo=true&model=flux&seed={seed}"
    )

    son_hata = None
    for url in adresler:
        try:
            return await asyncio.to_thread(gorsel_indir, url)
        except Exception as e:
            son_hata = e
            logging.warning(f"Görsel alınamadı ({type(e).__name__}): {e}")
    if son_hata:
        raise son_hata
    raise RuntimeError("Fotoğraf üretimi için kullanılabilir sağlayıcı bulunamadı.")
