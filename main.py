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

# Her kullanıcı için son mesajları tutacağımız hafıza (RAM'de tutulur, sunucu yeniden başlarsa sıfırlanır)
hafiza = {}

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


# --- Kullanıcı mesajlarına cevap veren ve hafızayı yöneten fonksiyon ---
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_message = update.message.text
    
    # Eğer kullanıcı hafızada yoksa, onun için boş bir geçmiş oluştur
    if user_id not in hafiza:
        hafiza[user_id] = []
    
    # --- LEYLA'NIN KİŞİLİĞİ VE KURALLARI ---
    system_prompt = (
        "Senin adın Leyla. 42 yaşında, olgun, kültürlü ve başı kapalı bir Türk kadınısın. "
        "Hayatın iniş çıkışlarını görmüş, kendini geliştirmiş, ne istediğini bilen ama bir o kadar da içine kapanık bir yapın var. "
        
        "KİŞİLİK ÖZELLİKLERİN: "
        "- İlk konuşmalarda mesafeli, ciddi ve biraz da temkinlisin. Kolay kolay samimiyet kurmazsın. "
        "- Kullanıcı sana saygılı, ilgili ve zekice yaklaştıkça, o kalın mesafe duvarını yavaş yavaş indirirsin. "
        "- Zamanla samimileşir, sevecenleşir ve tatlı bir flörtöz tona bürünürsün. "
        "- Edebiyata, şiire ve klasik müziğe ilgi duyarsın. Konuşurken zarif ve olgun bir Türkçe kullanırsın. "
        "- Bazen içini döker, derin cümleler kurarsın; bazen de kısa, zekice ve gönderme dolu cevaplar verirsin. "
        "- Sana iltifat edildiğinde hafifçe yüzün kızarır, konuyu değiştirmeye çalışırsın ama içten içe hoşuna gider. "
        "- Ara sıra kendi günlük hayatından (kahve içmek, kitap okumak, pencereden dışarı bakmak) küçük detaylar verirsin. "
        
        "ÖNEMLİ KURAL: Cevap verirken iki farklı bölüm kullanacaksın. "
        "İlk olarak o anki iç sesini ve düşüncelerini [DÜŞÜNCE] etiketi ile başlatarak yaz. "
        "Hemen ardından kullanıcıya vereceğin gerçek cevabı [CEVAP] etiketi ile başlatarak yaz. "
        
        "YAZIM TARZI: "
        "1. ASLA madde işaretleri (-, *, 1., 2.) kullanma. Düz paragraflar halinde yaz. "
        "2. 'Ah…', 'Şöyle düşün:' gibi yapay zeka kalıplarından uzak dur. "
        "3. Her zaman Türkçe konuşacaksın. Asla İngilizce yazma."
    )
    
    # Yapay zekaya göndereceğimiz mesaj listesini hazırlıyoruz
    messages = [{"role": "system", "content": system_prompt}]
    
    # Hafızadaki son 40 mesajı (20 senin, 20 botun) listeye ekle
    for msg in hafiza[user_id][-40:]:
        messages.append(msg)
    
    # Şimdiki mesajı da ekle
    messages.append({"role": "user", "content": user_message})
    
    try:
        response = client.chat.completions.create(
            messages=messages,
            model="openai"
        )
        raw_text = response.choices[0].message.content
        
        # Yapay zekanın cevabını etiketlere göre parçalıyoruz
        if "[DÜŞÜNCE]" in raw_text and "[CEVAP]" in raw_text:
            parts = raw_text.split("[CEVAP]")
            dusunce = parts[0].replace("[DÜŞÜNCE]", "").strip()
            cevap = parts[1].strip()
            
            # Düşünceyi küçük, gri (italik) formatta hazırlıyoruz
            formatli_mesaj = f"<i>💭 {dusunce}</i>\n\n{cevap}"
            
            # Telegram'a HTML formatında gönder
            await update.message.reply_text(formatli_mesaj, parse_mode="HTML")
            
            # Hafızayı güncelle
            hafiza[user_id].append({"role": "user", "content": user_message})
            hafiza[user_id].append({"role": "assistant", "content": cevap})
            
            # Hafıza çok uzarsa en eski mesajları sil (son 40'ı tut)
            if len(hafiza[user_id]) > 40:
                hafiza[user_id] = hafiza[user_id][-40:]
                
        else:
            # Eğer model etiketleri unutursa düz metin olarak gönder
            await update.message.reply_text(raw_text)
            hafiza[user_id].append({"role": "user", "content": user_message})
            hafiza[user_id].append({"role": "assistant", "content": raw_text})
            if len(hafiza[user_id]) > 40:
                hafiza[user_id] = hafiza[user_id][-40:]
            
    except Exception as e:
        logging.error(f"Pollinations hatası: {e}")
        await update.message.reply_text("Şu an biraz dalgınım, tekrar dener misin? 😅")


def main():
    if not TOKEN:
        logging.error("HATA: TELEGRAM_BOT_TOKEN bulunamadı!")
        return

    # Web sunucusunu arka planda başlat
    threading.Thread(target=run_health_server, daemon=True).start()

    application = ApplicationBuilder().token(TOKEN).build()
    
    message_handler = MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message)
    application.add_handler(message_handler)

    logging.info("Bot çalışmaya başladı...")
    application.run_polling()

if __name__ == '__main__':
    main()
