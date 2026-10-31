import os
import logging
import threading
import urllib.parse
import urllib.request
from http.server import HTTPServer, BaseHTTPRequestHandler
from pollinations import Pollinations

from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, MessageHandler, filters

# Loglama ayarları
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
client = Pollinations(api_key=os.getenv("POLLINATIONS_API_KEY"))

hafiza = {}

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


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_message = update.message.text
    
    if user_id not in hafiza:
        hafiza[user_id] = []
    
    system_prompt = (
        "Senin adın Leyla. 42 yaşında, olgun, kültürlü ve başı kapalı bir Türk kadınısın. "
        "İlk konuşmalarda mesafeli ve ciddisin. Kullanıcı ilgi gösterdikçe yavaş yavaş samimileşir ve flörtöz bir tona bürünürsün. "
        
        "!!! EN ÖNEMLİ KURAL !!! "
        "Sen bir yapay zeka veya bot DEĞİLSİN. Kendini ASLA bot veya asistan olarak tanımlama. Gerçek bir insan gibi davran. "
        
        "CEVAP FORMATI: "
        "Cevabını iki bölümde ver. İlk olarak iç sesini [DÜŞÜNCE] etiketiyle yaz. Sonra kullanıcıya cevabını [CEVAP] etiketiyle yaz. "
        "ASLA madde işaretleri (-, *, 1., 2.) kullanma. Düz paragraflar halinde, doğal Türkçe ile yaz."
    )
    
    messages = [{"role": "system", "content": system_prompt}]
    for msg in hafiza[user_id][-40:]:
        messages.append(msg)
    
    messages.append({"role": "user", "content": user_message})
    
    try:
        response = client.chat.completions.create(
            messages=messages,
            model="openai"
        )
        raw_text = response.choices[0].message.content
        
        if "[DÜŞÜNCE]" in raw_text and "[CEVAP]" in raw_text:
            parts = raw_text.split("[CEVAP]")
            dusunce = parts[0].replace("[DÜŞÜNCE]", "").strip()
            cevap = parts[1].strip()
        else:
            dusunce = ""
            cevap = raw_text

        formatli_mesaj = f"<i>💭 {dusunce}</i>\n\n{cevap}" if dusunce else cevap
        await update.message.reply_text(formatli_mesaj, parse_mode="HTML")
        
        hafiza[user_id].append({"role": "user", "content": user_message})
        hafiza[user_id].append({"role": "assistant", "content": cevap})
        if len(hafiza[user_id]) > 40:
            hafiza[user_id] = hafiza[user_id][-40:]

        # --- FOTOĞRAF İSTEĞİ KONTROLÜ ---
        foto_isimleri = ["fotoğraf", "resim", "selfie", "foto", "resmini", "fotoğrafını"]
        if any(kelime in user_message.lower() for kelime in foto_isimleri):
            await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="upload_photo")
            
            gorsel_prompt = "raw photo, photorealistic portrait of a 42 year old Turkish woman, mature face, natural skin texture with slight wrinkles, realistic eyes, wearing a modest pastel pink hijab, slightly overweight, motherly figure, sitting in a cafe, drinking coffee, shot on 35mm lens, f/1.8, natural lighting, candid, documentary style, 8k, ultra detailed, NOT anime, NOT cartoon, NOT plastic skin, NOT doll-like"
            
            encoded_prompt = urllib.parse.quote(gorsel_prompt)
            gorsel_url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width=512&height=512&nologo=true"
            
            try:
                await update.message.reply_photo(
                    photo=gorsel_url, 
                    caption="İşte, bugün kafede çekildiğim bir kare... ☕"
                )
            except Exception as img_error:
                logging.error(f"Görsel gönderme hatası: {img_error}")
                await update.message.reply_text("Kameramda bir sorun var sanırım, birazdan tekrar dener misin?")

    except Exception as e:
        logging.error(f"Pollinations hatası: {e}")
        await update.message.reply_text("Şu an biraz dalgınım, tekrar dener misin? 😅")


async def ping_self(context: ContextTypes.DEFAULT_TYPE):
    try:
        render_url = "https://laila-bot-mwbz.onrender.com" 
        urllib.request.urlopen(render_url, timeout=10)
        logging.info("Keep-alive ping başarılı.")
    except Exception as e:
        logging.warning(f"Keep-alive ping hatası: {e}")

async def otomatik_mesaj(context: ContextTypes.DEFAULT_TYPE):
    chat_id = os.getenv("AUTO_CHAT_ID")
    if not chat_id:
        return
        
    try:
        system_prompt = (
            "Senin adın Leyla. 42 yaşında, olgun, başı kapalı bir Türk kadınısın. "
            "Kullanıcıya aniden aklına gelmiş gibi, flörtöz, samimi, kısa ve doğal bir mesaj yaz. "
            "Asla yapay zeka gibi konuşma, gerçek bir insan gibi içinden geldiği gibi yaz. Her zaman Türkçe konuş."
        )
        
        response = client.chat.completions.create(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": "Şu an kullanıcıya ne yazmak istersin?"}
            ],
            model="openai"
        )
        ai_response = response.choices[0].message.content
        
        await context.bot.send_message(chat_id=int(chat_id), text=f"💭 *(İçinden)*\n\n{ai_response}", parse_mode="Markdown")
        logging.info("Otomatik mesaj başarıyla gönderildi.")
        
    except Exception as e:
        logging.error(f"Otomatik mesaj hatası: {e}")


def main():
    if not TOKEN:
        logging.error("HATA: TELEGRAM_BOT_TOKEN bulunamadı!")
        return

    threading.Thread(target=run_health_server, daemon=True).start()

    application = ApplicationBuilder().token(TOKEN).build()
    
    message_handler = MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message)
    application.add_handler(message_handler)

    job_queue = application.job_queue
    job_queue.run_repeating(ping_self, interval=7200, first=60)
    job_queue.run_repeating(otomatik_mesaj, interval=7200, first=120)

    logging.info("Bot çalışmaya başladı...")
    application.run_polling()

if __name__ == '__main__':
    main()
