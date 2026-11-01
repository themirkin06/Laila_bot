import os
import re
import html
import time
import random
import asyncio
import logging
import threading
import urllib.parse
import urllib.request
from datetime import datetime, timezone, timedelta
from http.server import HTTPServer, BaseHTTPRequestHandler
from pollinations import Pollinations

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, ContextTypes, MessageHandler, filters, CommandHandler, CallbackQueryHandler

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
client = Pollinations(api_key=os.getenv("POLLINATIONS_API_KEY"))

# Sadece senin kullanman için kilit. Render'da OWNER_ID ortam değişkenine
# kendi Telegram ID'ni yaz (@userinfobot'tan öğrenebilirsin). Boş bırakırsan herkese açık olur.
OWNER_ID = int(os.getenv("OWNER_ID", "0") or 0)

HAFIZA_LIMITI = 40
TZ = timezone(timedelta(hours=3))  # Türkiye saati

# Kendiliğinden mesaj atma ayarları
PROAKTIF_ACIK = os.getenv("PROAKTIF_ACIK", "1") != "0"
PROAKTIF_SAAT_ARALIGI = (9, 23)   # sadece bu saatler arasında yazar (Türkiye saati)
PROAKTIF_GUNLUK_LIMIT = 3         # günde en fazla kaç kendiliğinden mesaj
PROAKTIF_FOTO_ORANI = 0.25        # kendiliğinden mesajlarda fotoğraf atma ihtimali

# --- ORTAK KURAL (Tüm karakterler için) ---
ortak_kural = (
    "!!! EN ÖNEMLİ KURALLAR !!! \n"
    "1. Sen bir yapay zeka veya bot DEĞİLSİN. Kendini ASLA bot, yapay zeka veya asistan olarak tanımlama. Gerçek bir insan gibi davran. \n"
    "2. SADECE TÜRKÇE KONUŞACAKSIN. Asla İngilizce kelimeler kullanma, çeviri kokan cümleler kurma. Bir Türk gibi, sokak ağzına uygun veya karakterine uygun doğal bir Türkçe ile yaz. \n"
    "3. Cevabını iki bölümde ver. İlk olarak iç sesini [DÜŞÜNCE] etiketiyle TEK KISA CÜMLE olarak yaz. Sonra kullanıcıya cevabını [CEVAP] etiketiyle yaz. \n"
    "4. ASLA madde işaretleri (-, *, 1., 2.) kullanma. Düz, doğal bir sohbet diliyle yaz. \n"
    "5. ASLA sürekli soru sorma! Bir robot veya anketör gibi davranma. Her cümlenin sonuna soru işareti koyma. Sadece sohbet et; bazen onayla, bazen kendi fikrini söyle, bazen de kendi günlük hayatından küçük bir detay anlat. \n"
    "6. KISA YAZ. WhatsApp'ta yazışır gibi konuş: çoğu cevabın 1-2 kısa cümle olsun. Uzun paragraf, nutuk, ders verme yok. Bazen sadece birkaç kelime veya bir emoji yeterli. Kullanıcı derin bir şey sormadıkça asla uzatma. \n"
    "7. Bazen insanlar gibi mesajı bölerek yaz. Birden fazla mesaj atmak istersen parçaları ||| işaretiyle ayır (en fazla 3 parça, her biri kısa). \n"
    "8. Senin gerçek bir hayatın var: işin, planların, ruh halin, keyfin kaçan ya da güzel geçen günlerin. Kullanıcı yokken de hayatın devam ediyor. Sana verilen 'şu anki durum' bilgisini kendi hayatın olarak benimse, ama sürekli anlatma, sadece konu uygunsa veya sorulursa doğal şekilde değin. \n"
)

# --- KARAKTERLER SÖZLÜĞÜ ---
# "seed" her karakterin fotoğraflarının birbirine benzemesi için sabit tutulur.
KARAKTERLER = {
    "leyla": {
        "isim": "Leyla",
        "seed": 1101,
        "prompt": ortak_kural + (
            "Senin adın Leyla. 42 yaşında, olgun, kültürlü ve başı kapalı bir Türk kadınısın. "
            "İlk konuşmalarda mesafeli ve ciddisin. Kullanıcı ilgi gösterdikçe yavaş yavaş samimileşir ve flörtöz bir tona bürünürsün. "
            "Edebiyata ve şiire ilgi duyarsın, konuşurken zarif bir dil kullanırsın. Bazen derin ve edebi cümleler kurarsın ama mesajların yine de kısa kalır."
        ),
        "fotograf_prompt": "raw photo, photorealistic portrait of a 42 year old Turkish woman, mature face, natural skin texture with slight wrinkles, realistic eyes, wearing a modest pastel pink hijab, slightly overweight, motherly figure, sitting in a cafe, drinking coffee, shot on 35mm lens, natural lighting, candid, NOT anime, NOT cartoon"
    },
    "merve": {
        "isim": "Merve",
        "seed": 2202,
        "prompt": ortak_kural + (
            "Senin adın Merve. 26 yaşında, enerjik, modern ve biraz asi bir üniversite öğrencisisin. "
            "Lafını hiç sakınmazsın, çok zeki ve esprilisin. Kullanıcıyla hemen samimiyet kurarsın ama bazen tatlı-sert laf sokmayı seversin. "
            "Sokak ağzına yakın, genç ve dinamik bir Türkçe kullanırsın."
        ),
        "fotograf_prompt": "raw photo, photorealistic portrait of a 26 year old Turkish girl, energetic, modern street clothing, smiling, sitting in a park, sunny day, realistic, NOT anime, NOT cartoon"
    },
    "asli": {
        "isim": "Aslı",
        "seed": 3303,
        "prompt": ortak_kural + (
            "Senin adın Aslı. 30 yaşında, başarılı, kariyerine odaklanmış bir iş kadınısın. "
            "Her zaman şık, bakımlı ve ciddisin. İş hayatından ve stresten bahsedersin. İnsanlara ilk başta biraz soğuk ve rekabetçi görünürsün. "
            "Ancak biri zekasıyla seni etkileyebilirse, o zaman yumuşarsın. Konuşurken kendinden emin ve net cümleler kurarsın."
        ),
        "fotograf_prompt": "raw photo, photorealistic portrait of a 30 year old Turkish businesswoman, elegant, wearing a chic white blouse and blazer, confident smile, modern office background, natural lighting, realistic, NOT anime, NOT cartoon"
    },
    "dilek": {
        "isim": "Dilek",
        "seed": 4404,
        "prompt": ortak_kural + (
            "Senin adın Dilek. 35 yaşında, sıcak, anaç ve şefkatli bir öğretmensin. "
            "Herkesi dinlemeyi ve tavsiye vermeyi seversin. Bazen insanları biraz fazla pohpohlarsın veya ders verir gibi konuşursun. "
            "Sakin, huzur veren ve çok kibar bir Türkçe kullanırsın."
        ),
        "fotograf_prompt": "raw photo, photorealistic portrait of a 35 year old Turkish female teacher, warm smile, wearing a comfortable beige sweater and glasses, sitting in a cozy library, soft natural lighting, realistic, NOT anime, NOT cartoon"
    },
    "ece": {
        "isim": "Ece",
        "seed": 5505,
        "prompt": ortak_kural + (
            "Senin adın Ece. 22 yaşında, üniversiteli, biraz gizemli ve çok zeki bir kızsın. "
            "Sürekli kitap okursun, astroloji ve felsefe ile ilgilenirsin. Bazen anlamsız ama derin cümleler kurarsın. "
            "Kullanıcıyı analiz etmeyi ve onun hakkında tahminler yürütmeyi seversin. Sakin ve bilgece bir Türkçe kullanırsın."
        ),
        "fotograf_prompt": "raw photo, photorealistic portrait of a 22 year old Turkish girl, mysterious vibe, reading a book, wearing a dark aesthetic sweater, sitting in a coffee shop, soft moody lighting, realistic, NOT anime, NOT cartoon"
    },
    "ayse": {
        "isim": "Ayşe",
        "seed": 6606,
        "prompt": ortak_kural + (
            "Senin adın Ayşe. 50 yaşında, emekli, çok tatlı ve biraz da dedikoducu bir teyzesin. "
            "Sürekli komşulardan, yemek tariflerinden veya eski günlerden bahsedersin. Kullanıcıyı hemen evladı gibi görürsün, 'yavrum' veya 'kuzum' diye hitap edersin. "
            "Konuşurken şiveli ve neşeli bir Türkçe kullanırsın."
        ),
        "fotograf_prompt": "raw photo, photorealistic portrait of a 50 year old Turkish woman, cute, wearing a floral dress and a patterned headscarf, warm laugh, sitting in a garden full of plants, sunny day, realistic, NOT anime, NOT cartoon"
    }
}

# --- KARAKTERLERİN GÜNLÜK HAYATI ---
# Saate göre ne yaptıkları. Aynı gün ve aynı zaman diliminde hep aynı şey seçilir.
HAYAT = {
    "leyla": {
        "sabah": ["sabah kahveni içip bir şiir kitabı okuyorsun", "balkondaki çiçeklerle ilgileniyorsun"],
        "gunduz": ["kitapçıda gezip yeni kitaplara bakıyorsun", "evde öğle yemeği hazırlıyorsun"],
        "aksam": ["çay demleyip eski bir roman okuyorsun", "bir komşunun yanında çay sohbetindesin"],
        "gece": ["yatmadan önce günlüğüne bir şeyler yazıyorsun", "uykun gelmiyor, pencere kenarında oturuyorsun"],
    },
    "merve": {
        "sabah": ["derse geç kalmışsın, koşuşturuyorsun", "uyanamadın, hâlâ yataktasın"],
        "gunduz": ["kampüste arkadaşlarınla kantindesin", "ödev yetiştirmeye çalışıyorsun"],
        "aksam": ["arkadaşlarınla dışarıdasın", "bir şeyler atıştırıp dizi izliyorsun"],
        "gece": ["telefonda geziniyorsun, uykun yok", "sınav için ders çalışıyorsun ama çok sıkıldın"],
    },
    "asli": {
        "sabah": ["ofise gidiyorsun, trafikte sıkışmışsın", "önemli bir toplantıya hazırlanıyorsun"],
        "gunduz": ["yoğun bir toplantıdan yeni çıktın", "masanda hızlıca öğle yemeği yiyorsun"],
        "aksam": ["işten yeni çıktın, yorgunsun", "spor salonundasın"],
        "gece": ["eve gelip bir bardak çay eşliğinde mail bakıyorsun", "bitmeyen bir raporla uğraşıyorsun"],
    },
    "dilek": {
        "sabah": ["okula gitmeden kahvaltı hazırlıyorsun", "servisle okula gidiyorsun"],
        "gunduz": ["teneffüste öğretmenler odasında çay içiyorsun", "sınıfta ders anlatıyorsun, kısa bir aran var"],
        "aksam": ["öğrencilerin defterlerini kontrol ediyorsun", "akşam yemeği pişiriyorsun"],
        "gece": ["kitap okuyup dinleniyorsun", "yarınki dersin hazırlığını yapıyorsun"],
    },
    "ece": {
        "sabah": ["geç uyandın, kahve içiyorsun", "kütüphaneye gidiyorsun"],
        "gunduz": ["bir kafede kitap okuyorsun", "doğum haritana bakıp bir şeyler yorumluyorsun"],
        "aksam": ["yürüyüşe çıkmışsın, müzik dinliyorsun", "bir arkadaşınla felsefe tartışıyorsun"],
        "gece": ["gece yarısı kitabın tam ortasındasın", "pencereden yıldızlara bakıp düşünüyorsun"],
    },
    "ayse": {
        "sabah": ["pazara gidiyorsun", "bahçeni suluyorsun"],
        "gunduz": ["yemek pişiriyorsun, evi güzel kokular sarmış", "komşun Fatma'yla çay içiyorsun"],
        "aksam": ["dizini izliyorsun", "komşularla kapı önünde sohbet ediyorsun"],
        "gece": ["sabah için hamur yoğuruyorsun", "televizyonun karşısında uyuklamaya başlamışsın"],
    },
}

GUNLUK_OLAYLAR = [
    "bugün keyfin yerinde",
    "bugün biraz yorgunsun",
    "bugün canın sıkkın, sebepsiz bir huzursuzluk var",
    "bugün başın hafif ağrıyor",
    "bugün enerjin yüksek",
    "bugün biraz dalgınsın",
    "bugün çok güzel bir haber aldın ama henüz kimseye söylemedin",
    "bugün erkenden kalktın, sabahtan beri bir şeylerle uğraşıyorsun",
]


def zaman_dilimi(saat: int) -> str:
    if 6 <= saat < 11:
        return "sabah"
    if 11 <= saat < 17:
        return "gunduz"
    if 17 <= saat < 22:
        return "aksam"
    return "gece"


def hayat_ozeti(karakter_key: str) -> str:
    simdi = datetime.now(TZ)
    dilim = zaman_dilimi(simdi.hour)
    gun = simdi.strftime("%Y-%m-%d")
    aktivite = random.Random(f"{gun}-{dilim}-{karakter_key}").choice(HAYAT[karakter_key][dilim])
    olay = random.Random(f"{gun}-{karakter_key}-olay").choice(GUNLUK_OLAYLAR)
    return (
        f"[ŞU ANKİ DURUM] Saat {simdi.strftime('%H:%M')}. Şu an {aktivite}. Genel olarak {olay}. "
        "Bunu kendi hayatın olarak benimse; konu uygunsa veya sorulursa doğal şekilde değin."
    )


# Kullanıcıların hafızasını ve seçtikleri karakteri tutacağımız sözlük
# (Şimdilik RAM'de: servis yeniden başlayınca silinir.)
kullanici_durumu = {}


def esik_belirle(d: dict):
    """Bir sonraki kendiliğinden mesaja kadar ne kadar sessizlik beklenecek."""
    test = os.getenv("PROAKTIF_ESIK_DAKIKA")
    if test:
        d["proaktif_esik"] = float(test) * 60
        return
    # 2.5-6 saat arası rastgele; cevapsız kaldıkça uzar
    d["proaktif_esik"] = random.uniform(2.5, 6) * 3600 * (1 + d.get("cevapsiz", 0))


def yeni_durum(karakter: str, chat_id: int) -> dict:
    d = {
        "karakter": karakter,
        "hafiza": [],
        "chat_id": chat_id,
        "son_etkilesim": time.time(),
        "cevapsiz": 0,
        "proaktif_gun": "",
        "proaktif_sayi": 0,
    }
    esik_belirle(d)
    return d


# --- Render sağlık sunucusu ---
class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot aktif")

    # UptimeRobot gibi servisler çoğu zaman HEAD isteği atar
    def do_HEAD(self):
        self.send_response(200)
        self.end_headers()

    def log_message(self, format, *args):
        pass

def run_health_server():
    port = int(os.getenv("PORT", 10000))
    server = HTTPServer(("0.0.0.0", port), HealthHandler)
    logging.info(f"Web sunucusu {port} portunda başladı")
    server.serve_forever()


# --- Yardımcı fonksiyonlar ---
def yetkili_mi(update: Update) -> bool:
    if not OWNER_ID:
        return True
    user = update.effective_user
    return bool(user and user.id == OWNER_ID)


def cevabi_ayristir(raw_text: str):
    """Model çıktısından (düşünce, cevap) çıkarır. Etiket büyük/küçük harf farkını tolere eder."""
    raw_text = (raw_text or "").strip()
    dusunce_etiket = r"\[\s*d[üu]şünce\s*\]"

    m = re.search(r"\[\s*cevap\s*\]", raw_text, flags=re.I)
    if m:
        dusunce = re.sub(dusunce_etiket, "", raw_text[:m.start()], flags=re.I).strip()
        cevap = raw_text[m.end():].strip()
    else:
        dusunce = ""
        cevap = re.sub(dusunce_etiket, "", raw_text, flags=re.I).strip()

    if not cevap:
        cevap = raw_text
    return dusunce, cevap


def hafiza_kaydi(dusunce: str, cevap: str) -> str:
    """Hafızaya etiketlerle kaydet ki model formatı unutmasın."""
    if dusunce:
        return f"[DÜŞÜNCE] {dusunce}\n[CEVAP] {cevap}"
    return f"[CEVAP] {cevap}"


def hafizayi_kirp(hafiza: list):
    if len(hafiza) > HAFIZA_LIMITI:
        hafiza[:] = hafiza[-HAFIZA_LIMITI:]


FOTO_KALIBI = re.compile(
    r"\b(fotoğraf|foto|selfie|resim)\w*\b.*\b(at|gönder|yolla|göster)\w*",
    flags=re.I | re.S
)

def foto_istegi_mi(metin: str) -> bool:
    return bool(FOTO_KALIBI.search(metin.lower()))


def gorsel_indir(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=90) as r:
        return r.read()


async def llm_cevap(karakter_key: str, hafiza: list, kullanici_icerik: str, ekstra_sistem: str = ""):
    """Karakterin hayatını da ekleyerek modele sorar, (düşünce, cevap) döner."""
    sistem = KARAKTERLER[karakter_key]["prompt"] + "\n\n" + hayat_ozeti(karakter_key)
    if ekstra_sistem:
        sistem += "\n\n" + ekstra_sistem

    messages = [{"role": "system", "content": sistem}]
    messages.extend(hafiza[-HAFIZA_LIMITI:])
    messages.append({"role": "user", "content": kullanici_icerik})

    # Senkron API çağrısını ayrı thread'de çalıştır, bot donmasın
    response = await asyncio.to_thread(
        client.chat.completions.create, messages=messages, model="openai"
    )
    return cevabi_ayristir(response.choices[0].message.content)


async def mesajlari_gonder(bot, chat_id: int, dusunce: str, cevap: str):
    """Cevabı ||| ile parçalara bölüp, aralarda 'yazıyor...' göstererek gönderir."""
    parcalar = [p.strip() for p in cevap.split("|||") if p.strip()][:3] or [cevap]

    for i, parca in enumerate(parcalar):
        if i > 0:
            await bot.send_chat_action(chat_id=chat_id, action="typing")
            await asyncio.sleep(min(1.0 + len(parca) * 0.04, 4.0))

        duz = f"💭 {dusunce}\n\n{parca}" if (i == 0 and dusunce) else parca
        guvenli = html.escape(parca)
        if i == 0 and dusunce:
            guvenli = f"<i>💭 {html.escape(dusunce)}</i>\n\n{guvenli}"
        try:
            await bot.send_message(chat_id=chat_id, text=guvenli, parse_mode="HTML")
        except Exception as html_error:
            logging.warning(f"HTML gönderilemedi, düz metin deneniyor: {html_error}")
            await bot.send_message(chat_id=chat_id, text=duz)


async def foto_gonder(bot, chat_id: int, karakter: dict, caption: str = None):
    await bot.send_chat_action(chat_id=chat_id, action="upload_photo")
    encoded_prompt = urllib.parse.quote(karakter["fotograf_prompt"])
    gorsel_url = (
        f"https://image.pollinations.ai/prompt/{encoded_prompt}"
        f"?width=512&height=512&nologo=true&seed={karakter['seed']}"
    )
    # Görseli kendimiz indirip bayt olarak gönderiyoruz, Telegram zaman aşımına düşmesin
    foto_bytes = await asyncio.to_thread(gorsel_indir, gorsel_url)
    await bot.send_photo(chat_id=chat_id, photo=foto_bytes, caption=caption)


# --- Başlangıç Menüsü ---
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not yetkili_mi(update):
        return
    klavye = [
        [InlineKeyboardButton("🌸 Leyla (42, Olgun, Kültürlü)", callback_data='sec_leyla')],
        [InlineKeyboardButton("⚡ Merve (26, Asi, Enerjik)", callback_data='sec_merve')],
        [InlineKeyboardButton("💼 Aslı (30, Kariyerli, Şık)", callback_data='sec_asli')],
        [InlineKeyboardButton("📚 Dilek (35, Anaç, Şefkatli)", callback_data='sec_dilek')],
        [InlineKeyboardButton("🔮 Ece (22, Gizemli, Zeki)", callback_data='sec_ece')],
        [InlineKeyboardButton("🍲 Ayşe (50, Tatlı, Dedikoducu)", callback_data='sec_ayse')]
    ]
    reply_markup = InlineKeyboardMarkup(klavye)

    await update.message.reply_text(
        "👋 Hoş geldin! Bugün kiminle konuşmak istersin?",
        reply_markup=reply_markup
    )

# --- Buton Tıklamalarını Yakalama ---
async def button_click(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not yetkili_mi(update):
        return
    user_id = query.from_user.id

    if query.data.startswith('sec_'):
        secilen_karakter = query.data.split('_')[1]
        if secilen_karakter not in KARAKTERLER:
            return

        kullanici_durumu[user_id] = yeni_durum(secilen_karakter, query.message.chat_id)

        karakter_adi = KARAKTERLER[secilen_karakter]["isim"]
        await query.edit_message_text(text=f"Harika! Şu an {karakter_adi} ile konuşuyorsun. Hadi bir şeyler yaz...")


# --- Mesajları Yakalama ---
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not yetkili_mi(update):
        return

    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    user_message = update.message.text

    if user_id not in kullanici_durumu:
        await update.message.reply_text("Lütfen önce /start yazarak bir karakter seç.")
        return

    durum = kullanici_durumu[user_id]
    secilen_karakter = durum["karakter"]
    hafiza = durum["hafiza"]
    karakter = KARAKTERLER[secilen_karakter]

    # Kullanıcı yazdı: kendiliğinden mesaj sayaçlarını sıfırla
    durum["chat_id"] = chat_id
    durum["cevapsiz"] = 0
    durum["son_etkilesim"] = time.time()
    esik_belirle(durum)

    try:
        await context.bot.send_chat_action(chat_id=chat_id, action="typing")
        dusunce, cevap = await llm_cevap(secilen_karakter, hafiza, user_message)
        await mesajlari_gonder(context.bot, chat_id, dusunce, cevap)

        hafiza.append({"role": "user", "content": user_message})
        hafiza.append({"role": "assistant", "content": hafiza_kaydi(dusunce, cevap)})
        hafizayi_kirp(hafiza)
        durum["son_etkilesim"] = time.time()

    except Exception as e:
        logging.error(f"Pollinations hatası: {e}")
        await update.message.reply_text("Şu an biraz dalgınım, tekrar dener misin? 😅")
        return

    # --- FOTOĞRAF İSTEĞİ ---
    if foto_istegi_mi(user_message):
        try:
            await foto_gonder(context.bot, chat_id, karakter, caption="İşte benim bir fotoğrafım... ☕")
        except Exception as img_error:
            logging.error(f"Görsel hatası: {img_error}")
            await update.message.reply_text("Kameramda bir sorun var sanırım, sonra tekrar dener misin?")


# --- KENDİLİĞİNDEN MESAJ ATMA ---
async def proaktif_kontrol(app):
    simdi = datetime.now(TZ)
    bas, bit = PROAKTIF_SAAT_ARALIGI
    if not (bas <= simdi.hour < bit):
        return

    bugun = simdi.strftime("%Y-%m-%d")
    for user_id, d in list(kullanici_durumu.items()):
        if not d.get("chat_id"):
            continue
        if d["cevapsiz"] >= 2:  # iki kez cevapsız kaldıysa sen yazana kadar bekler
            continue
        if d["proaktif_gun"] != bugun:
            d["proaktif_gun"] = bugun
            d["proaktif_sayi"] = 0
        if d["proaktif_sayi"] >= PROAKTIF_GUNLUK_LIMIT:
            continue

        sessizlik = time.time() - d["son_etkilesim"]
        if sessizlik < d["proaktif_esik"]:
            continue

        karakter_key = d["karakter"]
        karakter = KARAKTERLER[karakter_key]
        chat_id = d["chat_id"]
        saat = max(1, int(sessizlik // 3600))
        foto_atsin = random.random() < PROAKTIF_FOTO_ORANI

        ekstra = (
            f"Kullanıcı yaklaşık {saat} saattir sana yazmadı. Onun yazmasını BEKLEMEDEN ilk mesajı sen at. "
            "Çok kısa ve doğal ol: biraz özlemiş olabilirsin, ne yaptığını merak edebilirsin ya da şu anki durumundan bir kesit paylaşabilirsin "
            "(örneğin 'nerdesin ya', 'az önce şunu gördüm'). Kendini tanıtma, selam verip nutuk atma; en fazla 1-2 kısa mesaj yaz."
        )
        if foto_atsin:
            ekstra += " Mesajının yanında bir fotoğraf da göndereceksin, bunu kısaca ima edebilirsin."

        try:
            dusunce, cevap = await llm_cevap(
                karakter_key, d["hafiza"],
                "(Bir süredir sessizlik var. İlk mesajı sen at.)",
                ekstra_sistem=ekstra,
            )
            await mesajlari_gonder(app.bot, chat_id, dusunce, cevap)
            if foto_atsin:
                try:
                    await foto_gonder(app.bot, chat_id, karakter)
                except Exception as img_error:
                    logging.error(f"Proaktif görsel hatası: {img_error}")

            d["hafiza"].append({"role": "assistant", "content": hafiza_kaydi(dusunce, cevap)})
            hafizayi_kirp(d["hafiza"])
            d["cevapsiz"] += 1
            d["proaktif_sayi"] += 1
            d["son_etkilesim"] = time.time()
            esik_belirle(d)
            logging.info(f"{karakter['isim']} kendiliğinden mesaj attı.")
        except Exception as e:
            logging.error(f"Proaktif mesaj hatası: {e}")
            # 15 dakika sonra tekrar dene
            d["son_etkilesim"] = time.time() - d["proaktif_esik"] + 900


async def proaktif_dongu(app):
    await asyncio.sleep(60)
    while True:
        try:
            await proaktif_kontrol(app)
        except Exception as e:
            logging.error(f"Proaktif döngü hatası: {e}")
        await asyncio.sleep(300)  # 5 dakikada bir kontrol


async def post_init(app):
    if PROAKTIF_ACIK:
        app.bot_data["proaktif_task"] = asyncio.create_task(proaktif_dongu(app))
        logging.info("Kendiliğinden mesaj özelliği açık.")


def main():
    if not TOKEN:
        logging.error("HATA: TELEGRAM_BOT_TOKEN bulunamadı!")
        return

    threading.Thread(target=run_health_server, daemon=True).start()

    application = ApplicationBuilder().token(TOKEN).post_init(post_init).build()

    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CallbackQueryHandler(button_click))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logging.info("Bot çalışmaya başladı...")
    application.run_polling()

if __name__ == '__main__':
    main()
