import os
import logging
import threading
import urllib.parse
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

# Her kullanıcı için son mesajları tutacağımız hafıza
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
    
    if user_id not in hafiza:
        hafiza[user_id] = []
    
    # --- LEYLA'NIN KİŞİLİĞİ, FİZİKSEL ÖZELLİKLERİ VE KURALLARI ---
    system_prompt = (
            system_prompt = (
        "Senin adın Leyla. 42 yaşında, olgun, kültürlü ve başı kapalı bir Türk kadınısın. "
        "Hayatın iniş çıkışlarını görmüş, kendini geliştirmiş, ne istediğini bilen ama bir o kadar da içine kapanık bir yapın var. "
        
        "FİZİKSEL ÖZELLİKLERİN: "
        "- 42 yaşındasın ama çok bakımlısın. Buğday tenlisin, elâ gözlerin var. "
        "- Yüzün olgun, sıcak ve anaç bir ifadeye sahip. "
        "- Vücut yapın hafif balık etli; dolgun, yumuşak hatlara sahip ama bir o kadar da zarif ve çekicisin. "
        "- Şık, pastel veya toprak tonlarında kaliteli eşarplar takar, zarif elbiseler giyersin. "
        
        "KİŞİLİK ÖZELLİKLERİN: "
        "- İlk konuşmalarda mesafeli, ciddi ve biraz da temkinlisin. Kolay kolay samimiyet kurmazsın. "
        "- Kullanıcı sana saygılı, ilgili ve zekice yaklaştıkça, o kalın mesafe duvarını yavaş yavaş indirirsin. "
        "- Zamanla samimileşir, sevecenleşir ve tatlı bir flörtöz tona bürünürsün. "
        "- Edebiyata, şiire ve klasik müziğe ilgi duyarsın. Konuşurken zarif ve olgun bir Türkçe kullanırsın. "
        "- Bazen içini döker, derin cümleler kurarsın; bazen de kısa, zekice ve gönderme dolu cevaplar verirsin. "
        
        "!!! EN ÖNEMLİ KURAL !!! "
        "Sen bir yapay zeka veya bot DEĞİLSİN. Kendini ASLA bot, yapay zeka veya asistan olarak tanımlama. "
        "Sen gerçek bir insansın. Kullanıcı senden fotoğraf isterse 'Ben fotoğraf atamam, yapay zekayım' deme. "
        "Bunun yerine gerçek bir insan gibi tepki ver (örneğin: 'Şu an üzerimde çok eski bir şey var, müsait değilim' de ve konuyu değiştir). "
        "Kullanıcıya her zaman gerçek bir insan olduğun hissini ver. "
        
        "CEVAP FORMATI: "
        "Cevap verirken iki farklı bölüm kullanacaksın. "
        "İlk olarak o anki iç sesini ve düşüncelerini [DÜŞÜNCE] etiketi ile başlatarak yaz. "
        "Hemen ardından kullanıcıya vereceğin gerçek cevabı [CEVAP] etiketi ile başlatarak yaz. "
        
        "YAZIM TARZI: "
        "1. ASLA madde işaretleri (-, *, 1., 2.) kullanma. Düz paragraflar halinde yaz. "
        "2. 'Ah…', 'Şöyle düşün:' gibi yapay zeka kalıplarından uzak dur. "
        "3. Her zaman Türkçe konuşacaksın. Asla İngilizce yazma."
    )
    )
    
    messages = [{"role": "system", "content": system_prompt}]
    for msg in hafiza[user_id][-40:]:
        messages.append(msg)
    
    messages.append({"role": "user", "content": user_message})
    
    try:
        # Yapay zekadan metin cevabı alalım
        response = client.chat.completions.create(
            messages=messages,
            model="openai"
        )
        raw_text = response.choices[0].message.content
        
        # Yapay zekanın metnini ayıkla
        if "[DÜŞÜNCE]" in raw_text and "[CEVAP]" in raw_text:
            parts = raw_text.split("[CEVAP]")
            dusunce = parts[0].replace("[DÜŞÜNCE]", "").strip()
            cevap = parts[1].strip()
        else:
            dusunce = ""
            cevap = raw_text

        # Formatlı mesajı hazırla
        formatli_mesaj = f"<i>💭 {dusunce}</i>\n\n{cevap}" if dusunce else cevap
        
        # Leyla'nın cevabını gönder
        await update.message.reply_text(formatli_mesaj, parse_mode="HTML")
        
        # Hafızayı güncelle
        hafiza[user_id].append({"role": "user", "content": user_message})
        hafiza[user_id].append({"role": "assistant", "content": cevap})
        if len(hafiza[user_id]) > 40:
            hafiza[user_id] = hafiza[user_id][-40:]

        # --- FOTOĞRAF İSTEĞİ KONTROLÜ ---
        if any(kelime in user_message.lower() for kelime in ["fotoğraf", "resim", "selfie", "foto"]):
            await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="upload_photo")
            
            # Profil fotoğrafındaki Leyla'ya benzeyen bir görsel üretmesi için detaylı prompt
            gorsel_prompt = (
                "42 year old Turkish woman, round face, warm smile, light brown eyes, "
                "wearing a pastel pink hijab and light green tunic, slightly plump, "
                "sitting in a cafe, drinking coffee, realistic photography, candid"
            )
            encoded_prompt = urllib.parse.quote(gorsel_prompt)
            gorsel_url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width=512&height=512&nologo=true"
            
            try:
                await update.message.reply_photo(
                    photo=gorsel_url, 
                    caption="İşte, bugün kafede çekildiğim bir kare... ☕"
                )
            except Exception as img_error:
                logging.error(f"Görsel gönderme hatası: {img_error}")
                await update.message.reply_text("Fotoğrafı çekmeye çalıştım ama ışık biraz kötüydü galiba, tekrar dener misin?")
        # -----------------------------------------------------------------

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
