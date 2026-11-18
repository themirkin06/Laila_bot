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
from characters import foto_istegindeki_kiyafeti_bul, foto_promptu, tam_boy_istendi_mi

AI_HORDE_URL = "https://aihorde.net/api/v2"
IMAGE_STEPS = 25
IMAGE_CFG_SCALE = 6
# Conservative img2img strengths preserve face identity while allowing outfit edits.
IMAGE_DENOISING_STRENGTH = 0.42
IMAGE_CLOTHING_DENOISING_STRENGTH = 0.47
IMAGE_FULL_BODY_DENOISING_STRENGTH = 0.50
IMAGE_POLL_INTERVAL = 3
IMAGE_MAX_EDGE = 1024


def _source_to_webp(reference_image: bytes, full_length: bool = False) -> tuple[bytes, int, int]:
    """Normalize a reference; use a portrait canvas when head-to-toe framing is requested."""
    if not reference_image:
        raise ValueError("AI Horde img2img için karakterin yüz referansı gerekli.")
    try:
        with Image.open(BytesIO(reference_image)) as opened:
            source = ImageOps.exif_transpose(opened).convert("RGB")
    except Exception as exc:
        raise ValueError("Karakterin yüz referansı okunamadı; geçerli bir fotoğraf yükle.") from exc

    if full_length:
        # Keep the identity reference in the upper frame and leave room below for legs and feet.
        width, height = 768, IMAGE_MAX_EDGE
        reference_height = round((height * 0.625) / 64) * 64
        contained = ImageOps.contain(
            source, (width, reference_height), method=Image.Resampling.LANCZOS
        )
        canvas = Image.new("RGB", (width, height), (127, 127, 127))
        canvas.paste(contained, ((width - contained.width) // 2, 64))
        output = BytesIO()
        canvas.save(output, format="WEBP", quality=92, method=4)
        return output.getvalue(), width, height
    else:
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


def ai_horde_img2img_sync(
    prompt: str, seed: int, reference_image: bytes = None,
    denoising_strength: float = IMAGE_DENOISING_STRENGTH, full_length: bool = False,
) -> bytes:
    """Use img2img when a face reference exists; otherwise generate from the character prompt."""
    if reference_image and AI_HORDE_IMAGE_API_KEY == "0000000000":
        raise RuntimeError(
            "Yüz referansları anonim AI Horde isteklerinde herkese açık veri kümesiyle paylaşılabilir. "
            "Önce kayıtlı bir AI Horde anahtarını AI_HORDE_IMAGE_API_KEY olarak ayarla."
        )
    if reference_image:
        source_webp, width, height = _source_to_webp(reference_image, full_length=full_length)
    else:
        width, height = (768, 1024) if full_length else (768, 768)
        source_webp = None

    params = {
        "steps": IMAGE_STEPS,
        "cfg_scale": IMAGE_CFG_SCALE,
        "width": width,
        "height": height,
        "seed": str(seed),
    }
    payload = {
        "prompt": prompt,
        "params": params,
        "models": [AI_HORDE_IMAGE_MODEL],
        "nsfw": True,
        "trusted_workers": True,
        "shared": False,
    }
    if reference_image:
        params["denoising_strength"] = denoising_strength
        payload["source_image"] = base64.b64encode(source_webp).decode("ascii")
        payload["source_processing"] = "img2img"

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


def _denoising_strength(scene_prompt: str) -> float:
    if tam_boy_istendi_mi(scene_prompt):
        return IMAGE_FULL_BODY_DENOISING_STRENGTH
    if foto_istegindeki_kiyafeti_bul(scene_prompt):
        return IMAGE_CLOTHING_DENOISING_STRENGTH
    return IMAGE_DENOISING_STRENGTH


def cloudflare_img2img_sync(
    prompt: str, seed: int, reference_image: bytes, full_length: bool = False,
) -> bytes:
    """Generate or edit an image with Cloudflare Workers AI using a face reference."""
    if not CF_AKTIF:
        raise RuntimeError("Cloudflare fotoğraf üretimi için hesap kimliği ve API tokenı gerekli.")
    reference, width, height = _source_to_webp(reference_image, full_length=full_length)

    boundary = "----LailaWorkersAI" + secrets.token_hex(12)
    chunks = []

    def field(name: str, value: str) -> None:
        chunks.extend((
            f"--{boundary}\r\n".encode(),
            f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode(),
            str(value).encode("utf-8"), b"\r\n",
        ))

    field("prompt", prompt)
    field("width", str(width))
    field("height", str(height))
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
    """Use the character prompt for text-to-image, and preserve identity when a reference exists."""
    prompt = foto_promptu(
        karakter, yakinlik=yakinlik, surpriz=surpriz, scene_prompt=scene_prompt
    )
    full_length = tam_boy_istendi_mi(scene_prompt)
    denoising_strength = _denoising_strength(scene_prompt)
    if reference_image:
        prompt = (
            "Preserve exactly the same adult woman's recognizable facial identity from the input image: "
            "same age and apparent age, face shape, eye shape and color, nose, skin tone, and distinguishing features. "
            "Do not beautify into a different person or make her look younger. "
            + prompt
        )
        if CF_AKTIF:
            try:
                image = await asyncio.to_thread(
                    cloudflare_img2img_sync, prompt, seed, reference_image, full_length
                )
                logging.info("Fotoğraf Cloudflare Workers AI üzerinden üretildi.")
                return image
            except Exception as exc:
                logging.warning("Cloudflare fotoğraf üretimi başarısız; AI Horde deneniyor: %s", exc)
        logging.info(
            "AI Horde img2img framing=%s denoising_strength=%.2f",
            "full-length" if full_length else "standard", denoising_strength,
        )
    else:
        logging.info("Yüz referansı yok; karakter promptuyla AI Horde text-to-image kullanılacak.")
    return await asyncio.to_thread(
        ai_horde_img2img_sync, prompt, seed, reference_image, denoising_strength, full_length
    )
