import os
import re
import json
import html
import time
import random
import asyncio
import logging
import threading
import urllib.request
from datetime import datetime, timezone, timedelta
from http.server import HTTPServer, BaseHTTPRequestHandler

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto
from telegram.ext import ApplicationBuilder, ContextTypes, MessageHandler, filters, CommandHandler, CallbackQueryHandler

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
# httpx her isteği URL'siyle (içinde bot token'ı var) loglar. Token loglara sızmasın diye sustur.
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

from config import *
from characters import *
from photos import *
from memory import *
from relationship import *
from emotions import *
from world import *
from proactive import proaktif_dongu
from story import *
from ai import *



# Örnek konuşmalar: modele üslubu göstermek için (yalnızca stil, birebir tekrar edilmez).


# --- ROL YAPMA STİLİ ---
# Hareketler *yıldız* içinde (Telegram'da italik görünür), konuşmalar yıldızsız.



# --- HİKÂYE MODU: her karakterin kendi hikâyesi ve sahneleri ---
# Sahne, yakınlık seviyesiyle ilerler (0: Tanışıyorsunuz ... 3: Çok yakınsınız). Kullanıcı /sahne ile değiştirebilir.





def yakinlik_bildirimi(key: str, karakter: dict, sev: int) -> str:
    r = HIKAYE.get(key, {}).get("rutbeler")
    if r:
        return f"🐺 Sürüdeki rütben yükseldi: {r[sev]}"
    return f"✨ {karakter['isim']} ile aranız değişti: {YAKINLIK_ADLARI[sev]}"













# --- KARAKTERLERİN GÜNLÜK HAYATI ---
# Saate göre ne yaptıkları. Aynı gün ve aynı zaman diliminde hep aynı şey seçilir.
# Karakterlerin günlük rutinleri world.py içinde tutulur.

# ---- Asena (kurt adam sürüsü) ----
FOTO_KISI["dondu"] = "a 43-year-old Turkish woman with strong features, amber-colored eyes and long dark wavy hair"
FOTO_SAHNELER["dondu"] = ["at the edge of a misty pine forest at dusk", "beside a stone fireplace in a mountain cabin", "on a hilltop under a pale full moon", "walking along a forest path at dawn"]

# Örnek konuşmalar (sade, günlük dil, emojisiz). Önceki örnekleri geçersiz kılar.

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
    d.setdefault("kullanici_profili", {"ad": "", "yas": None, "bilgiler": []})
    d.setdefault("tanismalar", {})
    d.setdefault("chat_id", None)
    d.setdefault("son_etkilesim", time.time())
    d.setdefault("cevapsiz", 0)
    d.setdefault("yakinlik", {})
    d.setdefault("son_kullanici", time.time())
    d.setdefault("son_proaktif_foto", 0)
    d.setdefault("proaktif_foto_gun", "")
    d.setdefault("proaktif_foto_sayi", 0)
    # Her yakınlık seviyesi için en fazla bir otomatik kutlama fotoğrafı gönderilir.
    d.setdefault("seviye_foto_gonderildi", {})
    d.setdefault("stil", "hikaye")
    d.setdefault("sahneler", {})
    d.setdefault("sahne_hafizasi", {})  # karakter bazında kalıcı son sahne notu
    # Yeni ilişki ve dünya alanları: eski Redis kayıtlarına zarar vermeden eklenir.
    d.setdefault("iliski", {})
    d.setdefault("duygular", {})
    d.setdefault("gunluk", {})
    d.setdefault("karakter_sirlari", {})
    d.setdefault("dunya", {})
    d.setdefault("yan_karakterler", {})
    d.setdefault("son_olaylar", {})
    d.setdefault("proaktif_gun", "")
    d.setdefault("proaktif_sayi", 0)
    if "proaktif_esik" not in d:
        esik_belirle(d)
    return d


def yeni_durum(karakter: str, chat_id: int) -> dict:
    return durum_tamamla({"karakter": karakter, "chat_id": chat_id})


# Fotoğraf havuzu: karakter -> Telegram file_id listesi
FOTO_HAVUZU = {k: [] for k in KARAKTERLER}
son_havuz_foto = {}
HAVUZ_ANAHTARI = "bot:havuz"
YUZ_REFERANS_ANAHTARI = "bot:yuz_referanslari"
YUZ_REFERANSLARI = {k: None for k in KARAKTERLER}
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


def keep_alive_loop():
    """Render ücretsiz planda 15 dk istek gelmezse servis uyur. Kendi adresine 10 dakikada bir istek atar."""
    url = os.getenv("KEEPALIVE_URL") or os.getenv("RENDER_EXTERNAL_URL")
    if not url:
        logging.info("Kendi kendine ping kapalı (RENDER_EXTERNAL_URL yok).")
        return
    logging.info(f"Kendi kendine ping açık: {url}")
    time.sleep(60)
    while True:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "keepalive"})
            urllib.request.urlopen(req, timeout=30).read()
        except Exception as e:
            logging.warning(f"Ping hatası: {e}")
        time.sleep(600)


# --- Yardımcı fonksiyonlar ---
def yetkili_mi(update: Update) -> bool:
    if not OWNER_ID:
        return True
    user = update.effective_user
    return bool(user and user.id == OWNER_ID)




FOTO_KALIBI = re.compile(
    r"\b(fotoğraf|foto|selfie|resim)\w*\b.*\b(at|gönder|yolla|göster)\w*",
    flags=re.I | re.S
)

def foto_istegi_mi(metin: str) -> bool:
    return bool(FOTO_KALIBI.search(metin.lower()))




async def mesajlari_gonder(bot, chat_id: int, dusunce: str, cevap: str):
    """Cevabı ||| ile parçalara bölüp, aralarda 'yazıyor...' göstererek gönderir."""
    parcalar = [p.strip() for p in cevap.split("|||") if p.strip()][:3] or [cevap]

    for i, parca in enumerate(parcalar):
        if i > 0:
            await bot.send_chat_action(chat_id=chat_id, action="typing")
            await asyncio.sleep(min(1.0 + len(parca) * 0.04, 4.0))

        duz = f"💭 {dusunce}\n\n{parca}" if (i == 0 and dusunce) else parca
        guvenli = html.escape(parca)
        guvenli = re.sub(r"\*{1,2}([^*\n]+?)\*{1,2}", r"<i>\1</i>", guvenli)  # *hareket* -> italik
        if i == 0 and dusunce:
            guvenli = f"<i>💭 {html.escape(dusunce)}</i>\n\n{guvenli}"
        try:
            await bot.send_message(chat_id=chat_id, text=guvenli, parse_mode="HTML")
        except Exception as html_error:
            logging.warning(f"HTML gönderilemedi, düz metin deneniyor: {html_error}")
            await bot.send_message(chat_id=chat_id, text=duz)


# --- Sohbet içinden otomatik sahne fotoğrafı ---
# Yalnızca karakterin kendi ağzından, şu anda yaptığı açıkça anlaşılan eylemler yakalanır.
OTOMATIK_FOTO_SAHNELERI = [
    ("cay_icme", re.compile(r"\b(çay içiyorum|çayımı içiyorum|çay içmeye başladım)\b", re.I),
     "drinking Turkish tea at home, holding a clear tulip-shaped tea glass, cozy natural setting"),
    ("cay_demleme", re.compile(r"\b(çay demliyorum|demlik hazırlıyorum|çay koyuyorum|çay hazırlıyorum|demliyorum)\b", re.I),
     "preparing and brewing Turkish tea in a home kitchen, tea kettle and teapot clearly visible"),
    ("kahve", re.compile(r"\b(kahve yapıyorum|kahvemi hazırlıyorum|kahve pişiriyorum|kahve içiyorum)\b", re.I),
     "making or drinking coffee in a cozy kitchen or cafe, coffee cup clearly visible"),
    ("yemek", re.compile(r"\b(yemek yapıyorum|yemek hazırlıyorum|mutfakta.*pişiriyorum|yemek pişiriyorum)\b", re.I),
     "cooking a meal in the kitchen, ingredients and cookware visible"),
    ("temizlik", re.compile(r"\b(temizlik yapıyorum|evi topluyorum|bulaşık yıkıyorum)\b", re.I),
     "doing ordinary housework at home, natural lived-in surroundings"),
    ("kitap", re.compile(r"\b(kitap okuyorum|kitap okuyordum)\b", re.I),
     "reading a book in a comfortable quiet corner, book clearly visible"),
    ("uzanma", re.compile(r"\b(uzandım|uzanıyorum|koltuğa uzandım|yatağa uzandım|dinleniyorum)\b", re.I),
     "relaxing while lying on a sofa or bed, comfortable modest home clothes"),
    ("uyku_hazirligi", re.compile(r"\b(yatıyorum|yatmaya gidiyorum|uyumaya hazırlanıyorum|yatağa geçiyorum)\b", re.I),
     "getting ready for bed in a cozy bedroom, modest sleepwear, warm bedside lighting"),
    ("hazirlik", re.compile(r"\b(giyiniyorum|hazırlanıyorum|makyaj yapıyorum|saçımı yapıyorum)\b", re.I),
     "getting ready in front of a bedroom mirror, everyday outfit and personal items visible"),
    ("disari", re.compile(r"\b(dışarıdayım|dışarı çıktım|yürüyüş yapıyorum|sahildeyim|parkta yürüyorum)\b", re.I),
     "out for a walk outdoors, natural street or park surroundings"),
    ("alisveris", re.compile(r"\b(alışveriş yapıyorum|marketteyim|pazara geldim)\b", re.I),
     "shopping in a grocery store or local market, natural candid setting"),
]


def otomatik_foto_sahnesi_bul(cevap: str):
    """Karakter cevabında açık bir şimdiki zaman etkinliği varsa sahne anahtarı ve prompt döndürür."""
    metin = re.sub(r"\*[^*]*\*", " ", cevap or "")
    for anahtar, kalip, prompt in OTOMATIK_FOTO_SAHNELERI:
        if kalip.search(metin):
            return anahtar, prompt
    return None


def otomatik_foto_gonderilmeli(durum: dict, karakter_key: str, sahne_key: str) -> bool:
    """Aynı etkinlikte tekrarı önler; yeni sahneye kısa bir geçiş payı bırakır."""
    kayitlar = durum.setdefault("otomatik_foto_kaydi", {})
    onceki = kayitlar.get(karakter_key, {})
    simdi = time.time()
    if onceki.get("sahne") == sahne_key and simdi - float(onceki.get("zaman", 0)) < 45 * 60:
        return False
    if onceki and simdi - float(onceki.get("zaman", 0)) < 3 * 60:
        return False
    return True


async def foto_gonder(
    bot, chat_id: int, karakter: dict, caption: str = None,
    yakinlik: int = 0, havuzdan: bool = True, surpriz: bool = False, scene_prompt: str = ""
):
    """Önce havuzu kullanır; yeni üretimde karakterin kayıtlı yüz referansını uygular."""
    key = karakter["key"]
    await bot.send_chat_action(chat_id=chat_id, action="upload_photo")

    havuz = FOTO_HAVUZU.get(key, []) if havuzdan and not surpriz else []
    if havuz:
        secenekler = [f for f in havuz if f != son_havuz_foto.get(key)] or havuz
        file_id = random.choice(secenekler)
        try:
            await bot.send_photo(chat_id=chat_id, photo=file_id, caption=caption)
            son_havuz_foto[key] = file_id
            return
        except Exception as e:
            logging.warning(f"Havuz fotoğrafı gönderilemedi, üretilecek: {e}")

    reference_bytes = None
    # Açıkça yüz referansı kaydedilmediyse mevcut havuzdaki ilk fotoğrafı kimlik referansı kullan.
    reference_file_id = YUZ_REFERANSLARI.get(key) or (FOTO_HAVUZU.get(key) or [None])[0]
    if reference_file_id:
        try:
            telegram_file = await bot.get_file(reference_file_id)
            reference_bytes = bytes(await telegram_file.download_as_bytearray())
        except Exception as e:
            logging.warning(f"{KARAKTERLER[key]['isim']} yüz referansı indirilemedi: {e}")

    foto_bytes = await foto_uret_bytes(
        karakter, random.randint(1, 999999), yakinlik=yakinlik,
        surpriz=surpriz, reference_image=reference_bytes, scene_prompt=scene_prompt,
    )
    await bot.send_photo(chat_id=chat_id, photo=foto_bytes, caption=caption)

async def cevabi_ilet(bot, chat_id: int, dusunce: str, cevap: str):
    """Karakter yanıtını normal Telegram mesajı olarak gönderir."""
    await mesajlari_gonder(bot, chat_id, dusunce, cevap)


# --- Başlangıç Menüsü: sade karşılama + sayfalı karakter galerisi ---
KARAKTER_KISA_TANITIM = {
    "leyla": "Kitapçı; zarif, ölçülü ve zamanla sıcak.",
    "merve": "Enerjik, zeki, esprili ve biraz asi.",
    "asli": "Kendinden emin, başarılı ve şık bir yönetici.",
    "dilek": "Şefkatli, sabırlı ve iyi bir dinleyici.",
    "ece": "Gizemli, meraklı; felsefe ve astroloji tutkunu.",
    "ayse": "Neşeli, sıcak ve mahallenin haber merkezi.",
    "dondu": "Bilge, otoriter ve koruyucu sürü lideri.",
}
GALERI_SAYFA_BOYUTU = 2

async def _karakter_galeri_fotografi(key: str, karakter: dict, semaphore: asyncio.Semaphore, bot):
    """Use the character's own reference for new gallery img2img photos."""
    havuz = FOTO_HAVUZU.get(key, [])
    reference_file_id = YUZ_REFERANSLARI.get(key) or (havuz[0] if havuz else None)
    if not reference_file_id:
        raise RuntimeError(f"{karakter['isim']} için yüz referansı kayıtlı değil.")
    async with semaphore:
        telegram_file = await bot.get_file(reference_file_id)
        reference_bytes = bytes(await telegram_file.download_as_bytearray())
        return await foto_uret_bytes(
            karakter, int(karakter.get("seed", random.randint(1, 999999))),
            reference_image=reference_bytes,
        )

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Sade karşılama ekranını gösterir; galeri kullanıcı isteyince açılır."""
    if not yetkili_mi(update):
        return
    metin = (
        "❤️ Laila'nın dünyasına hoş geldin!\n\n"
        "Her karakterin kendine ait bir kişiliği ve hikâyesi var. "
        "Önce karakterleri keşfet, sonra tanışmak istediğini seç."
    )
    klavye = InlineKeyboardMarkup([[InlineKeyboardButton("✨ Karakterleri keşfet", callback_data="gal_0")]])
    # Bu mesajda Markdown kullanmıyoruz; Telegram entity ayrıştırma hatasını önler.
    await update.effective_message.reply_text(metin, reply_markup=klavye)

async def karakter_galerisi_goster(query, context: ContextTypes.DEFAULT_TYPE, sayfa: int):
    """Her sayfada iki karakter gösterir; sayfa değişince önceki galeri temizlenir."""
    # Önceki sayfanın fotoğraflarını ve gezinme mesajını temizle.
    eski_mesaj_idleri = context.user_data.pop("laila_galeri_mesaj_idleri", [])
    for mesaj_id in eski_mesaj_idleri:
        try:
            await context.bot.delete_message(
                chat_id=query.message.chat_id,
                message_id=mesaj_id,
            )
        except Exception as exc:
            logging.debug("Eski galeri mesajı silinemedi (%s): %s", mesaj_id, exc)

    keys = list(KARAKTERLER.keys())
    toplam_sayfa = max(1, (len(keys) + GALERI_SAYFA_BOYUTU - 1) // GALERI_SAYFA_BOYUTU)
    sayfa = max(0, min(sayfa, toplam_sayfa - 1))
    secilenler = keys[sayfa * GALERI_SAYFA_BOYUTU:(sayfa + 1) * GALERI_SAYFA_BOYUTU]
    semaphore = asyncio.Semaphore(2)
    sonuclar = await asyncio.gather(
        *[_karakter_galeri_fotografi(key, KARAKTERLER[key], semaphore, context.bot) for key in secilenler],
        return_exceptions=True,
    )
    medya = []
    klavye = []
    for key, foto in zip(secilenler, sonuclar):
        karakter = KARAKTERLER[key]
        isim = karakter["isim"]
        tanitim = KARAKTER_KISA_TANITIM.get(key, "Kendi hikâyesi olan bir karakter.")
        if isinstance(foto, Exception) or not foto:
            logging.warning("%s galeri fotoğrafı üretilemedi: %s", isim, foto)
            klavye.append([InlineKeyboardButton(f"{isim} ile tanış", callback_data=f"sec_{key}")])
            continue
        medya.append(InputMediaPhoto(media=foto, caption=f"{isim}\n{tanitim}"))
        klavye.append([InlineKeyboardButton(f"{isim} ile tanış", callback_data=f"sec_{key}")])

    yeni_mesaj_idleri = []
    if medya:
        if len(medya) == 1:
            item = medya[0]
            gonderilen = await context.bot.send_photo(
                chat_id=query.message.chat_id, photo=item.media,
                caption=item.caption,
            )
            yeni_mesaj_idleri.append(gonderilen.message_id)
        else:
            gonderilenler = await context.bot.send_media_group(
                chat_id=query.message.chat_id, media=medya
            )
            yeni_mesaj_idleri.extend(m.message_id for m in gonderilenler)

    gezinme = []
    if sayfa > 0:
        gezinme.append(InlineKeyboardButton("⬅️ Önceki", callback_data=f"gal_{sayfa-1}"))
    gezinme.append(InlineKeyboardButton(f"{sayfa+1}/{toplam_sayfa}", callback_data="gal_bilgi"))
    if sayfa < toplam_sayfa - 1:
        gezinme.append(InlineKeyboardButton("Sonraki ➡️", callback_data=f"gal_{sayfa+1}"))
    klavye.append(gezinme)
    gezinme_mesaji = await context.bot.send_message(
        chat_id=query.message.chat_id,
        text="Tanışmak istediğin karakteri seç:",
        reply_markup=InlineKeyboardMarkup(klavye),
    )
    yeni_mesaj_idleri.append(gezinme_mesaji.message_id)
    context.user_data["laila_galeri_mesaj_idleri"] = yeni_mesaj_idleri

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
async def aday_gonder(bot, chat_id: int, key: str):
    """Aday fotoğraf üretir, altına Havuza ekle / At butonları koyar."""
    karakter = KARAKTERLER[key]
    await bot.send_chat_action(chat_id=chat_id, action="upload_photo")
    ref_file_id = YUZ_REFERANSLARI.get(key) or (FOTO_HAVUZU.get(key) or [None])[0]
    ref_bytes = None
    if ref_file_id:
        try:
            tg_file = await bot.get_file(ref_file_id)
            ref_bytes = bytes(await tg_file.download_as_bytearray())
        except Exception as e:
            logging.warning(f"Aday fotoğraf için yüz referansı indirilemedi: {e}")
    foto = await foto_uret_bytes(karakter, random.randint(1, 999999), reference_image=ref_bytes)
    klavye = InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Havuza ekle", callback_data=f"havuz_ekle_{key}"),
        InlineKeyboardButton("❌ At", callback_data="havuz_at"),
    ]])
    await bot.send_photo(chat_id=chat_id, photo=foto, reply_markup=klavye)


async def uret_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Seçili karakter için bir aday fotoğraf üretir, beğenirsen havuza eklersin."""
    if not yetkili_mi(update):
        return
    durum = kullanici_durumu.get(update.effective_user.id)
    if not durum:
        await update.message.reply_text("Önce /start ile bir karakter seç.")
        return
    key = durum["karakter"]
    await update.message.reply_text(f"{KARAKTERLER[key]['isim']} için aday fotoğraf üretiliyor...")
    try:
        await aday_gonder(context.bot, update.effective_chat.id, key)
    except Exception as e:
        logging.error(f"Aday fotoğraf hatası: {e}")
        await update.message.reply_text("Fotoğraf üretilemedi, biraz sonra tekrar dene.")


async def havuzdoldur_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/havuzdoldur 5 -> seçili karakter için 5 aday gönderir, beğendiklerine tek tıkla eklersin."""
    if not yetkili_mi(update):
        return
    durum = kullanici_durumu.get(update.effective_user.id)
    if not durum:
        await update.message.reply_text("Önce /start ile bir karakter seç.")
        return
    key = durum["karakter"]
    n = 4
    if context.args and context.args[0].isdigit():
        n = max(1, min(6, int(context.args[0])))
    await update.message.reply_text(
        f"{KARAKTERLER[key]['isim']} için {n} aday üretiliyor. Beğendiklerinin altındaki ✅ butonuna bas, olmayanları ❌ ile at."
    )
    basarili = 0
    for _ in range(n):
        try:
            await aday_gonder(context.bot, update.effective_chat.id, key)
            basarili += 1
        except Exception as e:
            logging.error(f"Aday fotoğraf hatası: {e}")
            break
    if basarili == 0:
        await update.message.reply_text("Fotoğraf üretilemedi, biraz sonra tekrar dene.")


async def havuz_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not yetkili_mi(update):
        return
    satirlar = ["📸 Fotoğraf havuzu\n"]
    for key, k in KARAKTERLER.items():
        satirlar.append(f"{k['isim']}: {len(FOTO_HAVUZU.get(key, []))} fotoğraf")
    satirlar.append("\nTek aday için /uret, birkaç aday için /havuzdoldur 5 yaz. Yüz referansı kaydetmek için net bir karakter fotoğrafını 'yuzref leyla' gibi bir altyazıyla gönder.")
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
    """Fotoğrafı havuza ekler; 'yuzref karakter' altyazısıyla yüz referansı kaydeder."""
    if not yetkili_mi(update):
        return
    ad = (update.message.caption or "").strip().lower().translate(str.maketrans("şıöüçğ", "sioucg"))
    durum = kullanici_durumu.get(update.effective_user.id)

    if ad.startswith("yuzref "):
        key = ad.split(maxsplit=1)[1].strip()
        if key not in KARAKTERLER:
            await update.message.reply_text("Karakter kodunu tanıyamadım. Örnek: yuzref leyla, yuzref merve, yuzref ayse.")
            return
        uygun = [p for p in update.message.photo if max(p.width, p.height) <= 512]
        if not uygun:
            await update.message.reply_text("Bu fotoğrafın 512 pikselden küçük bir sürümü bulunamadı.")
            return
        referans = max(uygun, key=lambda p: p.width * p.height)
        YUZ_REFERANSLARI[key] = referans.file_id
        if DB_AKTIF:
            try:
                await asyncio.to_thread(
                    redis_komut, "SET", YUZ_REFERANS_ANAHTARI,
                    json.dumps(YUZ_REFERANSLARI, ensure_ascii=False)
                )
            except Exception as e:
                logging.error(f"Yüz referansı Redis'e kaydedilemedi: {e}")
                await update.message.reply_text("Referans bu oturumda kaydedildi ama kalıcı kayıtta hata oldu.")
                return
        await update.message.reply_text(
            f"✅ {KARAKTERLER[key]['isim']} için yüz referansı kaydedildi. Yeni üretilen fotoğraflarda bu yüzü temel alacağım."
        )
        return

    if ad in KARAKTERLER:
        key = ad
    elif durum:
        key = durum["karakter"]
    else:
        await update.message.reply_text("Hangi karakter için? Altyazıya karakter adını yaz (örn. leyla) ya da önce /start ile karakter seç.")
        return
    file_id = update.message.photo[-1].file_id
    if file_id not in FOTO_HAVUZU[key]:
        FOTO_HAVUZU[key].append(file_id)
        await havuz_kaydet()
    await update.message.reply_text(f"✅ {KARAKTERLER[key]['isim']} havuzunda şimdi {len(FOTO_HAVUZU[key])} fotoğraf var.")


# --- /stil, /hikaye, /sahne ---
STIL_SIRASI = ["hikaye", "roleplay", "mesaj"]
STIL_ADLARI = {
    "hikaye": "Hikâye (karakterle aynı ortamda, sahneli rol yapma)",
    "roleplay": "Rol yapma (hareketler yıldız içinde, 2-4 cümle)",
    "mesaj": "Mesajlaşma (kısa, WhatsApp tarzı)",
}


async def stil_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/stil: sırayla değiştirir. /stil hikaye, /stil roleplay ya da /stil mesaj ile doğrudan seçilir."""
    if not yetkili_mi(update):
        return
    user_id = update.effective_user.id
    durum = kullanici_durumu.get(user_id)
    if not durum:
        await update.message.reply_text("Önce /start ile bir karakter seç.")
        return
    istenen = context.args[0].lower().replace("â", "a").replace("ı", "i") if context.args else ""
    if istenen in STIL_ADLARI:
        durum["stil"] = istenen
    else:
        simdiki = durum.get("stil", "hikaye")
        durum["stil"] = STIL_SIRASI[(STIL_SIRASI.index(simdiki) + 1) % len(STIL_SIRASI)]
    await durum_kaydet(user_id)
    await update.message.reply_text(
        f"🎭 Stil: {STIL_ADLARI[durum['stil']]}\nEski mesajlar yeni stile karışırsa /sifirla yazabilirsin."
    )


async def hikaye_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/hikaye: seçili karakterin hikâyesini ve şu anki sahneyi gösterir."""
    if not yetkili_mi(update):
        return
    durum = kullanici_durumu.get(update.effective_user.id)
    if not durum:
        await update.message.reply_text("Önce /start ile bir karakter seç.")
        return
    key = durum["karakter"]
    puan = yakinlik_puani(durum, key)
    ozel = durum["sahneler"].get(key)
    rutbe = rutbe_metni(key, puan)
    rutbe_satiri = f"🐺 Rütben: {rutbe}\n\n" if rutbe else ""
    await update.message.reply_text(
        f"📖 {KARAKTERLER[key]['isim']} hikâyesi\n\n{HIKAYE[key]['premise']}\n\n{rutbe_satiri}"
        f"🎬 Şu anki sahne{' (senin seçtiğin)' if ozel else ''}:\n{sahne_metni(key, puan, ozel)}\n\n"
        "Sahneyi değiştirmek için: /sahne <yeni sahne>. Otomatiğe dönmek için: /sahne sifirla"
    )


async def sahne_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/sahne <metin>: sahneyi sen belirlersin. /sahne sifirla: yakınlığa göre otomatiğe döner."""
    if not yetkili_mi(update):
        return
    user_id = update.effective_user.id
    durum = kullanici_durumu.get(user_id)
    if not durum:
        await update.message.reply_text("Önce /start ile bir karakter seç.")
        return
    key = durum["karakter"]
    metin = " ".join(context.args).strip() if context.args else ""
    if not metin:
        await update.message.reply_text(
            f"🎬 Şu anki sahne:\n{sahne_metni(key, yakinlik_puani(durum, key), durum['sahneler'].get(key))}\n\n"
            "Değiştirmek için: /sahne akşam sahilde yürüyoruz\nOtomatiğe dönmek için: /sahne sifirla"
        )
        return
    if metin.lower() in ("sifirla", "sıfırla", "otomatik"):
        durum["sahneler"].pop(key, None)
        durum.setdefault("sahne_hafizasi", {}).pop(key, None)
        await durum_kaydet(user_id)
        await update.message.reply_text("🎬 Sahne yakınlık seviyene göre otomatiğe döndü.")
        return
    metin = metin[:300]
    durum["sahneler"][key] = metin
    durum.setdefault("sahne_hafizasi", {})[key] = metin
    hafiza_al(durum).append({"role": "assistant", "content": f"*Sahne değişir: {metin}*"})
    await durum_kaydet(user_id)
    await update.message.reply_text(f"🎬 Sahne güncellendi: {metin}")


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

    if query.data.startswith("gal_"):
        parca = query.data.split("_", 1)[1]
        if parca == "bilgi":
            return
        try:
            sayfa = int(parca)
        except ValueError:
            return
        await karakter_galerisi_goster(query, context, sayfa)
        return

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
        # Karakter seçilince galeri fotoğraflarını ve seçim/gezinti mesajını temizle.
        galeri_mesaj_idleri = context.user_data.pop("laila_galeri_mesaj_idleri", [])
        if query.message and query.message.message_id not in galeri_mesaj_idleri:
            galeri_mesaj_idleri.append(query.message.message_id)
        for mesaj_id in galeri_mesaj_idleri:
            try:
                await context.bot.delete_message(chat_id=chat_id, message_id=mesaj_id)
            except Exception as exc:
                logging.debug("Seçim sonrası galeri mesajı silinemedi (%s): %s", mesaj_id, exc)
        await context.bot.send_message(chat_id=chat_id, text=metin)
        await durum_kaydet(user_id)

        # Hikâye modunda ilk kez konuşuluyorsa sahne girişi gönderilir
        durum_s = kullanici_durumu[user_id]
        if durum_s.get("stil", "hikaye") == "hikaye" and not hafiza_al(durum_s):
            # Eski giriş metinleri bazı karakterlerde kullanıcıyı önceden tanıyormuş gibi başlıyordu.
            # İlk karşılaşmada bu varsayımı kaldırıp karaktere uygun, tarafsız bir selamlama kullan.
            ilk_girisler = {
                "leyla": "*Kitapçının kapısındaki küçük çan çalar. Tezgâhın ardından başını kaldırıp gülümser.* Merhaba. Ben Leyla. Daha önce karşılaşmadık sanırım. Sana nasıl hitap edeyim?",
                "merve": "*Kafede masasından başını kaldırıp sana bakar.* Selam, ben Merve. Sanırım daha önce tanışmadık. Senin adın ne?",
                "asli": "*Toplantı odasının önünde elindeki dosyaları düzeltip sana döner.* Merhaba, ben Aslı. Sanırım tanışmıyoruz. Adını öğrenebilir miyim?",
                "dilek": "*Apartman bahçesinde çiçekleri sularken sana gülümser.* Merhaba, ben Dilek. Seni daha önce görmedim galiba. Adın ne?",
                "ece": "*Kitabını kapatıp merakla sana bakar.* Merhaba, ben Ece. Daha önce tanıştık mı, hatırlayamadım. Adın ne?",
                "ayse": "*Mutfaktan elinde çay bardağıyla çıkar, sıcakça gülümser.* Hoş geldin kuzum. Ben Ayşe. Senin adın ne bakalım?",
                "dondu": "*Ocağın ateşi çıtırdarken kehribar gözleriyle sana bakar.* Yeni gelen sensin demek. Ben Asena. Önce adını öğreneyim.",
            }
            giris = ilk_girisler.get(secilen_karakter, f"Merhaba, ben {karakter_adi}. Sanırım daha önce tanışmadık. Sana nasıl hitap edeyim?")
            await mesajlari_gonder(context.bot, chat_id, "", giris)
            hafiza_al(durum_s).append({"role": "assistant", "content": giris})
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
async def mesaji_isle(update: Update, context: ContextTypes.DEFAULT_TYPE, user_message: str):
    if not yetkili_mi(update):
        return

    user_id = update.effective_user.id
    chat_id = update.effective_chat.id

    if user_id not in kullanici_durumu:
        await update.message.reply_text("Lütfen önce /start yazarak bir karakter seç.")
        return

    durum = kullanici_durumu[user_id]
    secilen_karakter = durum["karakter"]
    hafiza = hafiza_al(durum)
    karakter = KARAKTERLER[secilen_karakter]

    # Açık fotoğraf isteğinde sohbet modelini bekletmeden doğrudan fotoğraf gönder.
    if foto_istegi_mi(user_message):
        durum["chat_id"] = chat_id
        durum["cevapsiz"] = 0
        durum["son_etkilesim"] = time.time()
        esik_belirle(durum)
        try:
            await foto_gonder(
                context.bot, chat_id, karakter,
                caption=(random.choice(FOTO_ALTYAZILARI) if EMOJI_KULLAN else emoji_temizle(random.choice(FOTO_ALTYAZILARI))),
                yakinlik=yakinlik_seviyesi(yakinlik_puani(durum, secilen_karakter)),
                havuzdan=False,
            )
        except Exception as img_error:
            logging.error(f"Görsel isteği hatası: {img_error}")
            await update.message.reply_text("Şu an fotoğrafı hazırlayamadım; biraz sonra tekrar deneyelim.")
        await durum_kaydet(user_id)
        return

    # Kullanıcının açıkça söylediği ad/yaş bilgilerini karakterlerden bağımsız sakla.
    kullanici_bilgisi_ogren(durum, user_message)
    profil_notu = kullanici_profili_prompt(
        durum, getattr(update.effective_user, "first_name", "") or ""
    )
    # İlk karşılama bot tarafından hafızaya yazılır; gerçek tanışma, kullanıcı ilk mesajını gönderince başlar.
    ilk_tanisma = not any(m.get("role") == "user" for m in hafiza)
    durum.setdefault("tanismalar", {})
    if ilk_tanisma:
        durum["tanismalar"][secilen_karakter] = True
    tanisma_notu = (
        "[İLK KARŞILAŞMA] Bu kullanıcıyla ilk kez karşılaşıyorsun. Önceden tanışıklık, ortak anı veya yakınlık varmış gibi konuşma. "
        "Kısa ve doğal bir tanışma yap; adını bilmiyorsan nasıl hitap etmeni istediğini sor. Yaşını bilmiyorsun; gerekirse sohbet ilerleyince öğren. "
        if ilk_tanisma else
        "[DEVAM EDEN TANIŞIKLIK] Yalnızca bu karakterle bu konuşma hafızasında gerçekten yaşanmış olayları ortak geçmiş olarak kullan. "
    )
    sahne_notu = durum.setdefault("sahne_hafizasi", {}).get(secilen_karakter, "")
    sahne_devamlilik = (
        "[SON KAYDEDİLEN SAHNE] " + sahne_notu + "\nKonuşma geçmişinde daha yeni, açık bir geçiş yoksa bu sahne bilgisini koru."
        if sahne_notu else
        "[SAHNE HAFIZASI] Ayrı bir sahne notu yok; hikâye ortamını ve son konuşmalardaki eylemleri esas al, sebepsiz yer/iş değişikliği yapma."
    )
    ekstra_sistem = profil_notu + "\n\n" + tanisma_notu + "\n\n" + sahne_devamlilik

    # Yakınlık puanı (soğuma hesabı için en başta) ve sayaçlar
    eski_sev, yeni_sev = yakinlik_ekle(durum, user_message)
    duygu_guncelle(durum, secilen_karakter, user_message)
    durum["chat_id"] = chat_id
    durum["cevapsiz"] = 0
    durum["son_etkilesim"] = time.time()
    esik_belirle(durum)

    try:
        await context.bot.send_chat_action(chat_id=chat_id, action="typing")
        dusunce, cevap = await llm_cevap(
            secilen_karakter, hafiza, user_message,
            puan=yakinlik_puani(durum, secilen_karakter),
            stil=durum.get("stil", "hikaye"),
            sahne=durum["sahneler"].get(secilen_karakter),
            duygu_notu=duygu_ozeti(durum, secilen_karakter),
            dunya_notu=dunya_ozeti(durum, secilen_karakter),
            ekstra_sistem=ekstra_sistem,
        )
        await cevabi_ilet(context.bot, chat_id, dusunce, cevap)

        # Yalnızca karakterin kendi yanıtında açık bir anlık eylem varsa sahne fotoğrafı gönder.
        # Kullanıcı mesajı tek başına tetikleyici olmaz; böylece geçmiş/varsayımsal eylemlere fotoğraf gitmez.
        bulunan_sahne = otomatik_foto_sahnesi_bul(cevap)
        if bulunan_sahne:
            sahne_key, sahne_prompt = bulunan_sahne
            if otomatik_foto_gonderilmeli(durum, secilen_karakter, sahne_key):
                try:
                    await foto_gonder(
                        context.bot, chat_id, karakter,
                        yakinlik=yakinlik_seviyesi(yakinlik_puani(durum, secilen_karakter)),
                        havuzdan=False, surpriz=True, scene_prompt=sahne_prompt,
                    )
                    durum.setdefault("otomatik_foto_kaydi", {})[secilen_karakter] = {
                        "sahne": sahne_key, "zaman": time.time(),
                    }
                    await durum_kaydet(user_id)
                    logging.info("Sohbet eylem fotoğrafı gönderildi: %s / %s", secilen_karakter, sahne_key)
                except Exception as img_error:
                    # Görsel üretim sorunu sohbet yanıtını başarısız kılmamalı.
                    logging.warning("Sohbet eylem fotoğrafı gönderilemedi: %s", img_error)


        hafiza.append({"role": "user", "content": user_message})
        hafiza.append({"role": "assistant", "content": hafiza_kaydi(dusunce, cevap)})
        hafizayi_kirp(hafiza)
        durum["son_etkilesim"] = time.time()
        await durum_kaydet(user_id)

        if YAKINLIK_BILDIRIM and yeni_sev > eski_sev:
            await context.bot.send_message(
                chat_id=chat_id,
                text=yakinlik_bildirimi(secilen_karakter, karakter, yeni_sev),
            )

        # Yeni yakınlık seviyesini küçük bir fotoğraf sürpriziyle kutla.
        # Her karakter, her seviyede bunu yalnızca bir kez yapar.
        if yeni_sev > eski_sev:
            gonderilenler = durum.setdefault("seviye_foto_gonderildi", {})
            onceki_foto_seviyesi = int(gonderilenler.get(secilen_karakter, -1))
            if yeni_sev > onceki_foto_seviyesi:
                # Önce işaretle: fotoğraf servisi hata verse bile her mesajda tekrar deneme.
                gonderilenler[secilen_karakter] = yeni_sev
                await durum_kaydet(user_id)
                altyazilar = FOTO_SURPRIZ_ALTYAZILARI.get(
                    secilen_karakter, FOTO_SURPRIZ_ALTYAZILARI["default"]
                )
                try:
                    await foto_gonder(
                        context.bot,
                        chat_id,
                        karakter,
                        caption=random.choice(altyazilar),
                        yakinlik=yeni_sev,
                        havuzdan=False,
                        surpriz=True,
                    )
                except Exception as surpriz_hatasi:
                    logging.warning(f"Seviye fotoğraf sürprizi gönderilemedi: {surpriz_hatasi}")

        # Hikâye modunda seviye atlayınca sahne de değişir (özel sahne seçmediysen)
        if yeni_sev > eski_sev and durum.get("stil", "hikaye") == "hikaye" and secilen_karakter not in durum["sahneler"]:
            yeni_sahne = f"*{HIKAYE[secilen_karakter]['sahneler'][yeni_sev]}*"
            await mesajlari_gonder(context.bot, chat_id, "", yeni_sahne)
            hafiza.append({"role": "assistant", "content": yeni_sahne})
            await durum_kaydet(user_id)

    except Exception as e:
        logging.error(f"Pollinations hatası: {e}")
        await update.message.reply_text("Şu an biraz dalgınım, tekrar dener misin? 😅")
        return



async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await mesaji_isle(update, context, update.message.text)


async def post_init(app):
    if DB_AKTIF:
        try:
            yuklenen = await asyncio.to_thread(durumlari_yukle_sync, durum_tamamla)
            kullanici_durumu.update(yuklenen)
            logging.info(f"Kalıcı hafıza açık, {len(yuklenen)} kullanıcı yüklendi.")
            havuz = await asyncio.to_thread(havuz_yukle_sync)
            for k, liste in havuz.items():
                if k in FOTO_HAVUZU:
                    FOTO_HAVUZU[k] = list(liste)
            logging.info("Fotoğraf havuzu yüklendi: " + ", ".join(f"{k}={len(v)}" for k, v in FOTO_HAVUZU.items()))
            yuz_ref = await asyncio.to_thread(redis_komut, "GET", YUZ_REFERANS_ANAHTARI)
            if yuz_ref:
                kayitli_ref = json.loads(yuz_ref)
                for k, file_id in kayitli_ref.items():
                    if k in YUZ_REFERANSLARI:
                        YUZ_REFERANSLARI[k] = file_id
            logging.info("Yüz referansları yüklendi: " + ", ".join(k for k, v in YUZ_REFERANSLARI.items() if v))
        except Exception as e:
            logging.error(f"Hafıza yüklenemedi (RAM ile devam): {e}")
    else:
        logging.warning("UPSTASH_REDIS_REST_URL/TOKEN yok: hafıza sadece RAM'de, yeniden başlayınca silinir.")

    logging.info(f"Fotoğraf: AI Horde img2img açık ({AI_HORDE_IMAGE_MODEL}; denoise 0.40, 25 steps, CFG 6).")
    logging.info("AI Horde: " + ("açık (anahtar " + ("var" if AI_HORDE_KEY != "0000000000" else "yok, anonim") + ")." if AI_HORDE_ACIK else "kapalı."))
    logging.info("Emoji: " + ("açık." if EMOJI_KULLAN else "kapalı."))
    logging.info("NSFW durumu: " + ("AÇIK (tüm karakterler)." if NSFW_ACIK else "KAPALI."))
    logging.info("Türkçe düzeltme geçişi: " + ("açık." if TURKCE_DUZELT else "kapalı."))

    if PROAKTIF_ACIK:
        proaktif_baglam = {
            "TZ": TZ,
            "PROAKTIF_SAAT_ARALIGI": PROAKTIF_SAAT_ARALIGI,
            "PROAKTIF_GUNLUK_LIMIT": PROAKTIF_GUNLUK_LIMIT,
            "PROAKTIF_FOTO_ORANLARI": PROAKTIF_FOTO_ORANLARI,
            "PROAKTIF_FOTO_ARALIK": PROAKTIF_FOTO_ARALIK,
            "kullanici_durumu": kullanici_durumu,
            "KARAKTERLER": KARAKTERLER,
            "yakinlik_seviyesi": yakinlik_seviyesi,
            "yakinlik_puani": yakinlik_puani,
            "llm_cevap": llm_cevap,
            "hafiza_al": hafiza_al,
            "duygu_ozeti": duygu_ozeti,
            "dunya_ozeti": dunya_ozeti,
            "cevabi_ilet": cevabi_ilet,
            "foto_gonder": foto_gonder,
            "otomatik_foto_sahnesi_bul": otomatik_foto_sahnesi_bul,
            "hafiza_kaydi": hafiza_kaydi,
            "hafizayi_kirp": hafizayi_kirp,
            "esik_belirle": esik_belirle,
            "durum_kaydet": durum_kaydet,
        }
        app.bot_data["proaktif_task"] = asyncio.create_task(
            proaktif_dongu(app, proaktif_baglam)
        )
        logging.info("Kendiliğinden mesaj özelliği açık.")


def main():
    if not TOKEN:
        logging.error("HATA: TELEGRAM_BOT_TOKEN bulunamadı!")
        return

    threading.Thread(target=run_health_server, daemon=True).start()
    threading.Thread(target=keep_alive_loop, daemon=True).start()

    application = ApplicationBuilder().token(TOKEN).post_init(post_init).build()

    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("karakter", start_command))
    application.add_handler(CommandHandler("sifirla", sifirla_command))
    application.add_handler(CommandHandler("stil", stil_command))
    application.add_handler(CommandHandler("hikaye", hikaye_command))
    application.add_handler(CommandHandler("sahne", sahne_command))
    application.add_handler(CommandHandler("yakinlik", yakinlik_command))
    application.add_handler(CommandHandler("uret", uret_command))
    application.add_handler(CommandHandler("havuzdoldur", havuzdoldur_command))
    application.add_handler(CommandHandler("havuz", havuz_command))
    application.add_handler(CommandHandler("havuzsil", havuzsil_command))
    application.add_handler(MessageHandler(filters.PHOTO, foto_yukle))
    application.add_handler(CallbackQueryHandler(button_click))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logging.info("Bot çalışmaya başladı...")
    application.run_polling()

if __name__ == '__main__':
    main()
