import os
import logging
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, MessageHandler, filters

# Loglama ayarları
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# Telegram Bot Token'ını Render ortam değişkenlerinden (Environment Variables) alacağız
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_message = update.message.text
    # Şimdilik test amaçlı gelen mesaja echo (aynısını döndürme) yapıyoruz
    # İlerleyen aşamada buraya AI API (Groq/OpenRouter vb.) entegrasyonunu ekleyeceğiz.
    response_text = f"Leyla şu an aktif ve mesajını aldı: {user_message}"
    
    await update.message.reply_text(response_text)

def main():
    if not TOKEN:
        print("HATA: TELEGRAM_BOT_TOKEN bulunamadı!")
        return

    application = ApplicationBuilder().token(TOKEN).build()

    # Metin mesajlarını dinleyen handler
    message_handler = MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message)
    application.add_handler(message_handler)

    print("Bot çalışmaya başladı...")
    application.run_polling()

if __name__ == '__main__':
    main()
