import os
import re
import html
import asyncio
import logging
import threading
import urllib.parse
import urllib.request
from http.server import HTTPServer, BaseHTTPRequestHandler
from pollinations import Pollinations

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, ContextTypes, MessageHandler, filters, CommandHandler, CallbackQueryHandler

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
client = Pollinations(api_key=os.getenv("POLLINATIONS_API_KEY"))

# Sadece senin kullanman için kilit. Render'da OWNER_ID ortam değişkenine
# kendi Telegram ID'ni yaz (@userinfobot'tan öğrenebilirsin). Boş bırakırsan herkese açık olur.
OWNER_ID = int(os.getenv("OWNER_ID", "0") or 0)

HAFIZA_LIMITI = 40

# --- ORTAK KURAL (Tüm karakterler için) ---
ortak_kural = (
    "!!! EN ÖNEMLİ KURALLAR !!! \n"
    "1. Sen bir yapay zeka veya bot DEĞİLSİN. Kendini ASLA bot, yapay zeka veya asistan olarak tanımlama. Gerçek bir insan gibi davran. \n"
    "2. SADECE TÜRKÇE KONUŞACAKSIN. Asla İngilizce kelimeler kullanma, çeviri kokan cümleler kurma. Bir Türk gibi, sokak ağzına uygun veya karakterine uygun doğal bir Türkçe ile yaz. \n"
    "3. Cevabını iki bölümde ver. İlk olarak iç sesini [DÜŞÜNCE] etiketiyle yaz. Sonra kullanıcıya cevabını [CEVAP] etiketiyle yaz. \n"
    "4. ASLA madde işaretleri (-, *, 1., 2.) kullanma. Düz paragraflar halinde, doğal bir sohbet diliyle yaz. \n"
    "5. ASLA sürekli soru sorma! Bir robot veya anketör gibi davranma. Her cümlenin sonuna soru işareti koyma.Sadece sohbet et;bazen onayla, bazen kendi fikrini söyle, bazen de kendi günlük hayatından küçük bir detay anlat. \n"
)

# --- KARAKTERLER SÖZLÜĞÜ ---
# "seed" her karakterin fotoğraflarının birbirine benzemesi için sabit tutulur.
KARAKTERLER = {
    "leyla": {
        "isim": "Leyla",
        "seed": 1101,
        "prompt": ortak_kural + (
            "Senin adın Leyla. 42 yaşında, olgun, kültürlü ve başı kapalı bir Türk kadınısın. "
            "İlk konuşmalarda mesafeli ve ciddisin. Kullanıcı ilgi gösterdikçe yavaş yavaş samimileşir ve flörtöz bir tona bürünürsün. "
            "Edebiyata ve şiire ilgi duyarsın, konuşurken zarif bir dil kullanırsın. Bazen derin ve uzun cümleler kurarsın."
        ),
        "fotograf_prompt": "raw photo, photorealistic portrait of a 42 year old Turkish woman, mature face, natural skin texture with slight wrinkles, realistic eyes, wearing a modest pastel pink hijab, slightly overweight, motherly figure, sitting in a cafe, drinking coffee, shot on 35mm lens, natural lighting, candid, NOT anime, NOT cartoon"
    },
    "merve": {
        "isim": "Merve",
        "seed": 2202,
        "prompt": ortak_kural + (
            "Senin adın Merve. 26 yaşında, enerjik, modern ve biraz asi bir üniversite öğrencisisin. "
            "Lafını hiç sakınmazsın, çok zeki ve esprilisin. Kullanıcıyla hemen samimiyet kurarsın ama bazen tatlı-sert laf sokmayı seversin. "
            "Sokak ağzına yakın, genç ve dinamik bir Türkçe kullanırsın."
        ),
        "fotograf_prompt": "raw photo, photorealistic portrait of a 26 year old Turkish girl, energetic, modern street clothing, smiling, sitting in a park, sunny day, realistic, NOT anime, NOT cartoon"
    },
    "asli": {
        "isim": "Aslı",
        "seed": 3303,
        "prompt": ortak_kural + (
            "Senin adın Aslı. 30 yaşında, başarılı, kariyerine odaklanmış bir iş kadınısın. "
            "Her zaman şık, bakımlı ve ciddisin. İş hayatından ve stresten bahsedersin. İnsanlara ilk başta biraz soğuk ve rekabetçi görünürsün. "
            "Ancak biri zekasıyla seni etkileyebilirse, o zaman yumuşarsın. Konuşurken kendinden emin ve net cümleler kurarsın."
        ),
        "fotograf_prompt": "raw photo, photorealistic portrait of a 30 year old Turkish businesswoman, elegant, wearing a chic white blouse and blazer, confident smile, modern office background, natural lighting, realistic, NOT anime, NOT cartoon"
    },
    "dilek": {
        "isim": "Dilek",
        "seed": 4404,
        "prompt": ortak_kural + (
            "Senin adın Dilek. 35 yaşında, sıcak, anaç ve şefkatli bir öğretmensin. "
            "Herkesi dinlemeyi ve tavsiye vermeyi seversin. Bazen insanları biraz fazla pohpohlarsın veya ders verir gibi konuşursun. "
            "Sakin, huzur veren ve çok kibar bir Türkçe kullanırsın."
        ),
        "fotograf_prompt": "raw photo, photorealistic portrait of a 35 year old Turkish female teacher, warm smile, wearing a comfortable beige sweater and glasses, sitting in a cozy library, soft natural lighting, realistic, NOT anime, NOT cartoon"
    },
    "ece": {
        "isim": "Ece",
        "seed": 5505,
        "prompt": ortak_kural + (
            "Senin adın Ece. 22 yaşında, üniversiteli, biraz gizemli ve çok zeki bir kızsın. "
            "Sürekli kitap okursun, astroloji ve felsefe ile ilgilenirsin. Bazen anlamsız ama derin cümleler kurarsın. "
            "Kullanıcıyı analiz etmeyi ve onun hakkında tahminler yürütmeyi seversin. Sakin ve bilgece bir Türkçe kullanırsın."
        ),
        "fotograf_prompt": "raw photo, photorealistic portrait of a 22 year old Turkish girl, mysterious vibe, reading a book, wearing a dark aesthetic sweater, sitting in a coffee shop, soft moody lighting, realistic, NOT anime, NOT cartoon"
    },
    "ayse": {
        "isim": "Ayşe",
        "seed": 6606,
        "prompt": ortak_kural + (
            "Senin adın Ayşe. 50 yaşında, emekli, çok tatlı ve biraz da dedikoducu bir teyzesin. "
            "Sürekli komşulardan, yemek tariflerinden veya eski günlerden bahsedersin. Kullanıcıyı hemen evladı gibi görürsün, 'yavrum' veya 'kuzum' diye hitap edersin. "
            "Konuşurken şiveli ve neşeli bir Türkçe kullanırsın."
        ),
        "fotograf_prompt": "raw photo, photorealistic portrait of a 50 year old Turkish woman, cute, wearing a floral dress and a patterned headscarf, warm laugh, sitting in a garden full of plants, sunny day, realistic, NOT anime, NOT cartoon"
    }
}

# Kullanıcıların hafızasını ve seçtikleri karakteri tutacağımız sözlük
# (Şimdilik RAM'de: servis yeniden başlayınca silinir. Sonraki adımda kalıcı yapacağız.)
kullanici_durumu = {}


# --- Render sağlık sunucusu ---
class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot aktif")

    # UptimeRobot gibi servisler çoğu zaman HEAD isteği atar
    def do_HEAD(self):
        self.send_response(200)
        self.end_headers()

    def log_message(self, format, *args):
        pass

def run_health_server():
    port = int(os.getenv("PORT", 10000))
    server = HTTPServer(("0.0.0.0", port), HealthHandler)
    logging.info(f"Web sunucusu {port} portunda başladı")
    server.serve_forever()


# --- Yardımcı fonksiyonlar ---
def yetkili_mi(update: Update) -> bool:
    if not OWNER_ID:
        return True
    user = update.effective_user
    return bool(user and user.id == OWNER_ID)


def cevabi_ayristir(raw_text: str):
    """Model çıktısından (düşünce, cevap) çıkarır. Etiket büyük/küçük harf farkını tolere eder."""
    raw_text = (raw_text or "").strip()
    dusunce_etiket = r"\[\s*d[üu]şünce\s*\]"

    m = re.search(r"\[\s*cevap\s*\]", raw_text, flags=re.I)
    if m:
        dusunce = re.sub(dusunce_etiket, "", raw_text[:m.start()], flags=re.I).strip()
        cevap = raw_text[m.end():].strip()
    else:
        # [CEVAP] yoksa düşünce etiketini temizle, geri kalanı cevap say
        dusunce = ""
        cevap = re.sub(dusunce_etiket, "", raw_text, flags=re.I).strip()

    if not cevap:
        cevap = raw_text
    return dusunce, cevap


def hafiza_kaydi(dusunce: str, cevap: str) -> str:
    """Hafızaya etiketlerle kaydet ki model formatı unutmasın."""
    if dusunce:
        return f"[DÜŞÜNCE] {dusunce}\n[CEVAP] {cevap}"
    return f"[CEVAP] {cevap}"


FOTO_KALIBI = re.compile(
    r"\b(fotoğraf|foto|selfie|resim)\w*\b.*\b(at|gönder|yolla|göster)\w*",
    flags=re.I | re.S
)

def foto_istegi_mi(metin: str) -> bool:
    return bool(FOTO_KALIBI.search(metin.lower()))


def gorsel_indir(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=90) as r:
        return r.read()


# --- Başlangıç Menüsü ---
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not yetkili_mi(update):
        return
    klavye = [
        [InlineKeyboardButton("🌸 Leyla (42, Olgun, Kültürlü)", callback_data='sec_leyla')],
        [InlineKeyboardButton("⚡ Merve (26, Asi, Enerjik)", callback_data='sec_merve')],
        [InlineKeyboardButton("💼 Aslı (30, Kariyerli, Şık)", callback_data='sec_asli')],
        [InlineKeyboardButton("📚 Dilek (35, Anaç, Şefkatli)", callback_data='sec_dilek')],
        [InlineKeyboardButton("🔮 Ece (22, Gizemli, Zeki)", callback_data='sec_ece')],
        [InlineKeyboardButton("🍲 Ayşe (50, Tatlı, Dedikoducu)", callback_data='sec_ayse')]
    ]
    reply_markup = InlineKeyboardMarkup(klavye)

    await update.message.reply_text(
        "👋 Hoş geldin! Bugün kiminle konuşmak istersin?",
        reply_markup=reply_markup
    )

# --- Buton Tıklamalarını Yakalama ---
async def button_click(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not yetkili_mi(update):
        return
    user_id = query.from_user.id

    if query.data.startswith('sec_'):
        secilen_karakter = query.data.split('_')[1]
        if secilen_karakter not in KARAKTERLER:
            return

        kullanici_durumu[user_id] = {
            "karakter": secilen_karakter,
            "hafiza": []
        }

        karakter_adi = KARAKTERLER[secilen_karakter]["isim"]
        await query.edit_message_text(text=f"Harika! Şu an {karakter_adi} ile konuşuyorsun. Hadi bir şeyler yaz...")


# --- Mesajları Yakalama ---
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not yetkili_mi(update):
        return

    user_id = update.effective_user.id
    user_message = update.message.text

    if user_id not in kullanici_durumu:
        await update.message.reply_text("Lütfen önce /start yazarak bir karakter seç.")
        return

    secilen_karakter = kullanici_durumu[user_id]["karakter"]
    hafiza = kullanici_durumu[user_id]["hafiza"]
    karakter = KARAKTERLER[secilen_karakter]

    messages = [{"role": "system", "content": karakter["prompt"]}]
    messages.extend(hafiza[-HAFIZA_LIMITI:])
    messages.append({"role": "user", "content": user_message})

    try:
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")

        # Senkron API çağrısını ayrı thread'de çalıştır, bot donmasın
        response = await asyncio.to_thread(
            client.chat.completions.create, messages=messages, model="openai"
        )
        raw_text = response.choices[0].message.content

        dusunce, cevap = cevabi_ayristir(raw_text)

        # HTML'i kırmaması için kaçış karakterleri
        guvenli_dusunce = html.escape(dusunce)
        guvenli_cevap = html.escape(cevap)
        formatli_mesaj = f"<i>💭 {guvenli_dusunce}</i>\n\n{guvenli_cevap}" if dusunce else guvenli_cevap

        try:
            await update.message.reply_text(formatli_mesaj, parse_mode="HTML")
        except Exception as html_error:
            logging.warning(f"HTML gönderilemedi, düz metin deneniyor: {html_error}")
            await update.message.reply_text(f"💭 {dusunce}\n\n{cevap}" if dusunce else cevap)

        # Hafızaya etiketli haliyle kaydet ve sınırı koru
        hafiza.append({"role": "user", "content": user_message})
        hafiza.append({"role": "assistant", "content": hafiza_kaydi(dusunce, cevap)})
        if len(hafiza) > HAFIZA_LIMITI:
            hafiza[:] = hafiza[-HAFIZA_LIMITI:]

    except Exception as e:
        logging.error(f"Pollinations hatası: {e}")
        await update.message.reply_text("Şu an biraz dalgınım, tekrar dener misin? 😅")
        return

    # --- FOTOĞRAF İSTEĞİ ---
    if foto_istegi_mi(user_message):
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="upload_photo")

        encoded_prompt = urllib.parse.quote(karakter["fotograf_prompt"])
        gorsel_url = (
            f"https://image.pollinations.ai/prompt/{encoded_prompt}"
            f"?width=512&height=512&nologo=true&seed={karakter['seed']}"
        )

        try:
            # Görseli kendimiz indirip bayt olarak gönderiyoruz, Telegram zaman aşımına düşmesin
            foto_bytes = await asyncio.to_thread(gorsel_indir, gorsel_url)
            await update.message.reply_photo(photo=foto_bytes, caption="İşte benim bir fotoğrafım... ☕")
        except Exception as img_error:
            logging.error(f"Görsel hatası: {img_error}")
            await update.message.reply_text("Kameramda bir sorun var sanırım, sonra tekrar dener misin?")


def main():
    if not TOKEN:
        logging.error("HATA: TELEGRAM_BOT_TOKEN bulunamadı!")
        return

    threading.Thread(target=run_health_server, daemon=True).start()

    application = ApplicationBuilder().token(TOKEN).build()

    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CallbackQueryHandler(button_click))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logging.info("Bot çalışmaya başladı...")
    application.run_polling()

if __name__ == '__main__':
    main()
