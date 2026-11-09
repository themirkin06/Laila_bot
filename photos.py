"""AI Horde Juggernaut XL img2img photo generation for Laila."""
import asyncio
import base64
import json
import logging
import secrets
import time
import urllib.error
import urllib.request
from io import BytesIO

from PIL import Image, ImageOps

from config import (
    AI_HORDE_IMAGE_API_KEY, AI_HORDE_IMAGE_MAX_WAIT, AI_HORDE_IMAGE_MODEL,
    CF_ACCOUNT_ID, CF_API_TOKEN, CF_AKTIF, CF_IMAGE_MODEL,
)
from characters import foto_promptu

AI_HORDE_URL = "https://aihorde.net/api/v2"
IMAGE_STEPS = 25
IMAGE_CFG_SCALE = 6
IMAGE_DENOISING_STRENGTH = 0.40
IMAGE_POLL_INTERVAL = 3
IMAGE_MAX_EDGE = 1024


def _source_to_webp(reference_image: bytes) -> tuple[bytes, int, int]:
    """Normalize a Telegram reference to a bounded, aspect-preserving WebP image."""
    if not reference_image:
        raise ValueError("AI Horde img2img için karakterin yüz referansı gerekli.")
    try:
        with Image.open(BytesIO(reference_image)) as opened:
            source = ImageOps.exif_transpose(opened).convert("RGB")
    except Exception as exc:
        raise ValueError("Karakterin yüz referansı okunamadı; geçerli bir fotoğraf yükle.") from exc

    scale = min(1.0, IMAGE_MAX_EDGE / max(source.size))
    scaled_width = max(1, round(source.width * scale))
    scaled_height = max(1, round(source.height * scale))
    width = max(512, min(IMAGE_MAX_EDGE, round(scaled_width / 64) * 64))
    height = max(512, min(IMAGE_MAX_EDGE, round(scaled_height / 64) * 64))
    contained = ImageOps.contain(source, (width, height), method=Image.Resampling.LANCZOS)
    canvas = Image.new("RGB", (width, height), (127, 127, 127))
    canvas.paste(contained, ((width - contained.width) // 2, (height - contained.height) // 2))
    output = BytesIO()
    canvas.save(output, format="WEBP", quality=92, method=4)
    return output.getvalue(), width, height


def _request_json(url: str, method: str = "GET", payload: dict | None = None) -> dict:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
    request = urllib.request.Request(
        url, data=body, method=method,
        headers={
            "apikey": AI_HORDE_IMAGE_API_KEY,
            "Client-Agent": "LailaTelegramBot:1.0",
            "User-Agent": "Mozilla/5.0 (compatible; LailaTelegramBot/1.0)",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            raw = response.read()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:1500]
        raise RuntimeError(f"AI Horde HTTP {exc.code}: {detail or exc.reason}") from exc
    try:
        return json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError("AI Horde geçersiz JSON yanıtı döndürdü.") from exc


def _download_image(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(request, timeout=90) as response:
        image = response.read()
    if not image:
        raise RuntimeError("AI Horde görsel bağlantısı boş içerik döndürdü.")
    return image


def ai_horde_img2img_sync(prompt: str, seed: int, reference_image: bytes) -> bytes:
    """Submit img2img to the selected model, wait for completion, and fetch the image."""
    if AI_HORDE_IMAGE_API_KEY == "0000000000":
        raise RuntimeError(
            "Yüz referansları anonim AI Horde isteklerinde herkese açık veri kümesiyle paylaşılabilir. "
            "Önce kayıtlı bir AI Horde anahtarını AI_HORDE_IMAGE_API_KEY olarak ayarla."
        )
    source_webp, width, height = _source_to_webp(reference_image)
    payload = {
        "prompt": prompt,
        "params": {
            "steps": IMAGE_STEPS,
            "cfg_scale": IMAGE_CFG_SCALE,
            "denoising_strength": IMAGE_DENOISING_STRENGTH,
            "width": width,
            "height": height,
            "seed": str(seed),
        },
        "models": [AI_HORDE_IMAGE_MODEL],
        "source_image": base64.b64encode(source_webp).decode("ascii"),
        "source_processing": "img2img",
        "nsfw": True,
        "trusted_workers": True,
        "shared": False,
    }
    submitted = _request_json(f"{AI_HORDE_URL}/generate/async", method="POST", payload=payload)
    request_id = submitted.get("id")
    if not request_id:
        raise RuntimeError(f"AI Horde üretim isteği kabul edilmedi: {submitted.get('message') or submitted}")
    if submitted.get("is_possible") is False:
        raise RuntimeError(f"AI Horde isteği karşılayamıyor: {submitted.get('message', 'uygun işçi yok')}")

    deadline = time.monotonic() + AI_HORDE_IMAGE_MAX_WAIT
    while time.monotonic() < deadline:
        time.sleep(IMAGE_POLL_INTERVAL)
        status = _request_json(f"{AI_HORDE_URL}/generate/status/{request_id}")
        if status.get("faulted"):
            raise RuntimeError(f"AI Horde görsel üretimi başarısız oldu: {status.get('generations') or status}")
        if status.get("done"):
            generations = status.get("generations") or []
            image_url = generations[0].get("img") if generations else None
            if not image_url:
                raise RuntimeError("AI Horde işi tamamlandı ancak görsel döndürmedi.")
            return _download_image(image_url)

    raise TimeoutError(f"AI Horde img2img {AI_HORDE_IMAGE_MAX_WAIT} saniyede tamamlanmadı.")


def cloudflare_img2img_sync(prompt: str, seed: int, reference_image: bytes) -> bytes:
    """Generate or edit an image with Cloudflare Workers AI using a face reference."""
    if not CF_AKTIF:
        raise RuntimeError("Cloudflare fotoğraf üretimi için hesap kimliği ve API tokenı gerekli.")
    with Image.open(BytesIO(reference_image)) as opened:
        source = ImageOps.exif_transpose(opened).convert("RGB")
    source.thumbnail((512, 512), Image.Resampling.LANCZOS)
    output = BytesIO()
    source.save(output, format="WEBP", quality=90, method=4)
    reference = output.getvalue()

    boundary = "----LailaWorkersAI" + secrets.token_hex(12)
    chunks = []

    def field(name: str, value: str) -> None:
        chunks.extend((
            f"--{boundary}\r\n".encode(),
            f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode(),
            str(value).encode("utf-8"), b"\r\n",
        ))

    field("prompt", prompt)
    field("width", "1024")
    field("height", "1024")
    field("seed", str(seed))
    chunks.extend((
        f"--{boundary}\r\n".encode(),
        b'Content-Disposition: form-data; name="input_image_0"; filename="reference.webp"\r\n',
        b"Content-Type: image/webp\r\n\r\n", reference, b"\r\n",
        f"--{boundary}--\r\n".encode(),
    ))
    body = b"".join(chunks)
    url = (
        f"https://api.cloudflare.com/client/v4/accounts/{CF_ACCOUNT_ID}"
        f"/ai/run/{CF_IMAGE_MODEL}"
    )
    request = urllib.request.Request(
        url, data=body, method="POST",
        headers={
            "Authorization": f"Bearer {CF_API_TOKEN}",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "Accept": "application/json, image/*",
            "User-Agent": "Mozilla/5.0 (compatible; LailaTelegramBot/1.0)",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            raw = response.read()
            content_type = response.headers.get("Content-Type", "")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:1000]
        raise RuntimeError(f"Cloudflare Workers AI HTTP {exc.code}: {detail or exc.reason}") from exc
    if content_type.startswith("image/"):
        image = raw
    else:
        try:
            data = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise RuntimeError("Cloudflare Workers AI geçersiz yanıt döndürdü.") from exc
        result = data.get("result", data) if isinstance(data, dict) else {}
        encoded = result.get("image") if isinstance(result, dict) else None
        if not encoded:
            detail = data.get("errors") or data.get("error") or "yanıtta image alanı yok"
            raise RuntimeError(f"Cloudflare Workers AI görsel üretmedi: {detail}")
        try:
            image = base64.b64decode(encoded)
        except Exception as exc:
            raise RuntimeError("Cloudflare Workers AI görsel verisi çözümlenemedi.") from exc
    if not image:
        raise RuntimeError("Cloudflare Workers AI boş görsel döndürdü.")
    return image


async def foto_uret_bytes(
    karakter: dict, seed: int, yakinlik: int = 0, surpriz: bool = False,
    reference_image: bytes = None, scene_prompt: str = "",
) -> bytes:
    """Generate a character-consistent img2img photo; failures are returned to the caller."""
    if not reference_image:
        raise RuntimeError("Bu karakter için yüz referansı kayıtlı değil. Önce karaktere ait bir fotoğraf yükle.")
    prompt = foto_promptu(karakter, yakinlik=yakinlik, surpriz=surpriz)
    if scene_prompt:
        prompt = (
            f"{prompt} Scene/action to depict: {scene_prompt}. "
            "Preserve the same adult woman's facial identity from the input image."
        )
    else:
        prompt = "Preserve the same adult woman's facial identity from the input image. " + prompt
    if CF_AKTIF:
        try:
            image = await asyncio.to_thread(
                cloudflare_img2img_sync, prompt, seed, reference_image
            )
            logging.info("Fotoğraf Cloudflare Workers AI üzerinden üretildi.")
            return image
        except Exception as exc:
            logging.warning("Cloudflare fotoğraf üretimi başarısız; AI Horde deneniyor: %s", exc)
    return await asyncio.to_thread(ai_horde_img2img_sync, prompt, seed, reference_image)
