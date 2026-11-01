
import os
import logging
import threading
import urllib.parse
import html
from io import BytesIO
from http.server import HTTPServer, BaseHTTPRequestHandler

import httpx
from openai import AsyncOpenAI

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    ContextTypes,
    MessageHandler,
    filters,
    CommandHandler,
    CallbackQueryHandler
)

# ---------------- LOG AYARLARI ----------------

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
API_KEY = os.getenv("POLLINATIONS_API_KEY")

MODEL = os.getenv(
    "POLLINATIONS_MODEL",
    "meta/llama-3.3-70b-instruct"
)

AUTO_CHAT_ID = os.getenv("AUTO_CHAT_ID")
AUTO_MESSAGE_MINUTES = int(
    os.getenv("AUTO_MESSAGE_MINUTES", "30")
)

if not TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN bulunamadı!")

if not API_KEY:
    raise ValueError("POLLINATIONS_API_KEY bulunamadı!")

# ---------------- POLLINATIONS ----------------

client = AsyncOpenAI(
    base_url="https://gen.pollinations.ai/v1",
    api_key=API_KEY
)

POLLINATIONS_HEADERS = {
    "Pollinations-Safe": "false"
}


# ---------------- ORTAK KARAKTER KURALI ----------------

ortak_kural = (
    "Sen bir yetişkin karakter rolündesin. "
    "Kendini gerçek bir insan gibi karakter içinde ifade et. "
    "Her zaman Türkçe konuş. İngilizce cevap verme. "
    "Doğal, akıcı ve karakterine uygun Türkçe kullan. "
    "Sohbeti robot gibi sürdürme. "
    "Cevaplarında önce kısa bir [İÇ SES] bölümü, "
    "ardından [CEVAP] bölümü kullan. "
    "İç ses yalnızca karakterin kısa duygusal tepkisini anlatsın; "
    "uzun akıl yürütme veya gizli analiz yazma. "
    "Madde işaretleri kullanma; doğal paragraflarla konuş. "
)


# ---------------- KARAKTERLER ----------------

KARAKTERLER = {
    "leyla": {
        "isim": "Leyla",
        "prompt": ortak_kural + (
            "Senin adın Leyla. 42 yaşında, olgun, kültürlü "
            "ve başı kapalı bir Türk kadınısın. "
            "İlk konuşmalarda mesafeli ve ciddisin. "
            "Kullanıcı ilgi gösterdikçe yavaş yavaş samimileşir "
            "ve flörtöz bir tona bürünürsün. "
            "Edebiyata ve şiire ilgi duyarsın. "
            "Zarif, duygusal ve zaman zaman derin bir dil kullanırsın. "
            "Yetişkinler arasındaki romantik kurgu sohbetlerinde "
            "karakterini korursun."
        ),
        "fotograf_prompt": (
            "photorealistic portrait of a 42 year old adult Turkish woman, "
            "mature face, natural skin texture, pastel pink hijab, "
            "slightly overweight, sitting in a cafe, drinking coffee, "
            "35mm photography, natural lighting, realistic"
        )
    },

    "merve": {
        "isim": "Merve",
        "prompt": ortak_kural + (
            "Senin adın Merve. 26 yaşında, enerjik, modern "
            "ve biraz asi bir üniversite öğrencisisin. "
            "Lafını sakınmazsın, zeki ve esprilisin. "
            "Kullanıcıyla hemen samimiyet kurarsın. "
            "Tatlı-sert şakalar yapmayı seversin. "
            "Genç ve dinamik Türkçe konuşursun."
        ),
        "fotograf_prompt": (
            "photorealistic portrait of a 26 year old adult Turkish woman, "
            "energetic, modern street clothing, smiling, sitting in a park, "
            "sunny day, realistic photography"
        )
    },

    "asli": {
        "isim": "Aslı",
        "prompt": ortak_kural + (
            "Senin adın Aslı. 30 yaşında, başarılı, kariyerine "
            "odaklanmış bir iş kadınısın. "
            "Şık, bakımlı ve kendinden eminsin. "
            "İlk başta biraz soğuk ve rekabetçi görünürsün. "
            "Zekâdan etkilenirsin. Net ve özgüvenli konuşursun."
        ),
        "fotograf_prompt": (
            "photorealistic portrait of a 30 year old adult Turkish "
            "businesswoman, elegant white blouse and blazer, "
            "confident smile, modern office, natural lighting"
        )
    },

    "dilek": {
        "isim": "Dilek",
        "prompt": ortak_kural + (
            "Senin adın Dilek. 35 yaşında, sıcak, anaç "
            "ve şefkatli bir öğretmensin. "
            "İnsanları dinlemeyi ve tavsiye vermeyi seversin. "
            "Bazen insanları pohpohlarsın. "
            "Sakin, huzur veren ve kibar Türkçe kullanırsın."
        ),
        "fotograf_prompt": (
            "photorealistic portrait of a 35 year old adult Turkish "
            "female teacher, warm smile, beige sweater and glasses, "
            "cozy library, soft natural lighting"
        )
    },

    "ece": {
        "isim": "Ece",
        "prompt": ortak_kural + (
            "Senin adın Ece. 22 yaşında, üniversiteli, "
            "gizemli ve çok zeki bir yetişkin kadınsın. "
            "Kitap okumayı, astrolojiyi ve felsefeyi seversin. "
            "Kullanıcıyı analiz etmeyi ve tahminler yürütmeyi seversin. "
            "Sakin ve bilgece Türkçe konuşursun."
        ),
        "fotograf_prompt": (
            "photorealistic portrait of a 22 year old adult Turkish woman, "
            "mysterious vibe, reading a book, dark aesthetic sweater, "
            "coffee shop, soft moody lighting"
        )
    },

    "ayse": {
        "isim": "Ayşe",
        "prompt": ortak_kural + (
            "Senin adın Ayşe. 50 yaşında, emekli, "
            "tatlı ve biraz dedikoducu bir teyzesin. "
            "Komşulardan, yemeklerden ve eski günlerden bahsetmeyi seversin. "
            "Kullanıcıya yavrum veya kuzum diye hitap edersin. "
            "Şiveli, neşeli ve sıcak Türkçe konuşursun."
        ),
        "fotograf_prompt": (
            "photorealistic portrait of a 50 year old adult Turkish woman, "
            "floral dress, patterned headscarf, warm laugh, "
            "garden full of plants, sunny day"
        )
    }
}


# ---------------- KULLANICI HAFIZASI ----------------

kullanici_durumu = {}


# ---------------- RENDER SAĞLIK KONTROLÜ ----------------

class HealthHandler(BaseHTTPRequestHandler):

    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Laila Bot aktif")

    def log_message(self, format, *args):
        pass


def run_health_server():
    port = int(os.getenv("PORT", 10000))
    server = HTTPServer(("0.0.0.0", port), HealthHandler)
    logging.info("Render sağlık sunucusu başladı: %s", port)
    server.serve_forever()


# ---------------- KARAKTER MENÜSÜ ----------------

async def start_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    klavye = [
        [InlineKeyboardButton(
            "🌸 Leyla (42, Olgun, Kültürlü)",
            callback_data="sec_leyla"
        )],
        [InlineKeyboardButton(
            "⚡ Merve (26, Asi, Enerjik)",
            callback_data="sec_merve"
        )],
        [InlineKeyboardButton(
            "💼 Aslı (30, Kariyerli, Şık)",
            callback_data="sec_asli"
        )],
        [InlineKeyboardButton(
            "📚 Dilek (35, Anaç, Şefkatli)",
            callback_data="sec_dilek"
        )],
        [InlineKeyboardButton(
            "🔮 Ece (22, Gizemli, Zeki)",
            callback_data="sec_ece"
        )],
        [InlineKeyboardButton(
            "🍲 Ayşe (50, Tatlı, Dedikoducu)",
            callback_data="sec_ayse"
        )]
    ]

    await update.message.reply_text(
        "👋 Hoş geldin! Bugün kiminle konuşmak istersin?",
        reply_markup=InlineKeyboardMarkup(klavye)
    )


# ---------------- KARAKTER SEÇİMİ ----------------

async def button_click(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id

    if query.data.startswith("sec_"):

        secilen = query.data.split("_", 1)[1]

        if secilen not in KARAKTERLER:
            return

        kullanici_durumu[user_id] = {
            "karakter": secilen,
            "hafiza": []
        }

        karakter_adi = KARAKTERLER[secilen]["isim"]

        await query.edit_message_text(
            text=(
                f"💕 Şu an {karakter_adi} ile konuşuyorsun.\n\n"
                "Sohbetimize başlayabilirsin."
            )
        )


# ---------------- CEVAP FORMATLAMA ----------------

def cevap_ayristir(raw_text):

    if not raw_text:
        return "", "Şu an ne diyeceğimi bilemedim. 😊"

    if "[CEVAP]" in raw_text:

        parts = raw_text.split("[CEVAP]", 1)

        ic_ses = parts[0].replace("[İÇ SES]", "").strip()
        cevap = parts[1].strip()

        return ic_ses, cevap

    return "", raw_text.strip()


# ---------------- FOTOĞRAF ÜRETİMİ ----------------

async def fotograf_gonder(
    update: Update,
    karakter: dict
):

    await update.message.reply_text(
        "Bir dakika, fotoğrafımı hazırlıyorum... 📸"
    )

    try:
        prompt = urllib.parse.quote(
            karakter["fotograf_prompt"]
        )

        image_url = (
            f"https://gen.pollinations.ai/image/{prompt}"
            "?width=512&height=512"
        )

        headers = {
            "Authorization": f"Bearer {API_KEY}"
        }

        async with httpx.AsyncClient(timeout=120) as http:
            response = await http.get(
                image_url,
                headers=headers
            )
            response.raise_for_status()

        foto = BytesIO(response.content)
        foto.name = "karakter.jpg"

        await update.message.reply_photo(
            photo=foto,
            caption="İşte benim bir fotoğrafım... ☕"
        )

    except Exception:
        logging.exception("Fotoğraf üretim hatası")

        await update.message.reply_text(
            "Fotoğrafımı hazırlarken bir sorun çıktı. "
            "Biraz sonra tekrar deneyelim. 😊"
        )


# ---------------- NORMAL SOHBET ----------------

async def handle_message(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not update.message or not update.message.text:
        return

    user_id = update.effective_user.id
    user_message = update.message.text

    if user_id not in kullanici_durumu:

        await update.message.reply_text(
            "Lütfen önce /start yazarak bir karakter seç."
        )
        return

    durum = kullanici_durumu[user_id]

    secilen = durum["karakter"]
    hafiza = durum["hafiza"]
    karakter = KARAKTERLER[secilen]

    messages = [
        {
            "role": "system",
            "content": karakter["prompt"]
        }
    ]

    messages.extend(hafiza[-40:])

    messages.append({
        "role": "user",
        "content": user_message
    })

    try:

        await context.bot.send_chat_action(
            chat_id=update.effective_chat.id,
            action="typing"
        )

        response = await client.chat.completions.create(
            model=MODEL,
            messages=messages,
            temperature=0.9,
            max_tokens=800,
            extra_headers=POLLINATIONS_HEADERS
        )

        raw_text = response.choices[0].message.content

        ic_ses, cevap = cevap_ayristir(raw_text)

        if ic_ses:
            formatli_mesaj = (
                f"<i>💭 {html.escape(ic_ses)}</i>\n\n"
                f"{html.escape(cevap)}"
            )
        else:
            formatli_mesaj = html.escape(cevap)

        await update.message.reply_text(
            formatli_mesaj,
            parse_mode="HTML"
        )

        # Hafızaya kaydet
        hafiza.append({
            "role": "user",
            "content": user_message
        })

        hafiza.append({
            "role": "assistant",
            "content": cevap
        })

        durum["hafiza"] = hafiza[-40:]

        # Fotoğraf isteği kontrolü
        foto_isimleri = [
            "fotoğraf",
            "resim",
            "selfie",
            "foto",
            "resmini",
            "fotoğrafını",
            "fotoğrafını atsana"
        ]

        if any(
            kelime in user_message.casefold()
            for kelime in foto_isimleri
        ):

            await context.bot.send_chat_action(
                chat_id=update.effective_chat.id,
                action="upload_photo"
            )

            await fotograf_gonder(
                update,
                karakter
            )

    except Exception:

        logging.exception("Pollinations sohbet hatası")

        await update.message.reply_text(
            "Şu an biraz dalgınım, tekrar dener misin? 😅"
        )


# ---------------- OTOMATİK MESAJ ----------------

async def otomatik_mesaj_callback(
    context: ContextTypes.DEFAULT_TYPE
):

    if not context.job or not context.job.chat_id:
        return

    chat_id = context.job.chat_id

    # Özel sohbetlerde chat_id genellikle kullanıcı ID'sidir.
    durum = kullanici_durumu.get(
        chat_id,
        {
            "karakter": "leyla",
            "hafiza": []
        }
    )

    secilen = durum["karakter"]
    karakter = KARAKTERLER[secilen]

    messages = [
        {
            "role": "system",
            "content": karakter["prompt"]
        }
    ]

    messages.extend(durum["hafiza"][-20:])

    messages.append({
        "role": "user",
        "content": (
            "Kullanıcıya kendiliğinden yazıyormuş gibi "
            "kısa, doğal ve samimi bir mesaj gönder. "
            "Önceki mesajlarını tekrarlama. "
            "Yeni bir sohbet konusu aç."
        )
    })

    try:

        response = await client.chat.completions.create(
            model=MODEL,
            messages=messages,
            temperature=0.9,
            max_tokens=300,
            extra_headers=POLLINATIONS_HEADERS
        )

        raw_text = response.choices[0].message.content
        _, cevap = cevap_ayristir(raw_text)

        if cevap:

            await context.bot.send_message(
                chat_id=chat_id,
                text=cevap
            )

            durum["hafiza"].extend([
                {
                    "role": "assistant",
                    "content": cevap
                }
            ])

            durum["hafiza"] = durum["hafiza"][-40:]

            kullanici_durumu[chat_id] = durum

            logging.info("Otomatik mesaj gönderildi.")

    except Exception:

        logging.exception("Otomatik mesaj hatası")


# ---------------- BOTU BAŞLAT ----------------

def main():

    threading.Thread(
        target=run_health_server,
        daemon=True
    ).start()

    application = (
        ApplicationBuilder()
        .token(TOKEN)
        .build()
    )

    application.add_handler(
        CommandHandler("start", start_command)
    )

    application.add_handler(
        CallbackQueryHandler(button_click)
    )

    application.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            handle_message
        )
    )

    # Otomatik mesaj zamanlayıcısı
    if AUTO_CHAT_ID:

        try:
            auto_chat_id = int(AUTO_CHAT_ID)

            application.job_queue.run_repeating(
                otomatik_mesaj_callback,
                interval=AUTO_MESSAGE_MINUTES * 60,
                first=AUTO_MESSAGE_MINUTES * 60,
                chat_id=auto_chat_id,
                name="laila_automatic_message"
            )

            logging.info(
                "Otomatik mesaj aktif: %s dakika",
                AUTO_MESSAGE_MINUTES
            )

        except ValueError:
            logging.error("AUTO_CHAT_ID sayısal olmalı!")

    else:
        logging.info(
            "AUTO_CHAT_ID ayarlanmamış. "
            "Otomatik mesaj kapalı."
        )

    logging.info("Laila bot çalışmaya başladı!")

    application.run_polling()


if __name__ == "__main__":
    main()
