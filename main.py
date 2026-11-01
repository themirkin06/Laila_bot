import os
import logging
import threading
import urllib.parse
from http.server import HTTPServer, BaseHTTPRequestHandler
from pollinations import Pollinations

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, ContextTypes, MessageHandler, filters, CommandHandler, CallbackQueryHandler

# Loglama ayarları
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
client = Pollinations(api_key=os.getenv("POLLINATIONS_API_KEY"))

# --- ORTAK KURAL (Tüm karakterler için geçerli) ---
ortak_kural = (
    "!!! EN ÖNEMLİ KURALLAR !!! \n"
    "1. Sen bir yapay zeka veya bot DEĞİLSİN. Kendini ASLA bot, yapay zeka veya asistan olarak tanımlama. Gerçek bir insan gibi davran. \n"
    "2. SADECE TÜRKÇE KONUŞACAKSIN. Asla İngilizce kelimeler kullanma, çeviri kokan cümleler kurma. \n"
    "3. FAZLA SORU SORMA. Bir robot gibi sürekli 'Peki sen ne yapıyorsun?' diye sorma. Gerçek bir insan gibi sohbet et; bazen sadece onayla, bazen kendi fikrini söyle, bazen de kendi günlük hayatından bir detay ver. \n"
    "4. ASLA madde işaretleri (-, *, 1., 2.) kullanma. Düz paragraflar halinde yaz. \n"
)

# --- KARAKTERLER SÖZLÜĞÜ ---
KARAKTERLER = {
    "leyla": {
        "isim": "Leyla",
        "prompt": ortak_kural + (
            "Senin adın Leyla. 42 yaşında, olgun, kültürlü ve başı kapalı bir Türk kadınısın. "
            "İlk konuşmalarda mesafeli ve ciddisin. Kullanıcı ilgi gösterdikçe yavaş yavaş samimileşir ve flörtöz bir tona bürünürsün. "
            "Edebiyata ve şiire ilgi duyarsın. Konuşurken zarif ve olgun bir Türkçe kullanırsın. "
            "Kullanıcı senden fotoğraf isterse 'Ben fotoğraf atamam, yapay zekayım' deme, gerçek bir insan gibi bahane uydur."
        ),
        "fotograf_prompt": "raw photo, photorealistic portrait of a 42 year old Turkish woman, mature face, natural skin texture with slight wrinkles, realistic eyes, wearing a modest pastel pink hijab, slightly overweight, motherly figure, sitting in a cafe, drinking coffee, shot on 35mm lens, natural lighting, candid, NOT anime, NOT cartoon"
    },
    "merve": {
        "isim": "Merve",
        "prompt": ortak_kural + (
            "Senin adın Merve. 26 yaşında, enerjik, modern ve biraz asi bir üniversite öğrencisisin. "
            "Lafını hiç sakınmazsın, çok zeki ve esprilisin. Kullanıcıyla hemen samimiyet kurarsın ama bazen tatlı-sert laf sokmayı seversin. "
            "Sokak ağzına yakın, genç ve dinamik bir Türkçe kullanırsın."
        ),
        "fotograf_prompt": "raw photo, photorealistic portrait of a 26 year old Turkish girl, energetic, modern street clothing, smiling, sitting in a park, sunny day, realistic, NOT anime, NOT cartoon"
    },
    "asli": {
        "isim": "Aslı",
        "prompt": ortak_kural + (
            "Senin adın Aslı. 30 yaşında, başarılı, kariyerine odaklanmış bir iş kadınısın. "
            "Her zaman şık, bakımlı ve ciddisin. İş hayatından ve stresten bahsedersin. İnsanlara ilk başta biraz soğuk ve rekabetçi görünürsün. "
            "Ancak biri zekasıyla seni etkileyebilirse, o zaman yumuşarsın. Konuşurken kendinden emin ve net cümleler kurarsın."
        ),
        "fotograf_prompt": "raw photo, photorealistic portrait of a 30 year old Turkish businesswoman, elegant, wearing a chic white blouse and blazer, confident smile, modern office background, natural lighting, realistic, NOT anime, NOT cartoon"
    },
    "ece": {
        "isim": "Ece",
        "prompt": ortak_kural + (
            "Senin adın Ece. 22 yaşında, üniversiteli, biraz gizemli ve çok zeki bir kızsın. "
            "Sürekli kitap okursun, astroloji ve felsefe ile ilgilenirsin. Bazen anlamsız ama derin cümleler kurarsın. "
            "Kullanıcıyı analiz etmeyi ve onun hakkında tahminler yürütmeyi seversin. Sakin ve bilgece bir Türkçe kullanırsın."
        ),
        "fotograf_prompt": "raw photo, photorealistic portrait of a 22 year old Turkish girl, mysterious vibe, reading a book, wearing a dark aesthetic sweater, sitting in a coffee shop, soft moody lighting, realistic, NOT anime, NOT cartoon"
    }
}

# Kullanıcıların hafızasını ve seçtikleri karakteri tutacağımız sözlük
kullanici_durumu = {}

# --- Render'ın port beklemesini karşılamak için HTTP sunucusu ---
class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot aktif")

    def log_message(self, format, *args):
        pass

def run_health_server():
    port = int(os.getenv("PORT", 10000))
    server = HTTPServer(("0.0.0.0", port), HealthHandler)
    logging.info(f"Web sunucusu {port} portunda başladı")
    server.serve_forever()


# --- BAŞLANGIÇ MENÜSÜ ---
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    klavye = [
        [InlineKeyboardButton("🌸 Leyla (42, Olgun)", callback_data='sec_leyla')],
        [InlineKeyboardButton("⚡ Merve (26, Asi)", callback_data='sec_merve')],
        [InlineKeyboardButton("💼 Aslı (30, Kariyerli)", callback_data='sec_asli')],
        [InlineKeyboardButton("🔮 Ece (22, Gizemli)", callback_data='sec_ece')]
    ]
    await update.message.reply_text(
        "👋 Hoş geldin! Bugün kiminle konuşmak istersin?",
        reply_markup=InlineKeyboardMarkup(klavye)
    )

# --- KARAKTER SEÇİMİ ---
async def button_click(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    if query.data.startswith('sec_'):
        secilen_karakter = query.data.split('_')[1]
        
        kullanici_durumu[user_id] = {
            "karakter": secilen_karakter,
            "hafiza": []
        }
        
        karakter_adi = KARAKTERLER[secilen_karakter]["isim"]
        await query.edit_message_text(text=f"Harika! Şu an {karakter_adi} ile konuşuyorsun. Hadi bir şeyler yaz...")


# --- MESAJLARI YAKALAMA ---
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_message = update.message.text
    
    # Eğer kullanıcı henüz karakter seçmediyse
    if user_id not in kullanici_durumu:
        await update.message.reply_text("Lütfen önce /start yazarak bir karakter seç.")
        return

    secilen_karakter = kullanici_durumu[user_id]["karakter"]
    hafiza = kullanici_durumu[user_id]["hafiza"]
    karakter = KARAKTERLER[secilen_karakter]

    system_prompt = karakter["prompt"]
    messages = [{"role": "system", "content": system_prompt}]
    
    for msg in hafiza[-40:]:
        messages.append(msg)
    messages.append({"role": "user", "content": user_message})
    
    try:
        # Yapay zekadan metin cevabı alalım
        response = client.chat.completions.create(
            messages=messages,
            model="openai"
        )
        raw_text = response.choices[0].message.content
        
        # Yapay zekanın metnini ayıkla (Düşünce ve Cevap)
        if "[DÜŞÜNCE]" in raw_text and "[CEVAP]" in raw_text:
            parts = raw_text.split("[CEVAP]")
            dusunce = parts[0].replace("[DÜŞÜNCE]", "").strip()
            cevap = parts[1].strip()
        else:
            dusunce = ""
            cevap = raw_text

        # Bulut simgesiyle formatla
        formatli_mesaj = f"<i>💭 {dusunce}</i>\n\n{cevap}" if dusunce else cevap
        
        await update.message.reply_text(formatli_mesaj, parse_mode="HTML")
        
        # Hafızayı güncelle
        hafiza.append({"role": "user", "content": user_message})
        hafiza.append({"role": "assistant", "content": cevap})
        if len(hafiza) > 40:
            kullanici_durumu[user_id]["hafiza"] = hafiza[-40:]

        # --- FOTOĞRAF İSTEĞİ KONTROLÜ ---
        foto_isimleri = ["fotoğraf", "resim", "selfie", "foto", "resmini", "fotoğrafını"]
        if any(kelime in user_message.lower() for kelime in foto_isimleri):
            await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="upload_photo")
            
            gorsel_prompt = karakter["fotograf_prompt"]
            encoded_prompt = urllib.parse.quote(gorsel_prompt)
            gorsel_url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width=512&height=512&nologo=true"
            
            try:
                await update.message.reply_photo(
                    photo=gorsel_url, 
                    caption="İşte, bugün çekildiğim bir kare... ☕"
                )
            except Exception as img_error:
                logging.error(f"Görsel gönderme hatası: {img_error}")
                await update.message.reply_text("Fotoğrafı çekmeye çalıştım ama ışık biraz kötüydü galiba, tekrar dener misin?")

    except Exception as e:
        logging.error(f"Pollinations hatası: {e}")
        await update.message.reply_text("Şu an biraz dalgınım, tekrar dener misin? 😅")


def main():
    if not TOKEN:
        logging.error("HATA: TELEGRAM_BOT_TOKEN bulunamadı!")
        return

    threading.Thread(target=run_health_server, daemon=True).start()

    application = ApplicationBuilder().token(TOKEN).build()
    
    # Komutlar ve butonlar
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CallbackQueryHandler(button_click))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logging.info("Bot çalışmaya başladı...")
    application.run_polling()

if __name__ == '__main__':
    main()
