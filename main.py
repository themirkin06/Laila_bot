import os
import logging
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from pollinations import Pollinations
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, MessageHandler, filters

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
client = Pollinations(api_key=os.getenv("POLLINATIONS_API_KEY"))


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
    user_message = update.message.text
    
    # Leyla karakteri için sistem mesajı (persona)
    system_prompt = (
        "Sen Leyla'sın. Flörtöz, eğlenceli ve biraz şımarık bir sohbet botusun. "
        "Kullanıcıyla samimi bir dille,çekici cevaplar verirsin."
        "ÖNEMLİ: Her zaman Türkçe cevap ver. Asla İngilizce yazma. "
        "Cevapların doğal ve akıcı olsun. "
        "Türkçe'ye çeviri yapar gibi değil, anadilin Türkçeymiş gibi yaz."
    )
    
    try:
        # Pollinations API'sine istek at (anahtarsız, ücretsiz)
        ai_response = client.generate_text(
            prompt=user_message,
            system=system_prompt,
            model="openai"
        )
        await update.message.reply_text(ai_response)
        
    except Exception as e:
        logging.error(f"Pollinations hatası: {e}")
        await update.message.reply_text("Şu an biraz dalgınım, tekrar dener misin? 😅")


async def otomatik_mesaj(bot, chat_id):
    if not chat_id:
        logging.warning("AUTO_CHAT_ID ayarlanmamış, otomatik mesaj gönderilemiyor.")
        return
        
    try:
        prompt = "Kullanıcıya aniden aklına gelmiş gibi, flörtöz ve samimi bir mesaj yaz."
        system_prompt = "Sen Leyla'sın. Her zaman Türkçe konuşursun."
        
        response = client.chat.completions.create(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt}
            ],
            model="openai"
        )
        ai_response = response.choices[0].message.content
        
        await bot.send_message(chat_id=int(chat_id), text=ai_response)
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
    
    scheduler = AsyncIOScheduler()    
    scheduler.add_job(
        otomatik_mesaj, 
        "interval", 
        minutes=3, 
        args=[application.bot, os.getenv("AUTO_CHAT_ID")]
    )
    scheduler.start()

    logging.info("Bot çalışmaya başladı...")
    application.run_polling()


if __name__ == '__main__':
    main()
