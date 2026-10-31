import os
import logging
import threading
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
# Pollinations istemcisini API anahtarı ile başlat
client = Pollinations(api_key=os.getenv("POLLINATIONS_API_KEY"))


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


# --- Kullanıcı mesajlarına cevap veren fonksiyon ---
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_message = update.message.text
    
    system_prompt = (
        "Sen Leyla'sın. Flörtöz, eğlenceli ve biraz şımarık bir sohbet botusun. "
        "Kullanıcıyla samimi bir dille,çekici cevaplar verirsin. "
        "ÖNEMLİ KURAL: Her zaman Türkçe konuşacaksın. Asla İngilizce yazma. "
        "Cümlelerin bir Türk gibi doğal ve akıcı olsun. Çeviri yapar gibi değil, "
        "anadilin Türkçeymiş gibi cevap ver."
    )
    
    try:
        response = client.chat.completions.create(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message}
            ],
            model="openai"
        )
        ai_response = response.choices[0].message.content
        await update.message.reply_text(ai_response)
        
    except Exception as e:
        logging.error(f"Pollinations hatası: {e}")
        await update.message.reply_text("Şu an biraz dalgınım, tekrar dener misin? 😅")


# --- Zamanlanmış Otomatik Mesaj Fonksiyonu (PTB JobQueue için) ---
async def otomatik_mesaj_callback(context: ContextTypes.DEFAULT_TYPE):
    chat_id = context.job.chat_id
    if not chat_id:
        logging.warning("AUTO_CHAT_ID ayarlanmamış, otomatik mesaj gönderilemiyor.")
        return
        
    try:
        prompt = "Kullanıcıya aniden aklına gelmiş gibi, flörtöz ve samimi bir mesaj yaz."
        system_prompt = "Sen Leyla'sın. Her zaman Türkçe konuşursun. Flörtöz ve şımarık bir kızsın."
        
        response = client.chat.completions.create(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt}
            ],
            model="openai"
        )
        ai_response = response.choices[0].message.content
        
        await context.bot.send_message(chat_id=int(chat_id), text=ai_response)
        logging.info("Otomatik mesaj başarıyla gönderildi.")
        
    except Exception as e:
        logging.error(f"Otomatik mesaj hatası: {e}")


def main():
    if not TOKEN:
        logging.error("HATA: TELEGRAM_BOT_TOKEN bulunamadı!")
        return

    # Web sunucusunu arka planda başlat
    threading.Thread(target=run_health_server, daemon=True).start()

    application = ApplicationBuilder().token(TOKEN).build()
    
    message_handler = MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message)
    application.add_handler(message_handler)

    # --- YERLEŞİK ZAMANLAYICI (JOBQUEUE) ---
    # Test için 60 saniye (1 dakika). 
    # Gerçek kullanımda "interval=7200" (2 saat) yapabilirsin.
    job_queue = application.job_queue
    job_queue.run_repeating(
        otomatik_mesaj_callback, 
        interval=60, 
        first=10, 
        chat_id=os.getenv("AUTO_CHAT_ID")
    )
    # --------------------------------------

    logging.info("Bot çalışmaya başladı...")
    application.run_polling()

if __name__ == '__main__':
    main()
