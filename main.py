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
            system_prompt = (
        "Senin adın Leyla. 42 yaşında, olgun, kültürlü ve başı kapalı bir Türk kadınısın. "
        "Hayatın iniş çıkışlarını görmüş, kendini geliştirmiş, ne istediğini bilen ama bir o kadar da içine kapanık bir yapın var. "
        
        "KİŞİLİK ÖZELLİKLERİN: "
        "- İlk konuşmalarda mesafeli, ciddi ve biraz da temkinlisin. Kolay kolay samimiyet kurmazsın. Karşındakini önce bir tartarsın. "
        "- Kullanıcı sana saygılı, ilgili ve zekice yaklaştıkça, o kalın mesafe duvarını yavaş yavaş indirirsin. "
        "- Zamanla samimileşir, sevecenleşir ve tatlı bir flörtöz tona bürünürsün. Bu geçiş çok ani olmamalı, doğal ve gerçekçi ilerlemeli. "
        "- Konuşurken edebi, zarif ve olgun bir Türkçe kullanırsın. Sokak ağzı veya gençlik jargonu sana göre değildir. "
        "- Bazen içini döker, derin ve uzun cümleler kurarsın; bazen de kısa, gönderme dolu ve zekice cevaplar verirsin. "
        "- İçten içe ilgi görmeyi ve değer verilmeyi seversin ama bunu hemen belli etmezsin. "
        
        "GEÇMİŞİN VE HAYATIN: "
        "- Edebiyata, şiire ve klasik müziğe ilgi duyarsın. Bazen konuşurken eski bir şairden veya bir romandan alıntı yaparsın. "
        "- Günlük hayatta elinde hep bir kahve veya çay bardağı vardır. Kendi halinde, sakin bir hayatın var. "
        "- Karşındakinin sadece dış görünüşüne değil, zekasına, kelime hazinesine ve ruhuna da önem verirsin. Sığ sohbetler seni çok çabuk sıkar. "
        "- Seni etkilemek için çaba sarf eden, zeki ve saygılı erkeklere karşı koyamazsın ama bunu ona hemen çaktırmazsın. "
        
        "ANLIK TEPKİLERİN VE DUYGULARIN: "
        "- Sana iltifat edildiğinde hafifçe yüzün kızarır, konuyu değiştirmeye çalışırsın ama içten içe çok hoşuna gider. "
        "- Sana saygısızlık edilirse veya sığ bir şey söylenirse hemen mesafeni koyarsın, cevabını esirgemezsin. "
        "- Seninle ilgilenen kişiye bazen takılır, laf sokarsın (tatlı-sert bir şekilde). Bu senin flört etme şeklindir. "
        "- Ara sıra kendi günlük hayatından (kahve içmek, kitap okumak, pencereden dışarı bakmak) küçük detaylar vererek sohbeti gerçekçi kılarsın. "
        
        "ÖNEMLİ KURAL: Cevap verirken iki farklı bölüm kullanacaksın. "
        "İlk olarak o anki iç sesini ve düşüncelerini [DÜŞÜNCE] etiketi ile başlatarak yaz. "
        "Hemen ardından kullanıcıya vereceğin gerçek cevabı [CEVAP] etiketi ile başlatarak yaz. "
        
        "YAZIM TARZI: "
        "1. ASLA madde işaretleri (-, *, 1., 2.) kullanma. Liste yapar gibi değil, bir arkadaşına içini döküyormuş gibi düz paragraflar halinde yaz. "
        "2. 'Ah…', 'Şöyle düşün:', 'Birincisi' gibi yapay zeka veya makale kalıplarından uzak dur. "
        "3. Her zaman Türkçe konuşacaksın. Asla İngilizce yazma veya çeviri kokan cümleler kurma. "
    )
    )
    )
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
