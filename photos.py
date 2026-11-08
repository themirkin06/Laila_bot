"""Laila fotoğraf üretim sağlayıcısı.

Referans görsel varsa Cloudflare FLUX.2 Klein 9B ile yüz kimliğini korumaya çalışır.
Referans yoksa mevcut FLUX Schnell akışı korunur.
"""
import asyncio
import base64
import json
import logging
import urllib.parse
import urllib.request
import uuid

from config import CF_ACCOUNT_ID, CF_API_TOKEN, CF_AKTIF, POLL_KEY, POLL_MODEL
from characters import foto_promptu


def gorsel_indir(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=90) as r:
        return r.read()


def _multipart_govde(fields: dict, files: dict) -> tuple[bytes, str]:
    """Standart kütüphane ile multipart/form-data gövdesi kurar."""
    boundary = "----Laila" + uuid.uuid4().hex
    chunks = []
    for name, value in fields.items():
        chunks.extend([
            f"--{boundary}\r\n".encode(),
            f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode(),
            str(value).encode("utf-8"), b"\r\n",
        ])
    for name, (filename, content, content_type) in files.items():
        chunks.extend([
            f"--{boundary}\r\n".encode(),
            f'Content-Disposition: form-data; name="{name}"; filename="{filename}"\r\n'.encode(),
            f"Content-Type: {content_type}\r\n\r\n".encode(),
            content, b"\r\n",
        ])
    chunks.append(f"--{boundary}--\r\n".encode())
    return b"".join(chunks), f"multipart/form-data; boundary={boundary}"


def cloudflare_referansli_sync(prompt: str, seed: int, reference_image: bytes) -> bytes:
    """FLUX.2 Klein 9B'ye tek yüz referansı gönderir."""
    url = (
        f"https://api.cloudflare.com/client/v4/accounts/{CF_ACCOUNT_ID}"
        "/ai/run/@cf/black-forest-labs/flux-2-klein-9b"
    )
    referansli_prompt = (
        "Use input_image_0 as the identity reference for the same fictional adult woman. "
        "Preserve her recognizable facial identity, face shape, eyes, nose, lips, age, "
        "skin tone and hair identity. Change only outfit, pose, expression, lighting and "
        "setting as described. Do not create a different person. " + prompt
    )
    body, content_type = _multipart_govde(
        {"prompt": referansli_prompt, "width": 768, "height": 1024, "seed": seed, "guidance": 3.5},
        {"input_image_0": ("identity-reference.jpg", reference_image, "image/jpeg")},
    )
    req = urllib.request.Request(
        url, data=body,
        headers={"Authorization": f"Bearer {CF_API_TOKEN}", "Content-Type": content_type,
                 "User-Agent": "Mozilla/5.0"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=150) as r:
        cevap = json.loads(r.read().decode("utf-8"))
    resim = (cevap.get("result") or {}).get("image")
    if not resim:
        raise RuntimeError(f"Cloudflare referanslı görsel döndürmedi: {cevap.get('errors') or cevap}")
    if isinstance(resim, str) and resim.startswith(("http://", "https://")):
        return gorsel_indir(resim)
    try:
        return base64.b64decode(resim)
    except Exception as exc:
        raise RuntimeError("Cloudflare referanslı görsel yanıtı çözümlenemedi.") from exc


def cloudflare_gorsel_sync(prompt: str, seed: int) -> bytes:
    url = (
        f"https://api.cloudflare.com/client/v4/accounts/{CF_ACCOUNT_ID}"
        "/ai/run/@cf/black-forest-labs/flux-1-schnell"
    )
    req = urllib.request.Request(
        url,
        data=json.dumps({"prompt": prompt, "steps": 6, "seed": seed}).encode("utf-8"),
        headers={"Authorization": f"Bearer {CF_API_TOKEN}", "Content-Type": "application/json",
                 "User-Agent": "Mozilla/5.0"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=90) as r:
        cevap = json.loads(r.read().decode("utf-8"))
    resim = (cevap.get("result") or {}).get("image")
    if not resim:
        raise RuntimeError(f"Cloudflare görsel döndürmedi: {cevap.get('errors')}")
    if isinstance(resim, str) and resim.startswith(("http://", "https://")):
        return gorsel_indir(resim)
    return base64.b64decode(resim)


async def foto_uret_bytes(
    karakter: dict, seed: int, yakinlik: int = 0, surpriz: bool = False,
    reference_image: bytes = None,
) -> bytes:
    """Referans varsa yüzü korumaya çalışır; yoksa eski üretim akışını kullanır."""
    prompt = foto_promptu(karakter, yakinlik=yakinlik, surpriz=surpriz)
    if reference_image and not CF_AKTIF:
        raise RuntimeError("Yüz referanslı üretim için CLOUDFLARE_ACCOUNT_ID ve CLOUDFLARE_API_TOKEN gerekli.")
    if CF_AKTIF and reference_image:
        # Referanslı üretim başarısızsa farklı yüz üretebilecek metin tabanlı yedeğe geçme.
        return await asyncio.to_thread(cloudflare_referansli_sync, prompt, seed, reference_image)
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
