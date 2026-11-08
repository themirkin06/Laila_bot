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

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
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
    d.setdefault("chat_id", None)
    d.setdefault("son_etkilesim", time.time())
    d.setdefault("cevapsiz", 0)
    d.setdefault("yakinlik", {})
    d.setdefault("son_kullanici", time.time())
    d.setdefault("son_proaktif_foto", 0)
    # Her yakınlık seviyesi için en fazla bir otomatik kutlama fotoğrafı gönderilir.
    d.setdefault("seviye_foto_gonderildi", {})
    d.setdefault("stil", "hikaye")
    d.setdefault("sahneler", {})
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


async def foto_gonder(
    bot, chat_id: int, karakter: dict, caption: str = None,
    yakinlik: int = 0, havuzdan: bool = True, surpriz: bool = False
):
    """Havuzdan veya mevcut görsel sağlayıcısından, ilişki seviyesine uygun fotoğraf gönderir."""
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

    foto_bytes = await foto_uret_bytes(karakter, random.randint(1, 999999), yakinlik=yakinlik, surpriz=surpriz)
    await bot.send_photo(chat_id=chat_id, photo=foto_bytes, caption=caption)


async def cevabi_ilet(bot, chat_id: int, dusunce: str, cevap: str):
    """Karakter yanıtını normal Telegram mesajı olarak gönderir."""
    await mesajlari_gonder(bot, chat_id, dusunce, cevap)


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
        [InlineKeyboardButton("🍲 Ayşe (50, Tatlı, Dedikoducu)", callback_data='sec_ayse')],
        [InlineKeyboardButton("🐺 Asena (43, Kurt Adam Sürüsü, Bilge)", callback_data='sec_dondu')]
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
async def aday_gonder(bot, chat_id: int, key: str):
    """Aday fotoğraf üretir, altına Havuza ekle / At butonları koyar."""
    karakter = KARAKTERLER[key]
    await bot.send_chat_action(chat_id=chat_id, action="upload_photo")
    foto = await foto_uret_bytes(karakter, random.randint(1, 999999))
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
    satirlar.append("\nTek aday için /uret, birkaç aday için /havuzdoldur 5 yaz. Kendi fotoğrafını eklemek için bota fotoğraf gönder (altyazıya karakter adını yazabilirsin).")
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
        await durum_kaydet(user_id)
        await update.message.reply_text("🎬 Sahne yakınlık seviyene göre otomatiğe döndü.")
        return
    metin = metin[:300]
    durum["sahneler"][key] = metin
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

        # Hikâye modunda ilk kez konuşuluyorsa sahne girişi gönderilir
        durum_s = kullanici_durumu[user_id]
        if durum_s.get("stil", "hikaye") == "hikaye" and not hafiza_al(durum_s):
            giris = HIKAYE[secilen_karakter]["giris"]
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
        )
        await cevabi_ilet(context.bot, chat_id, dusunce, cevap)

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

    # --- FOTOĞRAF İSTEĞİ ---
    if foto_istegi_mi(user_message):
        try:
            await foto_gonder(
                context.bot, chat_id, karakter,
                caption=(random.choice(FOTO_ALTYAZILARI) if EMOJI_KULLAN else emoji_temizle(random.choice(FOTO_ALTYAZILARI))),
                yakinlik=yakinlik_seviyesi(yakinlik_puani(durum, secilen_karakter)),
            )
        except Exception as img_error:
            logging.error(f"Görsel hatası: {img_error}")
            await update.message.reply_text("Kameramda bir sorun var sanırım, sonra tekrar dener misin?")


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
        except Exception as e:
            logging.error(f"Hafıza yüklenemedi (RAM ile devam): {e}")
    else:
        logging.warning("UPSTASH_REDIS_REST_URL/TOKEN yok: hafıza sadece RAM'de, yeniden başlayınca silinir.")

    logging.info("Fotoğraf: Cloudflare FLUX " + ("açık." if CF_AKTIF else "kapalı, Pollinations kullanılacak."))
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
