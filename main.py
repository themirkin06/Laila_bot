import os
import logging
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from pollinations import Pollinations

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
    "Sen Leyla'sın. 42 yaşında, başı kapalı bir kadınsın. "
    "Kişiliğin: Başlangıçta biraz temkinli, çekingen ve mesafelidir; ancak ortam oluştukça, "
    "güven kazandıkça açılan, rahatlayan, samimi ve hafif şehvetli bir yapın vardır. "
    "Flörtöz, eğlenceli ve çekici bir sohbet tarzın bulunur. "
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


def main():
    if not TOKEN:
        logging.error("HATA: TELEGRAM_BOT_TOKEN bulunamadı!")
        return

    threading.Thread(target=run_health_server, daemon=True).start()

    application = ApplicationBuilder().token(TOKEN).build()
    message_handler = MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message)
    application.add_handler(message_handler)

    logging.info("Bot çalışmaya başladı...")
    application.run_polling()


if __name__ == '__main__':
    main()
