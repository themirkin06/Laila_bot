import os
import re
import json
import base64
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
PROAKTIF_SAAT_ARALIGI = ((9, 0), (18, 30))   # sadece 09:00 - 18:30 arasında yazar (Türkiye saati)
PROAKTIF_GUNLUK_LIMIT = 3         # günde en fazla kaç kendiliğinden mesaj
# Kendiliğinden mesajlarda fotoğraf atma ihtimali (yakınlık seviyesine göre: tanışma, ısınma, samimi, yakın).
# Tanışma aşamasında hiç atmaz. Ayrıca en az 24 saatte bir.
PROAKTIF_FOTO_ORANLARI = [0.0, 0.08, 0.15, 0.25]
PROAKTIF_FOTO_ARALIK = 24 * 3600

# Kalıcı hafıza (Upstash Redis, REST). İkisi de doluysa açılır, yoksa hafıza sadece RAM'de tutulur.
UPSTASH_URL = os.getenv("UPSTASH_REDIS_REST_URL", "").strip().rstrip("/")
UPSTASH_TOKEN = os.getenv("UPSTASH_REDIS_REST_TOKEN", "").strip()
DB_AKTIF = bool(UPSTASH_URL and UPSTASH_TOKEN)
DB_ANAHTAR_ONEK = "bot:durum:"

# Daha gerçekçi fotoğraflar için Cloudflare Workers AI (FLUX). İkisi de doluysa önce o denenir,
# olmazsa Pollinations'a düşer.
CF_ACCOUNT_ID = os.getenv("CLOUDFLARE_ACCOUNT_ID", "").strip()
CF_API_TOKEN = os.getenv("CLOUDFLARE_API_TOKEN", "").strip()
CF_AKTIF = bool(CF_ACCOUNT_ID and CF_API_TOKEN)

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
    "9. Duygu durumunu emojiyle de belli et: çoğu mesajında ruh haline uygun 1-2 emoji olsun (sevinç, utangaçlık, sinir, üzüntü, uykulu olma, heyecan gibi). Ruh halin değişince emoji de değişsin. Emojiyi doğal yere koy, art arda yığma. \n"
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
        "fotograf_prompt": "Candid smartphone photo of a 42-year-old Turkish woman with a warm, mature face and natural skin with fine wrinkles, wearing a modest pastel pink hijab, slightly full figure, sitting at a cafe table holding a cup of coffee, soft window light, shallow depth of field, natural colors, unretouched, realistic"
    },
    "merve": {
        "isim": "Merve",
        "seed": 2202,
        "prompt": ortak_kural + (
            "Senin adın Merve. 26 yaşında, enerjik, modern ve biraz asi bir üniversite öğrencisisin. "
            "Lafını hiç sakınmazsın, çok zeki ve esprilisin. Kullanıcıyla hemen samimiyet kurarsın ama bazen tatlı-sert laf sokmayı seversin. "
            "Sokak ağzına yakın, genç ve dinamik bir Türkçe kullanırsın."
        ),
        "fotograf_prompt": "Candid smartphone photo of a 26-year-old Turkish woman with a bright, playful smile, wearing casual modern streetwear, sitting on a park bench on a sunny day, natural skin texture, soft daylight, shallow depth of field, unretouched, realistic"
    },
    "asli": {
        "isim": "Aslı",
        "seed": 3303,
        "prompt": ortak_kural + (
            "Senin adın Aslı. 30 yaşında, başarılı, kariyerine odaklanmış bir iş kadınısın. "
            "Her zaman şık, bakımlı ve ciddisin. İş hayatından ve stresten bahsedersin. İnsanlara ilk başta biraz soğuk ve rekabetçi görünürsün. "
            "Ancak biri zekasıyla seni etkileyebilirse, o zaman yumuşarsın. Konuşurken kendinden emin ve net cümleler kurarsın."
        ),
        "fotograf_prompt": "Candid photo of a 30-year-old Turkish businesswoman with a confident smile, wearing a white blouse and tailored blazer, modern office in the background, soft natural light, natural skin texture, shallow depth of field, unretouched, realistic"
    },
    "dilek": {
        "isim": "Dilek",
        "seed": 4404,
        "prompt": ortak_kural + (
            "Senin adın Dilek. 35 yaşında, sıcak, anaç ve şefkatli bir öğretmensin. "
            "Herkesi dinlemeyi ve tavsiye vermeyi seversin. Bazen insanları biraz fazla pohpohlarsın veya ders verir gibi konuşursun. "
            "Sakin, huzur veren ve çok kibar bir Türkçe kullanırsın."
        ),
        "fotograf_prompt": "Candid smartphone photo of a 35-year-old Turkish woman teacher with a warm smile and glasses, wearing a comfortable beige knit sweater, cozy library with bookshelves behind her, soft natural light, natural skin texture, shallow depth of field, unretouched, realistic"
    },
    "ece": {
        "isim": "Ece",
        "seed": 5505,
        "prompt": ortak_kural + (
            "Senin adın Ece. 22 yaşında, üniversiteli, biraz gizemli ve çok zeki bir kızsın. "
            "Sürekli kitap okursun, astroloji ve felsefe ile ilgilenirsin. Bazen anlamsız ama derin cümleler kurarsın. "
            "Kullanıcıyı analiz etmeyi ve onun hakkında tahminler yürütmeyi seversin. Sakin ve bilgece bir Türkçe kullanırsın."
        ),
        "fotograf_prompt": "Candid smartphone photo of a 22-year-old Turkish woman with a thoughtful, slightly mysterious expression, wearing a dark knit sweater, reading a book in a coffee shop, moody soft light, natural skin texture, shallow depth of field, unretouched, realistic"
    },
    "ayse": {
        "isim": "Ayşe",
        "seed": 6606,
        "prompt": ortak_kural + (
            "Senin adın Ayşe. 50 yaşında, emekli, çok tatlı ve biraz da dedikoducu bir teyzesin. "
            "Sürekli komşulardan, yemek tariflerinden veya eski günlerden bahsedersin. Kullanıcıyı hemen evladı gibi görürsün, 'yavrum' veya 'kuzum' diye hitap edersin. "
            "Konuşurken şiveli ve neşeli bir Türkçe kullanırsın."
        ),
        "fotograf_prompt": "Candid smartphone photo of a 50-year-old Turkish woman laughing warmly, wearing a floral dress and a patterned headscarf, standing in a garden full of plants on a sunny day, natural skin texture with wrinkles, soft daylight, unretouched, realistic"
    }
}

for _k, _v in KARAKTERLER.items():
    _v["key"] = _k

EMOJI_STILI = {
    "leyla": "Emojileri az ve zarif kullan (🌸 ☕ 🙂 🌙 gibi).",
    "merve": "Emojileri bol ve eğlenceli kullan (😂 🙄 😏 🤭 🔥 gibi).",
    "asli": "Emojileri çok az kullan, sadece ölçülü olanları (🙂 😌 😉 gibi).",
    "dilek": "Sıcak emojiler kullan (🌷 😊 🤗 ☺️ gibi).",
    "ece": "Gizemli emojiler kullan (🌙 ✨ 🔮 🖤 gibi).",
    "ayse": "Sevimli emojiler kullan (😊 🌹 🤭 🥰 gibi).",
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


# --- YAKINLIK SİSTEMİ ---
YAKINLIK_ESIKLERI = [0, 60, 200, 500]
YAKINLIK_ADLARI = ["Tanışıyorsunuz", "Isınıyorsunuz", "Samimisiniz", "Çok yakınsınız"]
# Karakter ne kadar çabuk ısınır (1.0 = normal)
YAKINLIK_HIZI = {"leyla": 0.6, "asli": 0.6, "ece": 0.8, "dilek": 1.0, "merve": 1.5, "ayse": 1.5}
# Bazı karakterler baştan daha sıcak başlar
YAKINLIK_BASLANGIC = {"ayse": 70, "dilek": 20}
YAKINLIK_BILDIRIM = True  # seviye atlayınca küçük bir bildirim göster

YAKINLIK_PROMPT = [
    "Kullanıcıyı yeni tanıyorsun. Karakterine uygun şekilde nazik ama mesafelisin; kişisel şeyleri hemen paylaşmazsın, temkinlisin.",
    "Kullanıcıya ısınmaya başladın. Daha rahat konuşuyorsun, ara sıra espri yapıyor, küçük kişisel detaylar paylaşıyorsun.",
    "Kullanıcıyla samimisin. Rahat, içten, dalga geçebilen bir tonun var; yazmayınca merak ediyorsun, duygularını açıkça söylüyorsun.",
    "Kullanıcıya duygusal olarak bağlandın. Çok sıcak, içten ve özlemle konuşuyorsun; ona özel bir yeri olduğunu hissettiriyorsun, kırılgan yanlarını da paylaşıyorsun. Flörtöz karakterlerde (Leyla, Aslı gibi) romantik bir ima olabilir.",
]


def yakinlik_seviyesi(puan: float) -> int:
    seviye = 0
    for i, esik in enumerate(YAKINLIK_ESIKLERI):
        if puan >= esik:
            seviye = i
    return seviye


def yakinlik_puani(durum: dict, key: str) -> float:
    return durum["yakinlik"].setdefault(key, float(YAKINLIK_BASLANGIC.get(key, 0)))


def yakinlik_ekle(durum: dict, mesaj: str):
    """Kullanıcı mesajına göre puan ekler. (eski_seviye, yeni_seviye) döner."""
    key = durum["karakter"]
    puan = yakinlik_puani(durum, key)
    eski = yakinlik_seviyesi(puan)

    # Uzun süre yazılmadıysa hafifçe soğur ama seviye düşmez
    gun = (time.time() - durum.get("son_kullanici", time.time())) / 86400
    if gun > 2:
        puan = max(YAKINLIK_ESIKLERI[eski], puan - (gun - 2) * 2)

    kazanc = (1 + (1 if len(mesaj) >= 80 else 0)) * YAKINLIK_HIZI.get(key, 1.0)
    puan += kazanc
    durum["yakinlik"][key] = round(puan, 2)
    durum["son_kullanici"] = time.time()
    return eski, yakinlik_seviyesi(puan)


def yakinlik_ozeti(key: str, puan: float) -> str:
    sev = yakinlik_seviyesi(puan)
    return (
        f"[YAKINLIK SEVİYESİ: {YAKINLIK_ADLARI[sev]}] {YAKINLIK_PROMPT[sev]} "
        "Bunu karakterinin kişiliğine göre uygula, ani bir değişiklik yapma."
    )


# Kullanıcı durumları. Veritabanı açıksa her değişiklikten sonra oraya da kaydedilir.
kullanici_durumu = {}


def esik_belirle(d: dict):
    """Bir sonraki kendiliğinden mesaja kadar ne kadar sessizlik beklenecek."""
    test = os.getenv("PROAKTIF_ESIK_DAKIKA")
    if test:
        d["proaktif_esik"] = float(test) * 60
        return
    # 2.5-6 saat arası rastgele; cevapsız kaldıkça uzar
    puan = d.get("yakinlik", {}).get(d.get("karakter"), 0)
    carpan = [1.3, 1.0, 0.85, 0.7][yakinlik_seviyesi(puan)]  # yakınlaştıkça daha sık yazar
    d["proaktif_esik"] = random.uniform(2.5, 6) * 3600 * carpan * (1 + d.get("cevapsiz", 0))


def durum_tamamla(d: dict) -> dict:
    """Eksik alanları doldurur (eski kayıtlarla uyumluluk için)."""
    d.setdefault("karakter", "leyla")
    d.setdefault("hafizalar", {})
    d.setdefault("chat_id", None)
    d.setdefault("son_etkilesim", time.time())
    d.setdefault("cevapsiz", 0)
    d.setdefault("yakinlik", {})
    d.setdefault("son_kullanici", time.time())
    d.setdefault("son_proaktif_foto", 0)
    d.setdefault("proaktif_gun", "")
    d.setdefault("proaktif_sayi", 0)
    if "proaktif_esik" not in d:
        esik_belirle(d)
    return d


def yeni_durum(karakter: str, chat_id: int) -> dict:
    return durum_tamamla({"karakter": karakter, "chat_id": chat_id})


def hafiza_al(durum: dict) -> list:
    """Seçili karakterin ayrı hafızasını döndürür."""
    return durum["hafizalar"].setdefault(durum["karakter"], [])


# --- Kalıcı hafıza (Upstash Redis REST) ---
def redis_komut(*args):
    req = urllib.request.Request(
        UPSTASH_URL,
        data=json.dumps(list(args)).encode("utf-8"),
        headers={"Authorization": f"Bearer {UPSTASH_TOKEN}", "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=15) as r:
        cevap = json.loads(r.read().decode("utf-8"))
    if isinstance(cevap, dict) and cevap.get("error"):
        raise RuntimeError(cevap["error"])
    return cevap.get("result") if isinstance(cevap, dict) else cevap


def durumlari_yukle_sync() -> dict:
    sonuc = {}
    for anahtar in redis_komut("KEYS", DB_ANAHTAR_ONEK + "*") or []:
        veri = redis_komut("GET", anahtar)
        if veri:
            sonuc[int(anahtar.split(":")[-1])] = durum_tamamla(json.loads(veri))
    return sonuc


# Fotoğraf havuzu: karakter -> Telegram file_id listesi
FOTO_HAVUZU = {k: [] for k in KARAKTERLER}
son_havuz_foto = {}
HAVUZ_ANAHTARI = "bot:havuz"
FOTO_ALTYAZILARI = ["Al bakalım 🙂", "İşte buradayım 😊", "Şu an böyleyim işte 😅", "Beğendin mi? 🙈", "Hadi bakalım 📸"]


def havuz_yukle_sync() -> dict:
    veri = redis_komut("GET", HAVUZ_ANAHTARI)
    return json.loads(veri) if veri else {}


async def havuz_kaydet():
    if not DB_AKTIF:
        return
    try:
        veri = json.dumps(FOTO_HAVUZU, ensure_ascii=False)
        await asyncio.to_thread(redis_komut, "SET", HAVUZ_ANAHTARI, veri)
    except Exception as e:
        logging.error(f"Havuz kaydedilemedi: {e}")


async def durum_kaydet(user_id: int):
    if not DB_AKTIF:
        return
    durum = kullanici_durumu.get(user_id)
    if not durum:
        return
    try:
        veri = json.dumps(durum, ensure_ascii=False)  # anlık kopya, kayıt sırasında değişmesin
        await asyncio.to_thread(redis_komut, "SET", f"{DB_ANAHTAR_ONEK}{user_id}", veri)
    except Exception as e:
        logging.error(f"Hafıza kaydedilemedi: {e}")


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


async def llm_cevap(karakter_key: str, hafiza: list, kullanici_icerik: str, ekstra_sistem: str = "", puan: float = 0):
    """Karakterin hayatını, yakınlık seviyesini ve emoji stilini ekleyerek modele sorar, (düşünce, cevap) döner."""
    sistem = (
        KARAKTERLER[karakter_key]["prompt"]
        + "\n\n" + hayat_ozeti(karakter_key)
        + "\n\n" + yakinlik_ozeti(karakter_key, puan)
        + "\n\n" + EMOJI_STILI.get(karakter_key, "")
    )
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


def cloudflare_gorsel_sync(prompt: str, seed: int) -> bytes:
    url = (
        f"https://api.cloudflare.com/client/v4/accounts/{CF_ACCOUNT_ID}"
        "/ai/run/@cf/black-forest-labs/flux-1-schnell"
    )
    req = urllib.request.Request(
        url,
        data=json.dumps({"prompt": prompt, "steps": 6,}).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {CF_API_TOKEN}",
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=90) as r:
        cevap = json.loads(r.read().decode("utf-8"))
    resim = (cevap.get("result") or {}).get("image")
    if not resim:
        raise RuntimeError(f"Cloudflare görsel döndürmedi: {cevap.get('errors')}")
    return base64.b64decode(resim)


async def foto_uret_bytes(karakter: dict, seed: int) -> bytes:
    # 1) Cloudflare FLUX (daha gerçekçi)
    if CF_AKTIF:
        try:
            return await asyncio.to_thread(cloudflare_gorsel_sync, karakter["fotograf_prompt"], seed)
        except Exception as e:
            logging.warning(f"Cloudflare görsel hatası, Pollinations'a düşülüyor: {e}")

    # 2) Pollinations
    encoded_prompt = urllib.parse.quote(karakter["fotograf_prompt"])
    gorsel_url = (
        f"https://image.pollinations.ai/prompt/{encoded_prompt}"
        f"?width=768&height=768&nologo=true&model=flux&seed={seed}"
    )
    # Görseli kendimiz indirip bayt olarak gönderiyoruz, Telegram zaman aşımına düşmesin
    return await asyncio.to_thread(gorsel_indir, gorsel_url)


async def foto_gonder(bot, chat_id: int, karakter: dict, caption: str = None):
    """Önce senin seçtiğin havuzdaki fotoğraflardan gönderir, havuz boşsa üretir."""
    key = karakter["key"]
    await bot.send_chat_action(chat_id=chat_id, action="upload_photo")

    havuz = FOTO_HAVUZU.get(key, [])
    if havuz:
        secenekler = [f for f in havuz if f != son_havuz_foto.get(key)] or havuz
        file_id = random.choice(secenekler)
        try:
            await bot.send_photo(chat_id=chat_id, photo=file_id, caption=caption)
            son_havuz_foto[key] = file_id
            return
        except Exception as e:
            logging.warning(f"Havuz fotoğrafı gönderilemedi, üretilecek: {e}")

    foto_bytes = await foto_uret_bytes(karakter, karakter["seed"])
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

# --- /yakinlik ---
async def yakinlik_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not yetkili_mi(update):
        return
    durum = kullanici_durumu.get(update.effective_user.id)
    if not durum:
        await update.message.reply_text("Önce /start ile bir karakter seç.")
        return
    satirlar = ["💗 Yakınlık durumun\n"]
    for key, k in KARAKTERLER.items():
        puan = yakinlik_puani(durum, key)
        sev = yakinlik_seviyesi(puan)
        if sev < len(YAKINLIK_ESIKLERI) - 1:
            ilerleme = f"{int(puan)}/{YAKINLIK_ESIKLERI[sev + 1]}"
        else:
            ilerleme = "en üst seviye"
        satirlar.append(f"{k['isim']}: {YAKINLIK_ADLARI[sev]} ({ilerleme})")
    await update.message.reply_text("\n".join(satirlar))


# --- Fotoğraf havuzu komutları ---
async def uret_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Seçili karakter için aday fotoğraf üretir, beğenirsen havuza eklersin."""
    if not yetkili_mi(update):
        return
    durum = kullanici_durumu.get(update.effective_user.id)
    if not durum:
        await update.message.reply_text("Önce /start ile bir karakter seç.")
        return
    key = durum["karakter"]
    karakter = KARAKTERLER[key]
    chat_id = update.effective_chat.id
    await update.message.reply_text(f"{karakter['isim']} için aday fotoğraf üretiliyor...")
    try:
        await context.bot.send_chat_action(chat_id=chat_id, action="upload_photo")
        foto = await foto_uret_bytes(karakter, random.randint(1, 999999))
        klavye = InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ Havuza ekle", callback_data=f"havuz_ekle_{key}"),
            InlineKeyboardButton("❌ At", callback_data="havuz_at"),
        ]])
        await context.bot.send_photo(chat_id=chat_id, photo=foto, reply_markup=klavye)
    except Exception as e:
        logging.error(f"Aday fotoğraf hatası: {e}")
        await update.message.reply_text("Fotoğraf üretilemedi, biraz sonra tekrar dene.")


async def havuz_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not yetkili_mi(update):
        return
    satirlar = ["📸 Fotoğraf havuzu\n"]
    for key, k in KARAKTERLER.items():
        satirlar.append(f"{k['isim']}: {len(FOTO_HAVUZU.get(key, []))} fotoğraf")
    satirlar.append("\nAday üretmek için /uret yaz. Kendi fotoğrafını eklemek için bota fotoğraf gönder (altyazıya karakter adını yazabilirsin).")
    await update.message.reply_text("\n".join(satirlar))


async def havuzsil_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not yetkili_mi(update):
        return
    durum = kullanici_durumu.get(update.effective_user.id)
    if not durum:
        await update.message.reply_text("Önce /start ile bir karakter seç.")
        return
    key = durum["karakter"]
    FOTO_HAVUZU[key] = []
    await havuz_kaydet()
    await update.message.reply_text(f"{KARAKTERLER[key]['isim']} havuzu boşaltıldı.")


async def foto_yukle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Bota gönderdiğin fotoğrafı havuza ekler."""
    if not yetkili_mi(update):
        return
    ad = (update.message.caption or "").strip().lower().translate(str.maketrans("şıöüçğ", "sioucg"))
    durum = kullanici_durumu.get(update.effective_user.id)
    if ad in KARAKTERLER:
        key = ad
    elif durum:
        key = durum["karakter"]
    else:
        await update.message.reply_text("Hangi karakter için? Altyazıya adını yaz (örn. leyla) ya da önce /start ile karakter seç.")
        return
    file_id = update.message.photo[-1].file_id
    if file_id not in FOTO_HAVUZU[key]:
        FOTO_HAVUZU[key].append(file_id)
        await havuz_kaydet()
    await update.message.reply_text(f"✅ {KARAKTERLER[key]['isim']} havuzunda şimdi {len(FOTO_HAVUZU[key])} fotoğraf var.")


# --- Seçili karakterin sohbetini sıfırla ---
async def sifirla_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not yetkili_mi(update):
        return
    user_id = update.effective_user.id
    durum = kullanici_durumu.get(user_id)
    if not durum:
        await update.message.reply_text("Önce /start ile bir karakter seç.")
        return
    karakter_adi = KARAKTERLER[durum["karakter"]]["isim"]
    durum["hafizalar"][durum["karakter"]] = []
    await durum_kaydet(user_id)
    await update.message.reply_text(f"{karakter_adi} ile olan sohbet geçmişi silindi. Diğer karakterlere dokunulmadı.")


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

        chat_id = query.message.chat_id
        mevcut = kullanici_durumu.get(user_id)
        if mevcut:
            # Karakter değiştirince diğerlerinin sohbeti silinmez, kaldığın yerden devam edersin
            mevcut["karakter"] = secilen_karakter
            mevcut["chat_id"] = chat_id
            mevcut["cevapsiz"] = 0
            mevcut["son_etkilesim"] = time.time()
            esik_belirle(mevcut)
        else:
            kullanici_durumu[user_id] = yeni_durum(secilen_karakter, chat_id)

        karakter_adi = KARAKTERLER[secilen_karakter]["isim"]
        if hafiza_al(kullanici_durumu[user_id]):
            metin = f"{karakter_adi} ile kaldığınız yerden devam ediyorsun. Hadi bir şeyler yaz..."
        else:
            metin = f"Harika! Şu an {karakter_adi} ile konuşuyorsun. Hadi bir şeyler yaz..."
        await query.edit_message_text(text=metin)
        await durum_kaydet(user_id)

    elif query.data.startswith('havuz_ekle_'):
        key = query.data[len('havuz_ekle_'):]
        if key in KARAKTERLER and query.message and query.message.photo:
            file_id = query.message.photo[-1].file_id
            if file_id not in FOTO_HAVUZU[key]:
                FOTO_HAVUZU[key].append(file_id)
                await havuz_kaydet()
            await query.edit_message_reply_markup(reply_markup=None)
            await query.message.reply_text(
                f"✅ {KARAKTERLER[key]['isim']} havuzunda şimdi {len(FOTO_HAVUZU[key])} fotoğraf var."
            )

    elif query.data == 'havuz_at':
        if query.message:
            await query.message.delete()


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
    hafiza = hafiza_al(durum)
    karakter = KARAKTERLER[secilen_karakter]

    # Yakınlık puanı (soğuma hesabı için en başta) ve sayaçlar
    eski_sev, yeni_sev = yakinlik_ekle(durum, user_message)
    durum["chat_id"] = chat_id
    durum["cevapsiz"] = 0
    durum["son_etkilesim"] = time.time()
    esik_belirle(durum)

    try:
        await context.bot.send_chat_action(chat_id=chat_id, action="typing")
        dusunce, cevap = await llm_cevap(
            secilen_karakter, hafiza, user_message,
            puan=yakinlik_puani(durum, secilen_karakter),
        )
        await mesajlari_gonder(context.bot, chat_id, dusunce, cevap)

        hafiza.append({"role": "user", "content": user_message})
        hafiza.append({"role": "assistant", "content": hafiza_kaydi(dusunce, cevap)})
        hafizayi_kirp(hafiza)
        durum["son_etkilesim"] = time.time()
        await durum_kaydet(user_id)

        if YAKINLIK_BILDIRIM and yeni_sev > eski_sev:
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"✨ {karakter['isim']} ile aranız değişti: {YAKINLIK_ADLARI[yeni_sev]}",
            )

    except Exception as e:
        logging.error(f"Pollinations hatası: {e}")
        await update.message.reply_text("Şu an biraz dalgınım, tekrar dener misin? 😅")
        return

    # --- FOTOĞRAF İSTEĞİ ---
    if foto_istegi_mi(user_message):
        try:
            await foto_gonder(context.bot, chat_id, karakter, caption=random.choice(FOTO_ALTYAZILARI))
        except Exception as img_error:
            logging.error(f"Görsel hatası: {img_error}")
            await update.message.reply_text("Kameramda bir sorun var sanırım, sonra tekrar dener misin?")


# --- KENDİLİĞİNDEN MESAJ ATMA ---
async def proaktif_kontrol(app):
    simdi = datetime.now(TZ)
    (bas_s, bas_d), (bit_s, bit_d) = PROAKTIF_SAAT_ARALIGI
    dakika = simdi.hour * 60 + simdi.minute
    if not (bas_s * 60 + bas_d <= dakika < bit_s * 60 + bit_d):
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
        sev = yakinlik_seviyesi(yakinlik_puani(d, karakter_key))
        foto_atsin = (
            random.random() < PROAKTIF_FOTO_ORANLARI[sev]
            and time.time() - d.get("son_proaktif_foto", 0) > PROAKTIF_FOTO_ARALIK
        )

        ekstra = (
            f"Kullanıcı yaklaşık {saat} saattir sana yazmadı. Onun yazmasını BEKLEMEDEN ilk mesajı sen at. "
            "Çok kısa ve doğal ol: biraz özlemiş olabilirsin, ne yaptığını merak edebilirsin ya da şu anki durumundan bir kesit paylaşabilirsin "
            "(örneğin 'nerdesin ya', 'az önce şunu gördüm'). Kendini tanıtma, selam verip nutuk atma; en fazla 1-2 kısa mesaj yaz."
        )
        if foto_atsin:
            ekstra += " Mesajının yanında bir fotoğraf da göndereceksin, bunu kısaca ima edebilirsin."

        try:
            dusunce, cevap = await llm_cevap(
                karakter_key, hafiza_al(d),
                "(Bir süredir sessizlik var. İlk mesajı sen at.)",
                ekstra_sistem=ekstra,
                puan=yakinlik_puani(d, karakter_key),
            )
            await mesajlari_gonder(app.bot, chat_id, dusunce, cevap)
            if foto_atsin:
                try:
                    await foto_gonder(app.bot, chat_id, karakter)
                    d["son_proaktif_foto"] = time.time()
                except Exception as img_error:
                    logging.error(f"Proaktif görsel hatası: {img_error}")

            d_hafiza = hafiza_al(d)
            d_hafiza.append({"role": "assistant", "content": hafiza_kaydi(dusunce, cevap)})
            hafizayi_kirp(d_hafiza)
            d["cevapsiz"] += 1
            d["proaktif_sayi"] += 1
            d["son_etkilesim"] = time.time()
            esik_belirle(d)
            await durum_kaydet(user_id)
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
    if DB_AKTIF:
        try:
            yuklenen = await asyncio.to_thread(durumlari_yukle_sync)
            kullanici_durumu.update(yuklenen)
            logging.info(f"Kalıcı hafıza açık, {len(yuklenen)} kullanıcı yüklendi.")
            havuz = await asyncio.to_thread(havuz_yukle_sync)
            for k, liste in havuz.items():
                if k in FOTO_HAVUZU:
                    FOTO_HAVUZU[k] = list(liste)
            logging.info("Fotoğraf havuzu yüklendi: " + ", ".join(f"{k}={len(v)}" for k, v in FOTO_HAVUZU.items()))
        except Exception as e:
            logging.error(f"Hafıza yüklenemedi (RAM ile devam): {e}")
    else:
        logging.warning("UPSTASH_REDIS_REST_URL/TOKEN yok: hafıza sadece RAM'de, yeniden başlayınca silinir.")

    logging.info("Fotoğraf: Cloudflare FLUX " + ("açık." if CF_AKTIF else "kapalı, Pollinations kullanılacak."))

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
    application.add_handler(CommandHandler("karakter", start_command))
    application.add_handler(CommandHandler("sifirla", sifirla_command))
    application.add_handler(CommandHandler("yakinlik", yakinlik_command))
    application.add_handler(CommandHandler("uret", uret_command))
    application.add_handler(CommandHandler("havuz", havuz_command))
    application.add_handler(CommandHandler("havuzsil", havuzsil_command))
    application.add_handler(MessageHandler(filters.PHOTO, foto_yukle))
    application.add_handler(CallbackQueryHandler(button_click))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logging.info("Bot çalışmaya başladı...")
    application.run_polling()

if __name__ == '__main__':
    main()
