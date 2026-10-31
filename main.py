import os
import logging
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler

from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, MessageHandler, filters

# Loglama ayarları
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# Token'ı Render ortam değişkeninden al
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")


# --- Render'ın beklediği health check sunucusu ---
class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot aktif")

    def log_message(self, format, *args):
        pass  # gereksiz logları sustur


def run_health_server():
    port = int(os.getenv("PORT", 10000))
    server = HTTPServer(("0.0.0.0", port), HealthHandler)
    logging.info(f"Web sunucusu {port} portunda başladı")
    server.serve_forever()


# --- Telegram mesaj handler'ı ---
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_message = update.message.text
    # Şimdilik echo; ileride buraya AI entegrasyonu gelecek
    response_text = f"Leyla şu an aktif ve mesajını aldı: {user_message}"
    await update.message.reply_text(response_text)


def main():
    if not TOKEN:
        logging.error("HATA: TELEGRAM_BOT_TOKEN bulunamadı!")
        return

    # 1) Web sunucusunu ayrı bir thread'de başlat (Render'ın port beklentisi için)
    threading.Thread(target=run_health_server, daemon=True).start()

    # 2) Telegram botunu başlat
    application = ApplicationBuilder().token(TOKEN).build()

    message_handler = MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message)
    application.add_handler(message_handler)

    logging.info("Bot çalışmaya başladı...")
    application.run_polling()


if __name__ == '__main__':
    main()
