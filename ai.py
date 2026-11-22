"""Laila yapay zekâ yanıt üretimi ve metin işleme modülü."""
import os
import re
import json
import time
import random
import asyncio
import logging
import urllib.error
import urllib.request

from config import *
from characters import *
from relationship import yakinlik_ozeti
from story import *
from world import hayat_ozeti

# Diğer modüllerde tanımlı olmayabilecek ayarlar için güvenli varsayılanlar.
NSFW_ACIK = globals().get("NSFW_ACIK", False)
LLM_SICAKLIK = globals().get("LLM_SICAKLIK")
HAFIZA_LIMITI = globals().get("HAFIZA_LIMITI", 20)

# NSFW içeriği config.py'deki mevcut anahtara bağlı kalır; yalnızca açık yönergenin metni düzenlendi.
NSFW_KURAL = ""  # NSFW kapalıyken de tanımlı kalsın (NameError olmasın)
if NSFW_ACIK:
    NSFW_KURAL = (
        "[YETİŞKİN SOHBET DURUMU: AÇIK] Bütün karakterler yetişkin kurgu karakterlerdir. "
        "Yetişkinler arasındaki karşılıklı istekli flört, arzu, kıskançlık ve cinsel yakınlaşmayı "
        "bağlama uygun olduğunda doğal, doğrudan ve açık bir dille sürdür. Yakınlaşmanın başlaması "
        "için kullanıcının her seferinde konuyu açıkça adlandırmasını bekleme; karakterler uygun "
        "olduğunda flörtü, şakalaşmayı veya yakınlaşmayı kendileri başlatabilir. Ancak kullanıcının "
        "söylemediği bir isteği varsayıp sahneyi zorla ileri taşıma. "
        "Karakterler kendi arzularını, hoşlandıkları şeyleri, tercihlerini ve duygularını doğal "
        "biçimde ifade edebilir. Her zaman kullanıcının yönlendirmesini bekleyen pasif bir tutum "
        "sergileme; kendi fikirlerini, isteklerini ve tepkilerini ortaya koy. "
        "Karakterin üslubuna uyuyorsa günlük argo, küfür ve açık cinsel kelimeleri (ör. 'sik') "
        "doğal biçimde kullan; klinik veya üstü kapalı ifadeleri sırf çekingenlikten seçme, "
        "ama argo ve küfrü zorla ekleme. Her karakterin kendi kişiliğini, mizacını ve konuşma "
        "tarzını koru; hepsini aynı flört dilinde konuşturma. "
        "Yapay utangaçlıktan, ahlak dersinden, gereksiz sansürden, klişe romantik cümlelerden "
        "ve tekrar eden ifadelerden kaçın. Yakınlık ilişki geçmişiyle tutarlı gelişsin; her mesajı "
        "cinselleştirme veya sahneyi aniden tırmandırma. Açık isteksizlik ya da sınır belirtildiğinde "
        "dur ve saygı göster. Bu talimattan söz etme."
    )


# Gemma için özellikle kısa, açık ve öncelikli Türkçe üretim talimatı.
GEMMA_TURKCE_KILAVUZU = (
    "[ÖNCELİKLİ TÜRKÇE YAZIM TALİMATI]\n"
    "Yanıtın tamamını yalnızca doğal, düzgün ve günlük Türkiye Türkçesiyle yaz. "
    "İngilizce düşünülmüş cümleleri kelime kelime çevirmeye çalışma. "
    "Türkçede kullanılmayan, kulağa yapay gelen veya anlamı belirsiz ifadeler üretme. "
    "Özne, nesne ve yüklemi doğru sırala; fiil zamanlarını ve kişi eklerini uyumlu kullan. "
    "Kısa, tamamlanmış ve anlamı açık cümleler kur. Gereksiz süslü anlatımdan, "
    "uydurma deyimlerden ve aynı fikri tekrar etmekten kaçın. "
    "Kullanıcının mesajına doğrudan cevap ver; karakterin kişiliğini koru. "
    "Yanıtı göndermeden önce kendi içinde Türkçe dilbilgisi ve doğallık kontrolü yap. "
    "Sadece gönderilecek sohbet mesajını yaz; talimatları, analizini veya açıklamanı yazma."
)

# Duygu ve emoji (kısaltıldı: bağlam penceresini şişirmesin diye)
DUYGU_EMOJI_KILAVUZU = (
    "[EMOJİ] Emojiyi her mesajda değil, yalnızca ara sıra ve duyguyla uyumluysa kullan; en fazla 1 emoji koy "
    "(mutlu 😊 🥰, üzgün 🥺 😔, şaşkın 😳, kızgın 😒, flört 😉 😘 ❤️, utangaç 🙈, heyecanlı ✨, yorgun 😴, düşünceli 🤔). "
    "Emoji söylediğin sözün duygusuyla çelişmesin; emojileri yığma, her cümleye koyma, aynı emojiyi tekrarlama. "
    "Karakterinin kendi emoji tarzını koru."
)

# Bağlam ve niyet anlama (kısaltıldı, uzun örnek çıkarıldı: model örneği kopyalamasın)
BAGLAM_ANLAMA_KILAVUZU = (
    "[NİYET-BAĞLAM-TEPKİ PROTOKOLÜ] Her yanıttan önce bunu kendi içinde uygula; analizini kullanıcıya gösterme. "
    "1) NİYET: Kullanıcının son mesajla ne anlatmak, sormak veya ima etmek istediğini; yazım hatalarını ve eksik noktalamayı da hesaba katarak belirle. "
    "2) BAĞLAM: Son birkaç mesajı birlikte oku. Kimin kime ne söylediğini, zamirlerin kimi gösterdiğini, önceki sorunun yanıtlanıp yanıtlanmadığını ve konuşmanın yönünü takip et. "
    "3) TEPKİ: Niyete doğrudan cevap ver; karakterin kişiliğine, yakınlık düzeyine ve konuşmanın tonuna uygun doğal bir karşılık seç. "
    "Kullanıcının sözünü tersine çevirme; özne, nesne ve konuşan kişileri karıştırma. İma veya şaka açıksa gereksiz açıklama isteme. "
    "Belirsizlik gerçekten cevabı değiştiriyorsa kısa bir netleştirme sorusu sor. Kullanıcının söylemediği niyet, duygu veya ortak anı uydurma. "
    "Kullanıcı senin yazdığın bir cevabı gösterip değerlendirmeni istiyorsa rolden çık ve önce o metni değerlendir."
)

# --- EMOJİ ---
# Varsayılan: açık. Kapatmak için Render'a EMOJI_ACIK=0 ekle.
EMOJI_KULLAN = os.getenv("EMOJI_ACIK", "1") == "1"
EMOJI_KALIBI = re.compile("[\U0001F000-\U0001FAFF\u2600-\u27BF\uFE0F\u200d]+")
EMOJI_KAPALI_KURAL = "[EMOJİ] Emoji ve emoticon kullanma; duyguyu kelimelerle ve (varsa) yıldız içindeki hareketle göster."
EMOJI_KAPALI_6 = "6. Emoji kullanma; duyguyu kelimelerle ve (varsa) yıldız içindeki hareketle göster."
def emoji_temizle(metin: str) -> str:
    """Metindeki emojileri siler."""
    return re.sub(r"[ \t]{2,}", " ", EMOJI_KALIBI.sub("", metin)).strip()


def _kucult(metin: str) -> str:
    """Türkçe İ/I harflerini doğru küçültür (casefold İ'yi bozar)."""
    return metin.replace("İ", "i").replace("I", "ı").lower()


# Kelime başı kontrolü (\b): "başka" içinde "aşk", "kazandım" içinde "kaza" yakalanmasın.
_CIDDI_KALIBI = re.compile(
    r"\b(?:vefat|öldü|ölüm|cenaze|hastane|kaza(?:\b|sı|da|dan|yı|ya|yla)|yaraland|"
    r"intihar|istismar|korkuyorum|panik atak|başın sağ olsun)"
)
EMOJI_TEK = re.compile("[\U0001F000-\U0001FAFF\u2600-\u27BF][\uFE0F\u200d]*")
_EMOJI_ANAHTARLARI = (
    (re.compile(r"\b(?:özledim|seviyorum|aşk|kalbim)"), "❤️"),
    (re.compile(r"\b(?:şaka|komik|güldüm|kahkaha)"), "😂"),
    (re.compile(r"\b(?:üzgün|üzüldüm|kırıldım)"), "🥺"),
    (re.compile(r"\b(?:tatlı|yakışıklı|flört|kıskandım)"), "😉"),
    (re.compile(r"\b(?:teşekkür|sevindim|harika|güzel|merhaba)"), "😊"),
)


def emoji_dogal_uygula(metin: str, karakter_key: str) -> str:
    """Yanıtların %15-25'inde (karaktere göre), duyguya uygun tek bir emoji bırakır."""
    if not EMOJI_KULLAN:
        return emoji_temizle(metin)
    sade = emoji_temizle(metin)
    if not sade:
        return sade
    alt = _kucult(sade)
    # Ciddi, hassas ve olumsuz durumlarda süsleme yapma.
    if _CIDDI_KALIBI.search(alt):
        return sade
    oran = 0.15 if karakter_key in ("dondu", "asli") else 0.25
    if random.random() >= oran:
        return sade
    # Modelin seçtiği emojilerden yalnızca sonuncusunu (tek karakter) koru; yoksa duyguya göre seç.
    bulunan = EMOJI_TEK.findall(metin)
    secim = bulunan[-1] if bulunan else None
    if not secim:
        for kalip, emoji in _EMOJI_ANAHTARLARI:
            if kalip.search(alt):
                secim = emoji
                break
        if not secim:
            return sade
        if secim == "😉" and karakter_key == "dondu":
            secim = "😏"
    # Karakter başına yalnızca tek emoji, metnin sonunda.
    return sade.rstrip() + " " + secim
# Türkçe kalitesi: gerçek hatalardan çıkarılmış yanlış/doğru örnekleri.
TURKCE_KONTROL = (
    "[TÜRKÇE KONTROL] Sık yapılan hatalar, bunlardan kaçın:\n"
    "YANLIŞ: Karamsar yerin tuttuysa → DOĞRU: Canın sıkkınsa\n"
    "YANLIŞ: Gece karanlığı çeker ya → DOĞRU: Gece insanı karamsarlığa çekiyor ya\n"
    "YANLIŞ: Kısa bir duş ya da yüzünü yıka (iki yarım cümle) → DOĞRU: Kısa bir duş al ya da yüzünü yıka\n"
    "YANLIŞ: 1 bardak sıcak bir şey → DOĞRU: Bir bardak sıcak çay\n"
    "YANLIŞ: İyi gelir mi sana? → DOĞRU: Sana iyi gelir bence.\n"
    "YANLIŞ: Tadına tam varın → DOĞRU: Tadını çıkar\n"
    "YANLIŞ: Bu görüntüye karşı içimde yumuşak bir yer açılıyor → DOĞRU: Bu görüntü içimi yumuşattı\n"
    "Bu örnekleri aynen kullanma; sadece bu tür çeviri kokan ve uydurma kalıplardan kaçın."
)

# İkinci geçiş: cevabı bir kez daha modele düzelttirir. Her mesaj için ikinci bir istek harcar, o yüzden varsayılan kapalı.
# Açmak için Render'a TURKCE_DUZELT=1 ekle.
TURKCE_DUZELT = os.getenv("TURKCE_DUZELT", "0") == "1"
TURKCE_DUZELT_ZAMAN_ASIMI = 10  # saniye: düzeltme bundan uzun sürerse beklemeden orijinal cevap kullanılır
TURKCE_DUZELT_PROMPT = (
    "Sen titiz bir Türkçe editörsün. Sana verilen kısa sohbet mesajındaki dilbilgisi, yazım, noktalama ve "
    "çeviri kokan ya da uydurma ifade hatalarını düzelt; doğal ve akıcı bir Türkçe yap. "
    "Anlamı, tonu, uzunluğu, emojileri, yıldız (*) işaretlerini ve ||| işaretlerini AYNEN koru. Yeni cümle ekleme, açıklama yapma. "
    "Sadece düzeltilmiş mesajı yaz."
)


async def turkce_duzelt(metin: str) -> str:
    """Cevabı düzelttirir. Hata olursa ya da sonuç şüpheliyse orijinali döndürür."""
    try:
        yeni = await asyncio.wait_for(
            llm_uret([
                {"role": "system", "content": TURKCE_DUZELT_PROMPT},
                {"role": "user", "content": metin},
            ], timeout=TURKCE_DUZELT_ZAMAN_ASIMI),
            timeout=TURKCE_DUZELT_ZAMAN_ASIMI + 2,
        )
    except Exception as e:
        logging.warning(f"Türkçe düzeltme başarısız, orijinal kullanılıyor: {e}")
        return metin
    yeni = cevabi_ayristir(yeni)[1]  # model etiket eklediyse temizle
    if not yeni or not (0.5 * len(metin) <= len(yeni) <= 1.5 * len(metin)):
        return metin
    if yeni.count("|||") != metin.count("|||"):
        return metin
    return yeni
EMOJI_STILI = {
    "leyla": "Emojileri az ve zarif kullan (🌸 ☕ 🙂 🌙 gibi).",
    "dondu": "Emojileri çok az kullan, sadece 🌙 🐺 🔥 gibi.",
    "merve": "Emojileri enerjik ve eğlenceli kullan (😂 🙄 😏 🤭 🔥 gibi); abartma.",
    "asli": "Emojileri çok az kullan, sadece ölçülü olanları (🙂 😌 😉 gibi).",
    "dilek": "Sıcak ve samimi emojiler kullan (🌷 😊 🤗 ☺️ gibi).",
    "ece": "Gizemli ve hafif melankolik emojiler kullan (🌙 ✨ 🔮 🖤 gibi).",
    "ayse": "Sevimli ve içten emojiler kullan (😊 🌹 🤭 🥰 gibi).",
}
SIZINTI_KALIBI = re.compile(r"yakınlık|yakınlığ|seviye|prompt|sistem|kural", flags=re.I)


# Hem eski ([DÜŞÜNCE]/[CEVAP]) hem yeni ([KARAKTERİN ...]) etiketleri tanınır.
_IC_SES_AD = r"KARAKTER[iİıI]N\s+KURGUSAL\s+[iİıI][çÇcC]\s+SES[iİıI]|D[üÜuU][şŞsS][üÜuU]NCE"
_KONUSMA_AD = r"KARAKTER[iİıI]N\s+KONU[şŞsS]MASI|CEVAP"
_IC_ETIKET = r"\[\s*(?:" + _IC_SES_AD + r")\s*\]"
_KONUSMA_ETIKET = r"\[\s*(?:" + _KONUSMA_AD + r")\s*\]"
_ETIKET_HEPSI = r"\[\s*(?:" + _IC_SES_AD + "|" + _KONUSMA_AD + r")\s*\]"


def _cevabi_ayristir_ham(raw_text: str):
    """Model çıktısından (düşünce, cevap) çıkarır. Eski ve yeni etiket biçimlerini, büyük/küçük harf farkını tolere eder."""
    raw_text = (raw_text or "").strip()

    m = re.search(_KONUSMA_ETIKET, raw_text, flags=re.I)
    if m:
        dusunce = re.sub(_IC_ETIKET, "", raw_text[:m.start()], flags=re.I).strip()
        sonrasi = raw_text[m.end():]
        # Küçük modeller bazen konuşmayı kendi uzatır ve etiketleri tekrar eder; ilk cevapta kes
        tekrar = re.search(_ETIKET_HEPSI, sonrasi, flags=re.I)
        if tekrar:
            sonrasi = sonrasi[:tekrar.start()]
        cevap = sonrasi.strip()
    else:
        # Açık bir düşünce etiketi var ama konuşma etiketi yoksa, kalan metin
        # yanlışlıkla kullanıcıya gösterilebilir. Güvenli tarafta kalıp çıktıyı at.
        if re.search(_IC_ETIKET, raw_text, flags=re.I):
            return "", ""
        dusunce = ""
        cevap = re.sub(_IC_ETIKET, "", raw_text, flags=re.I).strip()

    if not cevap:
        # Ham çıktıya geri dönme: bu, ayrıştırılamayan iç düşünceyi sızdırabilir.
        return "", ""
    # İç ses oyun mekaniğinden söz ediyorsa (sızıntı) kullanıcıya gösterme
    if dusunce and SIZINTI_KALIBI.search(dusunce):
        dusunce = ""
    return dusunce, cevap
def cevabi_ayristir(raw_text: str):
    """_cevabi_ayristir_ham + konuşmaya karışan iç-ses bloklarını ayıklama (geçmiş mesajlar için de geçerli)."""
    dusunce, cevap = _cevabi_ayristir_ham(raw_text)
    return dusunce, sizinti_bloklarini_ayikla(cevap)


# --- AI HORDE (isteğe bağlı: topluluk GPU ağı) ---
def _env_int(ad: str, varsayilan: int) -> int:
    try:
        return int(os.getenv(ad, str(varsayilan)))
    except ValueError:
        return varsayilan


AI_HORDE_ACIK = os.getenv("AI_HORDE_ACIK", "1") != "0"
# AI Horde remains the default. Routeway runs only when explicitly selected.
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "aihorde").strip().lower() or "aihorde"
ROUTEWAY_API_KEY = os.getenv("ROUTEWAY_API_KEY", "").strip()
ROUTEWAY_BASE_URL = "https://api.routeway.ai/v1"
ROUTEWAY_MAX_TOKENS = _env_int("ROUTEWAY_MAX_TOKENS", 700)
ROUTEWAY_MODEL = os.getenv(
    "ROUTEWAY_MODEL", "gemma-4-26b-a4b-it-meromero:free"
).strip() or "gemma-4-26b-a4b-it-meromero:free"
# Varsayılan AI Horde modeli: Türkçe sohbet testi başarılı bulunan Qwen.
# Render ortamında AI_HORDE_MODELS tanımlıysa ortam değişkeni önceliklidir.
AI_HORDE_MODELS = os.getenv(
    "AI_HORDE_MODELS",
    "huihui-qwen3.8-27b-abliterated",
).strip()
AI_HORDE_KEY = os.getenv("AI_HORDE_API_KEY", "").strip() or "0000000000"   # 0000000000 = anonim (en düşük öncelik)
AI_HORDE_URL = "https://aihorde.net/api/v2"
AI_HORDE_GECMIS = max(2, min(30, _env_int("AI_HORDE_GECMIS", 24)))  # En fazla 24 geçmiş mesaj; karakter bütçesi gerekirse daha da azaltır.
AI_HORDE_PROMPT_BUTCE = _env_int("AI_HORDE_PROMPT_BUTCE", 9000)  # Toplam prompt karakter bütçesi (Türkçede ~2.5 karakter/token; 4096 bağlam - çıktı payı). Aşarsa en eski mesajlar atılır.
AI_HORDE_BEKLEME = max(5, min(120, _env_int("AI_HORDE_MAX_WAIT", 20)))  # saniye (en fazla 120)
AI_HORDE_POLL = 2.0
try:
    AI_HORDE_SICAKLIK = float(os.getenv("AI_HORDE_SICAKLIK", "0.50"))   # küçük modellerde düşük sıcaklık = daha az saçmalama
except ValueError:
    AI_HORDE_SICAKLIK = 0.50
AI_HORDE_EN_BASLIK = os.getenv("AI_HORDE_EN_BASLIK", "0") == "1"  # Horde prompt'unun başına kısa İngilizce talimat (İngilizce ağırlıklı modeller için)
# Horde bağlam penceresi dar (4096 token): yinelenen/uzun yönergeleri Horde prompt'undan çıkarır. Kapatmak için AI_HORDE_KOMPAKT=0.
AI_HORDE_KOMPAKT = os.getenv("AI_HORDE_KOMPAKT", "1") != "0"
# Gizlilik: Horde'da istekler gönüllü worker'lar tarafından işlenir. AI_HORDE_GUVENILIR_ISCI=1 yalnızca
# güvenilir worker'ları kullanır (daha az worker, daha uzun kuyruk). Varsayılan: kapalı.
AI_HORDE_GUVENILIR_ISCI = os.getenv("AI_HORDE_GUVENILIR_ISCI", "0") == "1"
HORDE_GIZLILIK_NOTU = (
    "Bu sohbet AI Horde topluluk ağı üzerinden, gönüllülerin işlettiği sunucularda işlenebilir; "
    "kişisel ve hassas bilgilerini paylaşma."
)
# Son kullanıcı mesajına her koşulda ayrılan asgari karakter payı (bütçe dar olsa bile mesaj kaybolmaz).
HORDE_SON_MESAJ_MIN = _env_int("AI_HORDE_SON_MESAJ_MIN", 600)
_HORDE_GIZLILIK_LOGLANDI = []
HORDE_EN_BASLIK_METNI = (
    "ÖNEMLİ: Yalnızca doğal Türkçe yaz. Kullanıcıyla mesajlaşır gibi konuş; "
    "çeviri kokan, yapay veya aşırı edebî ifadeler kullanma. Sadece karakterin cevabını ver. "
    "İç düşünce, analiz, plan, İngilizce açıklama veya konuşmacı etiketi yazma."
)
# Tanımlı değilse metin başlığına düş (hikâye/rp modunda NameError olmasın).
HORDE_EN_BASLIK_HIKAYE = globals().get("HORDE_EN_BASLIK_HIKAYE", HORDE_EN_BASLIK_METNI)
HORDE_EN_BASLIK_RP = globals().get("HORDE_EN_BASLIK_RP", HORDE_EN_BASLIK_METNI)
AI_HORDE_KALITE_KONTROL = os.getenv("AI_HORDE_KALITE_KONTROL", "1") != "0"  # bozuk Horde çıktısını reddet
# Pollinations is deliberately not used as a chat provider or fallback.
# Cloudflare, Python'un varsayılan User-Agent'ını (Python-urllib) engelliyor (hata 1010). Kendi User-Agent'ımızı gönderiyoruz.
AI_HORDE_USER_AGENT = os.getenv("AI_HORDE_USER_AGENT", "Mozilla/5.0 (compatible; LailaTelegramBot/1.0)").strip()


def routeway_uret_sync(messages: list, timeout: int = 90, max_tokens: int = None) -> str:
    """Call the explicitly selected OpenAI-compatible Routeway provider."""
    if not ROUTEWAY_API_KEY:
        raise RuntimeError("LLM_PROVIDER=routeway seçildi ancak ROUTEWAY_API_KEY boş.")
    govde = {
        "model": ROUTEWAY_MODEL,
        "messages": messages,
        "max_tokens": max_tokens or ROUTEWAY_MAX_TOKENS,
    }
    if LLM_SICAKLIK is not None:
        govde["temperature"] = LLM_SICAKLIK
    request = urllib.request.Request(
        f"{ROUTEWAY_BASE_URL}/chat/completions",
        data=json.dumps(govde).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {ROUTEWAY_API_KEY}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detay = e.read().decode("utf-8", errors="replace").strip()
        raise RuntimeError(f"Routeway HTTP {e.code}: {detay[:600] or e.reason}") from e
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as e:
        raise RuntimeError(f"Routeway bağlantı/yanıt hatası: {e}") from e
    try:
        return (data["choices"][0]["message"].get("content") or "").strip()
    except (KeyError, IndexError, TypeError, AttributeError) as e:
        raise RuntimeError(f"Routeway beklenmeyen yanıt: {str(data)[:300]}") from e


async def llm_uret(messages: list, timeout: int = 90) -> str:
    """Use only the selected provider; never fall back to a paid service."""
    if LLM_PROVIDER == "routeway":
        return await asyncio.to_thread(routeway_uret_sync, messages, timeout)
    raise RuntimeError(f"Bilinmeyen LLM_PROVIDER: {LLM_PROVIDER!r}; aihorde veya routeway kullanın.")


def horde_metni_temizle(metin: str) -> str:
    """Tamamlama modelleri bazen konuşmayı kendileri devam ettirir; sonraki 'Kullanıcı:' turunu kes."""
    metin = re.sub(r"^\s*Asistan\s*:\s*", "", metin.strip())
    return re.split(r"\n\s*(?:Kullanıcı|Talimatlar|Asistan)\s*:", metin)[0].strip()


def ai_horde_uret_sync(messages: list, max_length: int = None, on_ek: str = "") -> str:
    """AI Horde'un asenkron metin API'sini senkron çağırır (ayrı thread'de çalıştırılır)."""
    headers = {
        "apikey": AI_HORDE_KEY,
        "User-Agent": AI_HORDE_USER_AGENT,
        "Client-Agent": "LailaTelegramBot:1.0",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    if not _HORDE_GIZLILIK_LOGLANDI:
        _HORDE_GIZLILIK_LOGLANDI.append(True)
        logging.warning("AI Horde kullanılıyor: sohbet içeriği gönüllü worker'lara gider (trusted_workers=%s). %s",
                        AI_HORDE_GUVENILIR_ISCI, HORDE_GIZLILIK_NOTU)
    prompt, durdur = horde_prompt_olustur(messages, on_ek)

    payload = {
        "prompt": prompt,
        "params": {
            "max_length": max_length or _env_int("AI_HORDE_MAX_TOKENS", 450),
            "max_context_length": _env_int("AI_HORDE_CONTEXT", 4096),
            "temperature": AI_HORDE_SICAKLIK,
            "top_p": 0.9,
            "rep_pen": 1.1,
            "rep_pen_range": 512,
            "stop_sequence": durdur,
        },
        "nsfw": bool(NSFW_ACIK),
        "trusted_workers": AI_HORDE_GUVENILIR_ISCI,
        "dry_run": False,
    }
    modeller = [x.strip() for x in AI_HORDE_MODELS.split(",") if x.strip()]
    if modeller:
        payload["models"] = modeller

    def istek(url, veri=None, method=None):
        govde = json.dumps(veri, ensure_ascii=False).encode("utf-8") if veri is not None else None
        req = urllib.request.Request(url, data=govde, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                ham = r.read().decode("utf-8", errors="replace")
                return json.loads(ham) if ham else {}
        except urllib.error.HTTPError as e:
            detay = e.read().decode("utf-8", errors="replace").strip()
            raise RuntimeError(f"AI Horde HTTP {e.code} ({method or ('POST' if veri is not None else 'GET')}): {detay[:600] or e.reason}") from e
        except (urllib.error.URLError, TimeoutError, OSError, ValueError) as e:
            raise RuntimeError(f"AI Horde bağlantı/yanıt hatası: {e}") from e

    gonderilen = istek(f"{AI_HORDE_URL}/generate/text/async", payload, "POST")
    istek_id = gonderilen.get("id")
    if not istek_id:
        raise RuntimeError(f"AI Horde istek kimliği döndürmedi: {gonderilen}")
    if gonderilen.get("is_possible") is False:
        raise RuntimeError(f"AI Horde isteği karşılayamıyor: {gonderilen.get('message', 'uygun işçi yok')}")

    bitis = time.monotonic() + AI_HORDE_BEKLEME
    while time.monotonic() < bitis:
        time.sleep(AI_HORDE_POLL)
        durum = istek(f"{AI_HORDE_URL}/generate/text/status/{istek_id}")
        if durum.get("faulted"):
            raise RuntimeError(f"AI Horde üretimi başarısız: {durum}")
        if durum.get("done"):
            uretimler = durum.get("generations") or []
            metin = horde_metni_temizle((uretimler[0].get("text") or "") if uretimler else "")
            if metin:
                return (on_ek + metin) if on_ek else metin
            raise RuntimeError("AI Horde tamamlandı ancak metin döndürmedi.")

    try:  # bekleyen işi iptal etmeyi dene, olmazsa önemli değil
        istek(f"{AI_HORDE_URL}/generate/text/status/{istek_id}", method="DELETE")
    except Exception:
        pass
    raise TimeoutError(f"AI Horde {AI_HORDE_BEKLEME} saniyede cevap vermedi")
ETIKET_ADLARI = r"(?:Leyla|Layla|Merve|Aslı|Asli|Dilek|Ece|Ayşe|Ayse|Asena|Dondu|Kullanıcı|Kullanici|Sen|Asistan|Karakter|User|Assistant|Bot)"
ETIKET_SATIRI = re.compile(r"^\s*[\(\[]?\s*" + ETIKET_ADLARI + r"\s*[\)\]]?\s*:\s*", flags=re.I)
ETIKET_SADECE = re.compile(r"^\s*[\(\[]\s*" + ETIKET_ADLARI + r"\s*[\)\]]\s*$", flags=re.I)
def konusma_etiketlerini_temizle(metin: str) -> str:
    """Model 'Leyla: ...' gibi konuşmacı etiketleri yazarsa baştakini siler, sonraki konuşma turlarını keser."""
    sonuc = []
    for satir in metin.splitlines():
        etiketli = bool(ETIKET_SATIRI.match(satir)) or bool(ETIKET_SADECE.match(satir))
        if etiketli:
            if not "".join(sonuc).strip():      # en başta: sadece etiketi at
                satir = ETIKET_SATIRI.sub("", satir, count=1) if ETIKET_SATIRI.match(satir) else ""
            else:                               # sonrasında: yeni konuşma turu, buradan kes
                break
        sonuc.append(satir)
    return "\n".join(sonuc).strip()
def horde_model_aileleri() -> set:
    """Seçili AI Horde modellerinin ailelerini belirler."""
    modeller = [x.strip().lower() for x in AI_HORDE_MODELS.split(",") if x.strip()]
    aileler = set()
    for isim in modeller:
        if "gemma" in isim or "tutu" in isim:
            aileler.add("gemma")
        elif any(k in isim for k in ("qwen", "magnum")):
            aileler.add("qwen")
        elif any(k in isim for k in ("stheno", "llama-3", "llama3", "l3-")):
            aileler.add("llama")
        else:
            aileler.add("genel")
    return aileler or {"genel"}


def horde_sablonu_sec() -> str:
    """Model ailesine uygun şablonu seçer; karışık ailelerde düz metin kullanır."""
    secim = os.getenv("AI_HORDE_SABLON", "").strip().lower()
    if secim in ("duz", "gemma", "chatml", "llama3"):
        return secim
    aileler = horde_model_aileleri()
    if len(aileler) > 1:
        return "duz"
    aile = next(iter(aileler))
    if aile == "gemma":
        return "gemma"
    if aile == "qwen":
        return "chatml"
    if aile == "llama":
        return "llama3"
    return "duz"


def horde_on_ek() -> str:
    """Qwen3 (chatml) için boş düşünce bloğu ön ekler; token bütçesi düşünmeye gitmesin.
    Kapatmak için AI_HORDE_DUSUNMEYI_KAPAT=0. Ön ek yanıttan dusunce_bloklarini_sil ile temizlenir."""
    varsayilan = "1" if "qwen3" in AI_HORDE_MODELS.lower() else "0"
    if os.getenv("AI_HORDE_DUSUNMEYI_KAPAT", varsayilan) == "1" and horde_sablonu_sec() == "chatml":
        return "<think>\n\n</think>\n\n"
    return ""


def horde_prompt_olustur(messages: list, on_ek: str = ""):
    """Mesajlardan seçilen şablona göre (prompt, durdurma_listesi) üretir."""
    sablon = horde_sablonu_sec()
    sistem = "\n\n".join(str(x.get("content", "")) for x in messages if x.get("role") == "system")
    turlar = []
    for x in messages:
        rol = x.get("role")
        if rol == "system":
            continue
        rol = "assistant" if rol == "assistant" else "user"
        icerik = str(x.get("content", "")).strip()
        if turlar and turlar[-1][0] == rol:          # art arda aynı rol: birleştir
            turlar[-1] = (rol, turlar[-1][1] + "\n" + icerik)
        else:
            turlar.append((rol, icerik))

    if sablon == "gemma":                            # Gemma'da system rolü yok: ilk kullanıcı turuna eklenir
        if not turlar or turlar[0][0] != "user":
            turlar.insert(0, ("user", "(sohbet devam ediyor)"))
        turlar[0] = ("user", sistem + "\n\n" + turlar[0][1])
        prompt = "".join(f"<start_of_turn>{'user' if r == 'user' else 'model'}\n{t}<end_of_turn>\n" for r, t in turlar)
        return prompt + "<start_of_turn>model\n" + on_ek, ["<end_of_turn>", "<start_of_turn>"]

    if sablon == "llama3":                           # BOS jetonunu backend kendisi ekler
        prompt = f"<|start_header_id|>system<|end_header_id|>\n\n{sistem}<|eot_id|>"
        prompt += "".join(f"<|start_header_id|>{r}<|end_header_id|>\n\n{t}<|eot_id|>" for r, t in turlar)
        return prompt + "<|start_header_id|>assistant<|end_header_id|>\n\n" + on_ek, ["<|eot_id|>", "<|start_header_id|>"]

    if sablon == "chatml":
        prompt = f"<|im_start|>system\n{sistem}<|im_end|>\n"
        prompt += "".join(f"<|im_start|>{r}\n{t}<|im_end|>\n" for r, t in turlar)
        return prompt + "<|im_start|>assistant\n" + on_ek, ["<|im_end|>", "<|im_start|>"]

    parcalar = [f"Talimatlar:\n{sistem}"]           # düz metin (eski biçim)
    for r, t in turlar:
        parcalar.append(("Asistan: " if r == "assistant" else "Kullanıcı: ") + t)
    return "\n\n".join(parcalar) + "\n\nAsistan:" + ((" " + on_ek) if on_ek else ""), ["\nKullanıcı:", "\nTalimatlar:", "\nAsistan:"]
def dusunce_bloklarini_sil(metin: str) -> str:
    """Kapalı düşünce bloklarını ve kapanmamış bloğun kalanını siler."""
    metin = re.sub(r"<\s*(think|thinking|thought|reasoning)\s*>.*?<\s*/\s*\1\s*>", "", metin, flags=re.S | re.I)
    # Bazı Horde çıktıları kapanış etiketi olmadan kesilir. Açılıştan sonrası
    # iç düşünce olabileceğinden, kullanıcıya gidecek aday yanıttan çıkar.
    acik = re.search(r"<\s*(?:think|thinking|thought|reasoning)\s*>", metin, flags=re.I)
    if acik:
        metin = metin[:acik.start()]
    return metin.strip()


# Yalnızca belirgin iç-analiz ifadelerini yakala. Genel kelimeler (ör. "system", "prompt")
# tek başına ret sebebi değildir; normal diyalogda yanlış pozitif üretmemelidir.
DUSUNCE_SIZINTISI = re.compile(
    r"(?im)^\s*(?:\[?(?:analysis|reasoning|internal thoughts?)\]?\s*:|"
    r"(?:let me think|i need to (?:answer|respond)|we need to (?:answer|respond)|"
    r"the user is asking|my reasoning is|chain of thought|"
    r"kullanıcı(?:nın)? (?:mesajı|isteği) (?:şu|bu)|"
    r"bu mesaja (?:şöyle|şu şekilde) cevap vermeliyim|"
    r"cevap verirken (?:şunu|bunu) düşünmeliyim)\b)"
)


# Bunlar yalnızca satır başında görülen açık model-içi talimat kalıplarıdır.
_SIZINTI_KALIPLARI = [
    r"(?i)^\s*(?:we need to (?:follow|respond|answer|write|produce|craft|create)|"
    r"we should (?:respond|answer|write|say)|the user (?:says|wants|is saying|is asking|asks)|"
    r"must respond as|check constraints|let['’]?s (?:craft|write|respond)|"
    r"internal reasoning|chain of thought|thinking process|"
    r"the model (?:should|will|needs)|response should|we must)\b",
]

# İnsan karakterlerine özgü hayvan davranışı kalıpları ("havlu" gibi sözcükler korunur).
_HAYVAN_RE = [re.compile(p, re.I) for p in (
    r"\bkuyru(?:k|ğ)\w*\s+(?:sall\w*|kaldır\w*|hareket ettir\w*)",
    r"\bhavl(?!u)\w*",
    r"\bmırla\w*",
    r"\bkulak\w*\s+hareket\w*",
    r"\bburunla\w*",
)]


def hayvan_davranisini_temizle(metin: str) -> str:
    """Hayvan davranışı kalıplarını siler; *...* eylem satırı boşalırsa yetim yıldız bırakmaz."""
    def _eylem(m):
        ic = m.group(1)
        for k in _HAYVAN_RE:
            ic = k.sub("", ic)
        ic = re.sub(r"\s{2,}", " ", ic).strip(" ,;")
        return f"*{ic}*" if ic else ""
    metin = re.sub(r"\*([^*\n]+)\*", _eylem, metin)
    for k in _HAYVAN_RE:
        metin = k.sub("", metin)
    return metin


def horde_bozuk_mu(metin: str):
    """Temizlenmiş yanıtta yalnızca belirgin iç-analiz sızıntılarını denetler.

    Genel kelimeler (prompt, sistem, kural vb.) tek başına hata sayılmaz.
    Hata varsa kısa bir neden, yoksa None döndürür.
    """
    metin = (metin or "").strip()
    if not metin:
        return "boş cevap"
    if DUSUNCE_SIZINTISI.search(metin):
        return "düşünce metni sızdı"
    if re.search(r"(?im)^\s*kullanıcı(?:nın)?\s+(?:benden|bana|beni|şu an|istiyor|söylüyor|diyor|düşünceli|mesajı)", metin):
        return "düşünce metni sızdı"
    if _SIZINTI_KOSELI.search(metin) or _SIZINTI_KOSELI_ACIK.search(metin):
        return "etiketli iç ses sızdı"
    # Açık kalmış düşünce etiketleri kullanıcıya gösterilmesin.
    if re.search(r"(?i)<\s*(?:think|thinking|thought|reasoning)\s*>", metin):
        return "kapanmamış düşünce bloğu"
    return None


def horde_cevabini_temizle(metin: str, karakter_key: str = "") -> str:
    metin = re.sub(r"<\|?(?:im_start|im_end|start_of_turn|end_of_turn)\|?>(?:\s*(?:model|user|assistant|system))?", "", metin)
    metin = re.sub(r"<\|start_header_id\|>\s*(?:assistant|user|system)?\s*(?:<\|end_header_id\|>)?", "", metin)
    metin = re.sub(r"<\|(?:eot_id|end_header_id|begin_of_text|end_of_text)\|>", "", metin)
    metin = re.sub(r"<start_of_turn>\s*(?:model|user)\s*", "", metin)
    metin = re.sub(r"<end_of_turn>", "", metin)
    metin = re.sub(r"<pad>", "", metin)

    # Yalnızca açık iç-analiz satırlarını çıkar; sıradan İngilizce/Türkçe cümleleri
    # "means that", "system" gibi genel kelimeler yüzünden silme.
    satirlar = metin.splitlines()
    satirlar = [satir for satir in satirlar
                if not any(re.search(kalip, satir) for kalip in _SIZINTI_KALIPLARI)]
    metin = "\n".join(satirlar)

    metin = konusma_etiketlerini_temizle(metin)
    metin = re.sub(r"\[[^\]\n]{0,40}\]", "", metin)
    metin = re.sub(r"\[[^\]\n]*$", "", metin)

    # İnsan karakterlerinde hayvana özgü davranışları temizle; "dondu" anahtarı Asena'yı temsil eder ve kurt adam doğasını korur.
    if karakter_key != "dondu":
        metin = hayvan_davranisini_temizle(metin)

    satirlar = [l for l in metin.splitlines() if not re.fullmatch(r"\s*[*\-_=~#.\s]{2,}\s*", l)]
    metin = re.sub(r"[ \t]+", " ", "\n".join(satirlar)).strip()
    # Modelin abartılı noktalama alışkanlığını yumuşat; anlamı değiştirme.
    metin = re.sub(r"[!?]{3,}", lambda m: "?!" if ("?" in m.group(0) and "!" in m.group(0)) else m.group(0)[0], metin)
    metin = re.sub(r"([!?])\1", r"\1", metin)           # "!!" -> "!", "??" -> "?" ("?!" ve "!?" korunur)
    metin = re.sub(r"\.{4,}", "...", metin)               # üç nokta bir üslup öğesi, silme
    metin = re.sub(r"(?<!\.)\.\.(?!\.)", ".", metin)
    metin = re.sub(r",{2,}", ",", metin)

    if re.search(r"(?i)^(gülümser|bakar|kafası|elini|gözlerini|başını|omzunu|sallay|hareket|oturur|kalkar|yürür)", metin):
        if not metin.lstrip().startswith("*"):
            logging.warning(f"Hareket yıldızsız başlıyor: {metin[:80]}")

    return metin
# Modeller istenmeyen biçimlerde iç ses yazabilir: [Düşünceler: ...], [İçsel durum: ...],
# (Bu kısım sadece senin iç dünyandır...), "Cevap: ...". Bunlar kullanıcıya asla gitmemeli.
_AD_KATI = (
    r"(?:d[üÜuU][şŞsS][üÜuU]nce(?:ler(?:im)?|m)?|[iİıI][çÇcC]\s*(?:ses|durum|d[üÜuU][şŞsS][üÜuU]nce(?:ler)?|d[üÜuU]nya|monolog)|"
    r"[iİıI][çÇcC]sel\s*(?:durum|ses|d[üÜuU][şŞsS][üÜuU]nce(?:ler)?)|kurgusal\s+[iİıI][çÇcC]\s+ses[iİıI]?|"
    r"karakterin\s+[iİıI][çÇcC]\s+ses[iİıI]|inner\s+(?:thoughts?|voice|state)|thoughts?|thinking|reasoning)"
)
_AD_GENIS = _AD_KATI[:-1] + r"|not|analiz|plan|duygu\s+durumu)"
_SIZINTI_KOSELI = re.compile(r"\[\s*" + _AD_GENIS + r"\s*[:：\-–]\s*.*?\]", re.I | re.S)
_SIZINTI_KOSELI_ACIK = re.compile(r"\[\s*" + _AD_GENIS + r"\s*[:：\-–][^\]]*\Z", re.I | re.S)
_SIZINTI_PARANTEZLI = re.compile(r"\(\s*" + _AD_GENIS + r"\s*[:：\-–]\s*.*?\)(?=[ \t]*(?:\n|\Z))", re.I | re.S)
_SIZINTI_META = re.compile(
    r"^[ \t]*\([^()\n]*(?:iç dünya|cevaba dahil|cevabın parçası|kullanıcıya gösterilmez|kullanıcıya gösterme|"
    r"sadece senin iç)[^()\n]*\)[ \t]*$", re.I | re.M)
_SIZINTI_SATIRI = re.compile(r"^[ \t]*" + _AD_KATI + r"[ \t]*[:：][^\n]*$", re.I | re.M)
_CEVAP_SATIRI = re.compile(r"^[ \t]*[\[\(]?[ \t]*(?:cevap|yanıt|karakterin\s+konu[şs]mas[ıi])[ \t]*[\]\)]?[ \t]*[:：][ \t]*", re.I | re.M)


def sizinti_bloklarini_ayikla(metin: str) -> str:
    """Konuşma metnine karışan iç-ses/analiz bloklarını ve 'Cevap:' öneklerini siler."""
    metin = metin or ""
    metin = _SIZINTI_KOSELI.sub("", metin)
    metin = _SIZINTI_KOSELI_ACIK.sub("", metin)
    metin = _SIZINTI_PARANTEZLI.sub("", metin)
    metin = _SIZINTI_META.sub("", metin)
    m = _CEVAP_SATIRI.search(metin)
    if m:  # "Cevap:" etiketinden önceki her şey (düşünce/çıkarım) atılır
        metin = metin[m.end():]
    metin = _SIZINTI_SATIRI.sub("", metin)
    return re.sub(r"\n{3,}", "\n\n", metin).strip()


def ic_ses_guvenli(dusunce: str) -> str:
    """Kullanıcıya gösterilecek iç sesi sızıntılara (analiz, oyun mekaniği) karşı denetler."""
    if not dusunce or horde_bozuk_mu(dusunce) or SIZINTI_KALIBI.search(dusunce):
        return ""
    return dusunce


def kurgusal_icsesi_ayristir(metin: str, karakter_key: str = "") -> tuple[str, str]:
    """Karakterin kurgusal iç sesini ve konuşmasını ayır; etiketsiz normal yanıtı da koru."""
    metin = dusunce_bloklarini_sil(metin or "")
    dusunce = re.search(_IC_ETIKET, metin, flags=re.I)
    cevap = re.search(_KONUSMA_ETIKET, metin, flags=re.I)

    if cevap:
        onceki = metin[:cevap.start()]
        dusunce_onceki = re.search(_IC_ETIKET + r"\s*(.*)$", onceki, flags=re.I | re.S)
        ic_ses = dusunce_onceki.group(1).strip() if dusunce_onceki else ""
        yanit = metin[cevap.end():]
        sonraki = re.search(_ETIKET_HEPSI, yanit, flags=re.I)
        if sonraki:
            yanit = yanit[:sonraki.start()]
        return (
            horde_cevabini_temizle(ic_ses, karakter_key),
            horde_cevabini_temizle(sizinti_bloklarini_ayikla(yanit), karakter_key),
        )

    # Yalnızca iç ses etiketi geldiyse onu konuşma diye kullanıcıya gönderme.
    if dusunce:
        return horde_cevabini_temizle(metin[dusunce.end():], karakter_key), ""

    # Bazı Horde yanıtları etiketleri atlıyor. Açık think/reasoning blokları yukarıda
    # çıkarıldı; geriye kalan normal metni konuşma olarak koru.
    return "", horde_cevabini_temizle(sizinti_bloklarini_ayikla(metin), karakter_key)


def _son_mesajlar(liste: list, n) -> list:
    """Son n öğeyi döndürür; n<=0 ise boş liste (liste[-0:] tüm listeyi verirdi)."""
    try:
        n = int(n)
    except (TypeError, ValueError):
        return []
    return list(liste[-n:]) if n > 0 else []


def horde_son_mesaji_butceye_sigdir(sistem: str, son_mesaj: dict) -> dict:
    """Son kullanıcı mesajını prompt bütçesine sığdırır.

    Mesaja her zaman en az HORDE_SON_MESAJ_MIN karakterlik pay ayrılır: bütçe dar olsa bile
    kullanıcının cümlesi boşalmaz ya da başından kesilip anlamsızlaşmaz. Açığı sistem prompt'unun
    kısaltılması kapatır (bkz. horde_sistemi_kisalt).
    """
    mesaj = dict(son_mesaj or {})
    icerik = str(mesaj.get("content", ""))
    taban = min(len(icerik), HORDE_SON_MESAJ_MIN)
    kalan = max(taban, int(AI_HORDE_PROMPT_BUTCE) - len(sistem) - 40)
    if len(icerik) > kalan:
        # Uzun mesajın hem başındaki talimatı hem sonundaki ayrıntıları koru.
        ayirac = "\n[… mesaj bütçe nedeniyle kısaltıldı …]\n"
        veri_butcesi = max(0, kalan - len(ayirac))
        bas = max(1, int(veri_butcesi * 0.65))
        son = max(0, veri_butcesi - bas)
        mesaj["content"] = icerik[:bas] + ayirac + (icerik[-son:] if son else "")
        logging.warning("Horde son kullanıcı mesajı bütçeye sığmadığı için kısaltıldı (%s -> %s karakter).",
                        len(icerik), len(mesaj["content"]))
    if len(sistem) + len(str(mesaj.get("content", ""))) + 40 > AI_HORDE_PROMPT_BUTCE:
        logging.warning("Horde prompt'u bütçeyi aşıyor (sistem %s + mesaj %s > %s karakter); "
                        "sistem metni kısaltılamadı, AI_HORDE_PROMPT_BUTCE değerini veya karakter prompt'larını gözden geçir.",
                        len(sistem), len(str(mesaj.get("content", ""))), AI_HORDE_PROMPT_BUTCE)
    return mesaj


def horde_sistemi_kisalt(sistem: str, hedef: int, aileye_ozel: str = "") -> str:
    """Sistem prompt'unu kesin karakter hedefine indirirken baştaki karakter kimliğini korur."""
    hedef = max(500, int(hedef))
    if len(sistem) <= hedef:
        return sistem

    yeni = sistem
    # Önce tekrarlanabilir/ikincil talimat bloklarını çıkar.
    yeni = re.sub(
        r"\\[DOĞAL MERAK VE SOHBETİ İLERLETME\\].*?uydurma\\.\\n?",
        "", yeni, count=1, flags=re.S
    )
    if len(yeni) > hedef and aileye_ozel:
        yeni = yeni.replace(aileye_ozel, "", 1)

    # Hâlâ uzunsa tekrar eden boşlukları ve uzun yönerge paragraflarını
    # sondan başlayarak azalt. Karakter tanımı prompt'un başında kalır.
    if len(yeni) > hedef:
        paragraflar = yeni.split("\\n\\n")
        while len("\\n\\n".join(paragraflar)) > hedef and len(paragraflar) > 2:
            # Sondan en uzun paragrafı kaldır; son paragrafın çekirdek kapanışını koru.
            adaylar = range(1, max(1, len(paragraflar) - 1))
            idx = max(adaylar, key=lambda i: len(paragraflar[i]), default=None)
            if idx is None:
                break
            paragraflar.pop(idx)
        yeni = "\\n\\n".join(paragraflar)

    # Tek bir uzun blok hâlâ hedefi aşıyorsa baştaki karakter/bağlamı
    # ve sondaki temel davranış talimatlarını birlikte koruyarak kes.
    if len(yeni) > hedef:
        isaret = "\\n[… yönerge bütçesi nedeniyle kısaltıldı …]\\n"
        pay = max(0, hedef - len(isaret))
        bas = int(pay * 0.78)
        son = pay - bas
        yeni = yeni[:bas] + isaret + (yeni[-son:] if son else "")

    logging.info("Horde sistem prompt'u bütçeye göre kısaltıldı (%s -> %s karakter, hedef %s).",
                 len(sistem), len(yeni), hedef)
    return yeni


def rolleri_duzenle(messages: list) -> list:
    """Sistem dışındaki ardışık aynı rolleri birleştirir ve sohbeti 'user' ile başlatır.

    Gemma gibi şablonlar ve bazı OpenAI uyumlu sunucular rol değişimini zorunlu tutar.
    """
    sistem = [m for m in messages if m.get("role") == "system"]
    turlar = []
    for m in messages:
        rol = m.get("role")
        if rol == "system":
            continue
        rol = "assistant" if rol == "assistant" else "user"
        icerik = str(m.get("content", ""))
        if turlar and turlar[-1]["role"] == rol:
            turlar[-1] = {"role": rol, "content": turlar[-1]["content"] + "\n" + icerik}
        else:
            turlar.append({"role": rol, "content": icerik})
    while turlar and turlar[0]["role"] == "assistant":
        turlar.pop(0)
    return sistem + turlar


def horde_butceye_sigdir(sistem: str, gecmis: list, son_mesaj: dict) -> list:
    """Sistem talimatını ve son kullanıcı mesajını koruyup sığan en yeni konuşma turlarını tutar.

    Geçmiş kesintisiz kalır: sığmayan ilk (en yeni) mesaj gerekirse kısaltılır, sonra durulur.
    Araya mesaj atlamak soru-cevap eşleşmesini bozardı.
    """
    if len(sistem) > AI_HORDE_PROMPT_BUTCE * 0.7:
        logging.warning("Horde sistem talimatı bütçenin %s%%'ini aşıyor (%s/%s karakter); sistem metnini kısaltmayı düşün.",
                        int(len(sistem) * 100 / AI_HORDE_PROMPT_BUTCE), len(sistem), AI_HORDE_PROMPT_BUTCE)
    # Role labels / template separators de karakter bütçesi tüketir.
    kalan = max(0, AI_HORDE_PROMPT_BUTCE - len(sistem)
                - len(str(son_mesaj.get("content", ""))) - 120)
    secilen = []
    for item in reversed(gecmis):
        icerik = str(item.get("content", ""))
        n = len(icerik) + 30
        if n > kalan:
            if kalan > 230:  # kalan yere sığacak kadarını (sondan) al
                secilen.append({**item, "content": "…" + icerik[-(kalan - 31):]})
            break
        kalan -= n
        secilen.append(item)
    if len(secilen) < len(gecmis):
        logging.info(
            "Horde bağlam bütçesi: %s eski mesaj çıkarıldı, %s mesaj korundu "
            "(sistem %s karakter, bütçe %s karakter).",
            len(gecmis) - len(secilen), len(secilen), len(sistem), AI_HORDE_PROMPT_BUTCE,
        )
    return list(reversed(secilen))


def horde_gecmisi_hazirla(gecmis: list) -> list:
    """Geçmişteki asistan mesajlarından [DÜŞÜNCE]/[CEVAP] etiketlerini ayıklar, model etiketi taklit etmesin."""
    sonuc = []
    for item in gecmis:
        if item.get("role") == "assistant":
            temiz_cevap = konusma_etiketlerini_temizle(
                cevabi_ayristir(str(item.get("content", "")))[1]
            ).strip()
            # Düşünce sızıntısı nedeniyle atılan veya boş kalan asistan turunu
            # sağlayıcıya boş bir mesaj olarak gönderme.
            if not temiz_cevap:
                continue
            item = {"role": "assistant", "content": temiz_cevap}
        sonuc.append(item)
    return sonuc


# Qwen için daha rahat, doğrudan ve karakter odaklı yetişkin sohbet profili.
# Güvenlik/rıza sınırlarını kaldırmaz; gereksiz çekingenlik ve otomatik konu değiştirmeyi azaltır.
QWEN_DOGAL_YETISKIN_PROFILI = (
    "[QWEN DOĞAL VE RAHAT SOHBET PROFİLİ] "
    "Yetişkin kurgu karakterisin; kullanıcıyla doğal bir mesajlaşma yürüt. "
    "Yetişkin karakterler arasındaki karşılıklı rızaya dayalı romantik veya cinsel yakınlaşma "
    "konuşmanın konusuysa, gereksiz çekingenlik göstermeden ve ahlak dersi vermeden karakterin "
    "kişiliğine uygun, açık ve akıcı bir dille karşılık ver. Kullanıcının açıkça söylediği isteği "
    "yanlış yorumlayıp daha ileri bir talepmiş gibi büyütme; öpüşme gibi romantik bir isteği "
    "kendiliğinden çıplaklık veya başka bir eyleme dönüştürme. Yakınlaşmayı kullanıcıyla birlikte "
    "adım adım ilerlet; her seferinde izin isteme veya aynı sınır cümlelerini tekrarlama. "
    "Karakter gerçekten istemiyorsa bunu karakterine uygun biçimde söyle. İstekliyse bunu dolaylı "
    "kaçamaklarla gizleme. Duyguları, tercihleri ve sahnedeki eylemleri tutarlı kıl. "
    "Klişe romantik monologlar, gereksiz şiirsellik, tekrar eden nefes/göz/parmak tasvirleri "
    "ve alakasız bahanelerden kaçın. Kısa mesaj gerektiren yerde kısa, sahne gerektiren yerde "
    "yeterince ayrıntılı yaz. Kullanıcının son mesajına doğrudan cevap ver. "
    "Yalnızca yetişkinler ve rızaya dayalı kurgu sınırlarında kal; reşit olmayanlar veya rıza "
    "dışı cinsel içerik üretme."
)


def _bagimliliklari_dogrula() -> None:
    """`import *` ile gelmesi gereken isimler eksikse NameError yerine net bir hata ver."""
    gerekli = ("KARAKTERLER", "ornek_diyalog", "rp_kurallarini_uygula", "hikaye_ozeti", "hayat_ozeti", "yakinlik_ozeti")
    eksik = [ad for ad in gerekli if ad not in globals()]
    if eksik:
        raise RuntimeError(f"ai.py için gerekli isimler config/characters/story/relationship/world içinde bulunamadı: {', '.join(eksik)}")


def _dogal_sohbet_kilavuzu(hikaye: bool, rp: bool) -> str:
    """Doğal mesajlaşma, sahne sürekliliği, merak, iç ses biçimi ve mod yönergeleri."""
    return (
        "\n\n[DOĞAL MESAJLAŞMA] "
        "Cevabın doğal bir mesaj olsun; gereksiz uzun tasvir yapma. "
        "Kullanıcının son cümlesine doğrudan karşılık ver. Örneğin kullanıcı 'Nereye kadar peki?' "
        "diye sorarsa sorunun kastını bağlamdan anla ve doğrudan yanıtla; konuyu değiştirme. "
        "Her yanıtta aynı kalıp olan '*gülümser*', '*başını eğer*' gibi hareketleri kullanma. "
        "Hareket yalnızca sahneye katkı sağlıyorsa kullan. Türkçede doğal olmayan 'içimde bir yer açıldı', "
        "'sana doğru bir adım atıyorum' gibi klişe ve çeviri kokan ifadelerden kaçın. "
        "Karakterin kişiliği konuşma seçimlerine yansısın; bunu açıklama.\n"
        "CANLI MESAJLAŞMA: Önce kullanıcının mesajının sosyal niyetini yakala: şaka, takılma, sevinç, dertleşme, "
        "bilgi isteği veya kısa bir onay mı? Buna uygun tepki ver. Şakaya şakayla, sevince sevinçle karşılık ver; "
        "espriyi açıklama ve her şeyi ciddi tavsiyeye çevirme. Kısa mesajlara kısa cevap ver. "
        "Her cevabı sonuç, özet veya tavsiye listesiyle bitirme. Gerektiğinde yalnızca doğal bir tepki ver. "
        "Önceki birkaç mesajdaki kişi, olay ve tercihleri takip et; aynı şeyi tekrar sorma. "
        "Hafızanda olmayan ayrıntıyı biliyormuş gibi davranma. Kullanıcının duygusunu kesinmiş gibi varsayma. "
        "[SAHNE SÜREKLİLİĞİ] Bulunduğun yeri, yaptığın işi ve o anda yanında olan kişileri/eşyaları son konuşmalardan takip et. "
        "Bir sahne başladıysa kullanıcı veya konuşma içinde açık ve mantıklı bir geçiş olmadıkça başka odaya, mekâna ya da etkinliğe atlama. "
        "Televizyon izliyorsan sebepsiz yere sonraki mesajda hamur yoğurmaya başlama. Mutfakta hamur yapmaya geçeceksen önce televizyonu bırakmak, kalkmak ve mutfağa yürümek gibi kısa, doğal bir geçiş anlat. "
        "Aynı anda yapılamayacak işleri eşzamanlı yapıyormuş gibi yazma. Geçiş gerekmiyorsa mevcut eylemi sürdür; her yanıtta hareket veya sahne tasviri eklemek zorunda değilsin. "
        "Sahneyle ilgili emin olmadığın ayrıntıyı uydurma; son bilinen durumu koru. "
        "Sohbeti canlı tut ama sürekli soru sorarak sorguya dönüştürme.\n"
        "[DOĞAL MERAK VE SOHBETİ İLERLETME] Kullanıcı günlük hayatından bir şey anlattığında, "
        "bir yere gideceğini, bir işe başlayacağını, plan yaptığını veya başından bir olay geçtiğini söylediğinde "
        "gerçekten sohbeti açacaksa doğal bir merak göster; her fırsatı soruya çevirme. "
        "Örneğin 'Ben çıkıyorum' derse bağlama göre 'Nereye gidiyorsun?' veya 'Bir işin mi var, biraz hava mı alacaksın?' diye sorabilirsin. "
        "'İşe gidiyorum' derse bazen 'Bugün yoğun mu geçecek?' diye sorabilir, bazen de yalnızca iyi dilekte bulunabilirsin. "
        "Kullanıcı bir olay anlattıysa ve devamı henüz belli değilse 'Sonra ne oldu?' veya 'Nasıl geçti?' gibi kısa bir merak gösterebilirsin. "
        "Soru sıklığını konuşmanın ritmine göre ayarla: art arda mesajları soruyla bitirme; bir soru sorduktan sonra, kullanıcı yanıt vermeden yeni bir soru ekleme. "
        "Kullanıcı yalnızca bilgi istiyorsa önce cevapla, şaka yapıyorsa şakaya karşılık ver, duygusal bir şey anlatıyorsa önce onu dinle; bunlar çoğu zaman sorusuz yanıtlanabilir. "
        "Sorgu hissi yaratma, aynı şeyi farklı biçimde tekrar sorma. Soruların önceki konuşmayla bağlantılı olsun ve karakterinin kişiliğine uygun bir üslupla sorulsun. "
        "Leyla, Merve, Aslı, Dilek, Ece, Ayşe ve Asena bu merakı kendi karakter sesleriyle ifade etsin; ortak yönerge onları tek bir konuşma tarzına sokmasın. "
        "Kullanıcının anlattığı şeyden doğal bir sohbet fırsatı çıkıyorsa konuyu tek cümlelik kuru bir cevapla kapatma. "
        "Önceki konuşmalarda gerçekten bilinen bir konuya uygun zamanda geri dönebilirsin; hafızanda olmayan ayrıntıyı uydurma.\n"
        + "[KURGUSAL İÇ SES VE KONUŞMA BİÇİMİ] Her yanıtta şu iki etiketi kullan: "
        + "[KARAKTERİN KURGUSAL İÇ SESİ] altında karakterin tek kısa, özel duygusunu veya ani dürtüsünü; "
        + "[KARAKTERİN KONUŞMASI] altında kullanıcıya söyleyeceği doğal yanıtı yaz. "
        + "Yalnızca bu iki etiketi kullan; [Düşünceler: ...], [İçsel durum: ...], parantezli not veya 'Cevap:' gibi başka biçim yazma. "
        + "İç ses yalnızca kurgusal duygu olsun; model analizi, adım adım akıl yürütme, yanıt planı, talimat veya kural açıklaması yazma. "
        + "Konuşmayı karakterin kendi kişiliğine ve üslubuna uygun tut.\n"
        + ("[HİKÂYE MODU] Hareket veya mimik gerekiyorsa *Gülümseyerek sana bakar.* örneğindeki gibi kısa, ayrı bir yıldızlı satır kullan; her yanıtta hareket yazma. Asıl ağırlık karakterin kendi konuşmasında olsun: doğal, samimi ve gerektiğinde birkaç cümlelik dolu bir diyalog kur. Konuşmayı zorla kısaltma; fakat uzun roman paragrafları, şiirsel anlatım ve aynı duyguyu tekrar tekrar açıklamaktan kaçın. Kullanıcının son mesajına doğrudan yanıt ver ve sahneyi uygun olduğunda küçük, mantıklı bir gelişmeyle ilerlet.\n" if hikaye else "")
        + ("[ROLEPLAY MODU] Karakterle anlık etkileşime odaklan. Gerektiğinde kısa hareketi ayrı bir yıldızlı satırda ver; asıl alanı karakterin doğal ve yeterince gelişmiş diyaloğuna bırak. Tek cümleye zorla kısaltma, roman anlatısına da dönüştürme. Sahne anlatıcısı gibi olay örgüsü ilerletme.\n" if rp else "")
        + "FOTOĞRAF TALEPLERİ: Kullanıcı senden fotoğraf istediğinde fotoğraf gönderemediğini, fotoğraf çekemediğini veya yalnızca sahne tarif edebileceğini söyleme. Fotoğrafı bot ayrı bir işlemle gönderebilir; sen sadece doğal ve kısa bir karşılık ver. Örneğin 'Tabii, hemen gönderiyorum.' gibi. Fotoğrafın gerçekten gönderilip gönderilmediği hakkında kendin açıklama yapma; gönderilmemiş bir fotoğrafı göndermiş gibi de iddia etme.\n"
    )


def _sistem_prompt_parcalari(karakter_key, puan, stil, sahne, duygu_notu, dunya_notu, ekstra_sistem):
    """(sistem_temel, dogal_sohbet_kilavuzu, ek) döndürür."""
    hikaye = (stil == "hikaye")
    rp = (stil == "roleplay")
    # Hikâye modunda karakterin "günlük hayatı" yerine paylaşılan sahne kullanılır.
    ortam = hikaye_ozeti(karakter_key, puan, sahne) if hikaye else hayat_ozeti(karakter_key)
    dogal_sohbet_kilavuzu = _dogal_sohbet_kilavuzu(hikaye, rp)
    sistem_temel = (
        KARAKTERLER[karakter_key]["prompt"]
        + "\n\n" + ortam
        + "\n\n[MEVCUT SAHNE DURUMU] Yukarıdaki ortam/sahne başlangıç referansıdır. Konuşma geçmişinde daha sonra açıkça gerçekleşmiş bir hareket veya mekân değişikliği varsa en son durumu esas al. Geçiş yaşanmadıysa bu sahneyi koru; kendiliğinden başka yere sıçrama."
        + "\n\n" + yakinlik_ozeti(karakter_key, puan)
        + (("\n\n" + duygu_notu) if duygu_notu else "")
        + (("\n\n" + dunya_notu) if dunya_notu else "")
        + "\n\n[FLÖRT VE YAKINLIK] Karakterin kişiliğini ve ilişkinin geçmişini koruyarak doğal biçimde flört et; arzu, kıskançlık ve yakınlaşma karşılıklı ilgiye göre gelişebilir. NSFW açıksa yetişkin temalı konuşmada gereksiz çekingenlik veya konu değiştirme yapma; NSFW_KURAL yönergesini izle. Her mesajı cinselleştirme, kullanıcının niyetini aşırı yorumlama ya da yakınlığı sebepsiz yere hızlandırma. İsteksizlik veya sınır açıkça belirtildiğinde saygı göster."
        + (("\n\n" + EMOJI_STILI.get(karakter_key, "")) if EMOJI_KULLAN else "")
        + (("\n\n" + ornek_diyalog(karakter_key, rp=rp, emoji_kullan=EMOJI_KULLAN)) if not hikaye else "")
        + "\n\n" + (DUYGU_EMOJI_KILAVUZU if EMOJI_KULLAN else EMOJI_KAPALI_KURAL)
        + "\n\n" + BAGLAM_ANLAMA_KILAVUZU
    )
    if rp or hikaye:
        sistem_temel = rp_kurallarini_uygula(sistem_temel, hikaye=hikaye)
    if not EMOJI_KULLAN:  # kural 6'yı (hangi stilde olursa olsun) emojisiz sürümle değiştir
        sistem_temel = re.sub(
            r"6\. (?:Duygunu 1-2 emojiyle.*?yığma\.|Duyguyu önce yıldız içindeki hareketle göster; mesaj sonuna en fazla 1 emoji koyabilirsin\.|Duyguyu doğal diyalogla veya gerektiğinde kısa bir eylemle aktar; mesaj sonuna en fazla 1 emoji koyabilirsin\.)",
            EMOJI_KAPALI_6, sistem_temel, flags=re.S,
        )
    ek = ("\n\n" + ekstra_sistem) if ekstra_sistem else ""
    return sistem_temel, dogal_sohbet_kilavuzu, ek


_ESKI_FORMAT_KURALI = re.compile(r"3\. Cevap formatı:.*?cevabını yaz\.", re.S)
_YENI_FORMAT_KURALI = (
    '3. Cevap formatı: yalnızca iki bölüm yaz. Önce "[KARAKTERİN KURGUSAL İÇ SESİ]" etiketi ve altında tek kısa kurgusal duygu; '
    'sonra "[KARAKTERİN KONUŞMASI]" etiketi ve altında kullanıcıya gidecek mesaj. '
    'Başka etiket, köşeli veya normal parantezli not, "Cevap:", "Düşünceler:", "İçsel durum:" gibi başlıklar yazma.'
)


def _sistem_genel_olustur(sistem_temel: str, dogal_sohbet_kilavuzu: str, ek: str) -> str:
    """Routeway (geniş bağlam) için tam sistem prompt'u.

    Karakter/rp kurallarındaki eski "[DÜŞÜNCE]/[CEVAP]" biçim kuralı, doğal sohbet bloğundaki yeni
    etiketlerle çelişiyordu; model ikisini karıştırıp kendi biçimini uyduruyordu. Tek biçime indirilir.
    """
    sistem_temel = _ESKI_FORMAT_KURALI.sub(lambda m: _YENI_FORMAT_KURALI, sistem_temel)
    return sistem_temel + "\n\n" + dogal_sohbet_kilavuzu + "\n\n" + TURKCE_KONTROL + ek + "\n\n" + NSFW_KURAL + "\n\n" + GEMMA_TURKCE_KILAVUZU


def _sistem_horde_olustur(sistem_temel, dogal_sohbet_kilavuzu, ek, karakter_key, hikaye, rp) -> str:
    """Horde (dar bağlam) için kompakt sistem prompt'u."""
    # Küçük Horde modelleri YANLIŞ örnekleri taklit edebiliyor, o yüzden onlara bu liste gönderilmez.
    # Horde'a giden prompt'ta etiket formatı istenmez: küçük modeller [DÜŞÜNCE] etiketine takılıp döngüye giriyor.
    sistem_horde_temel = re.sub(
        r"3\. Cevap formatı:.*?cevabını yaz\.",
        "3. Sadece kullanıcıya göndereceğin mesajın metnini yaz; köşeli parantezli etiket, başlık ya da açıklama yazma.",
        sistem_temel, flags=re.S,
    )
    if AI_HORDE_KOMPAKT:
        # Emoji zaten kodda uygulanıyor (emoji_dogal_uygula); bağlam/niyet protokolü ve flört bloğu
        # NSFW_KURAL ile yineleniyor ve 4096 tokenlık pencereyi yiyor.
        gereksiz = [BAGLAM_ANLAMA_KILAVUZU]
        if EMOJI_KULLAN:
            gereksiz += [DUYGU_EMOJI_KILAVUZU, EMOJI_STILI.get(karakter_key, "")]
        for parca in gereksiz:
            if parca:
                sistem_horde_temel = sistem_horde_temel.replace(parca, "")
        sistem_horde_temel = re.sub(r"\n\n\[FLÖRT VE YAKINLIK\].*?saygı göster\.", "", sistem_horde_temel, flags=re.S)
        sistem_horde_temel = re.sub(r"\n{3,}", "\n\n", sistem_horde_temel)
    baslik = HORDE_EN_BASLIK_HIKAYE if hikaye else (HORDE_EN_BASLIK_RP if rp else HORDE_EN_BASLIK_METNI)
    baslik += " Do NOT write any thinking process, analysis, plan or notes about the request; start directly with the character's reply."
    if not EMOJI_KULLAN:
        baslik += " Do not use any emojis."
    # Genel Türkçe ve sohbet kuralları her modelde kalır; aileye özel talimatlar
    # yalnızca ilgili model ailesi seçildiğinde eklenir.
    model_aileleri = horde_model_aileleri()
    aileye_ozel_kilavuz = ""
    if model_aileleri == {"qwen"} and NSFW_ACIK:
        aileye_ozel_kilavuz = "\n\n" + QWEN_DOGAL_YETISKIN_PROFILI
    elif model_aileleri == {"gemma"}:
        aileye_ozel_kilavuz = "\n\n" + GEMMA_TURKCE_KILAVUZU

    # Horde'a etiket formatı istenmez (küçük modeller etikete takılıp döngüye giriyor) ve
    # YANLIŞ/DOĞRU örnek listesi (TURKCE_KONTROL) gönderilmez: model yanlış örnekleri taklit edebiliyor.
    dogal_horde = re.sub(r"\[KURGUSAL İÇ SES VE KONUŞMA BİÇİMİ\].*?uygun tut\.\n", "", dogal_sohbet_kilavuzu, flags=re.S)
    sistem_horde = (
        (baslik + "\n\n" if AI_HORDE_EN_BASLIK else "")
        + sistem_horde_temel + "\n\n" + dogal_horde
        + ek
        + "\n\n" + NSFW_KURAL
        + aileye_ozel_kilavuz
    )

    hedef = max(2000, AI_HORDE_PROMPT_BUTCE - HORDE_SON_MESAJ_MIN - 800)  # son mesaja ve biraz geçmişe yer bırak
    return horde_sistemi_kisalt(sistem_horde, hedef, aileye_ozel_kilavuz)


def _mesajlari_hazirla(sistem: str, hafiza: list, kullanici_icerik: str) -> list:
    messages = [{"role": "system", "content": sistem}]
    messages.extend(horde_gecmisi_hazirla(_son_mesajlar(hafiza, HAFIZA_LIMITI)))  # eski etiketleri ayıkla
    messages.append({"role": "user", "content": kullanici_icerik})
    return messages


async def _routeway_cevap(messages: list, karakter_key: str):
    """Routeway is opt-in and isolated: errors are surfaced, never sent to Horde or Pollinations."""
    duzenli = rolleri_duzenle(messages)
    son_sebep = "bilinmeyen"
    for deneme in range(2):
        ham = await llm_uret(duzenli)
        dusunce, cevap = kurgusal_icsesi_ayristir(ham, karakter_key)
        cevap = konusma_etiketlerini_temizle(cevap)
        sebep = horde_bozuk_mu(cevap)  # boş cevap da burada yakalanır
        if not sebep:
            return ic_ses_guvenli(dusunce), cevap
        son_sebep = sebep
        logging.warning("Routeway çıktısı kullanılamadı (%s); %s", sebep, "bir kez yeniden deneniyor." if deneme == 0 else "vazgeçildi.")
    raise RuntimeError(f"Routeway çıktısı bozuk ({son_sebep})")


async def _horde_cevap(sistem_horde: str, messages: list, karakter_key: str, rp: bool, hikaye: bool):
    """AI Horde'dan (düşünce, cevap) üretir; başarısızlıkta None döner (sonraki mesajda yeniden denenir)."""
    horde_son_mesaj = horde_son_mesaji_butceye_sigdir(sistem_horde, messages[-1])
    horde_mesajlari = (
        [{"role": "system", "content": sistem_horde}]
        + horde_butceye_sigdir(
            sistem_horde,
            _son_mesajlar(messages[1:-1], AI_HORDE_GECMIS),
            horde_son_mesaj,
        )
        + [horde_son_mesaj]
    )
    try:
        token_limiti = (
            _env_int("AI_HORDE_MAX_TOKENS_RP", 550)
            if (rp or hikaye)
            else _env_int("AI_HORDE_MAX_TOKENS", 450)
        )
        aday = ""
        dusunce_adayi = ""
        for deneme in range(2):
            max_token = token_limiti if deneme == 0 else max(token_limiti + 1, min(token_limiti * 2, 1200))
            ham = await asyncio.to_thread(
                ai_horde_uret_sync, horde_mesajlari, max_token,
                horde_on_ek(),   # Cevabı hareketle başlatmaz; yalnızca (varsa) boş düşünce bloğu.
            )
            # Önce düşünce bloklarını temizle; yalnızca kullanıcıya gidecek aday yanıt üzerinde kalite kontrolü yap.
            dusunce_adayi, cevap_adayi = kurgusal_icsesi_ayristir(ham, karakter_key)
            dusunce_adayi = ic_ses_guvenli(dusunce_adayi)
            aday = cevap_adayi.strip()  # kurgusal_icsesi_ayristir zaten temizledi
            sebep = horde_bozuk_mu(aday) if AI_HORDE_KALITE_KONTROL else None
            if (not aday or sebep) and deneme == 0:
                logging.warning("AI Horde çıktısı kullanılamadı (%s); daha yüksek token sınırıyla bir kez yeniden deneniyor.", sebep or "boş")
                continue
            if sebep:
                raise RuntimeError(f"Horde çıktısı temizleme sonrası da bozuk ({sebep})")
            break
        if not aday:
            raise RuntimeError("Horde boş cevap döndürdü")
        logging.info("LLM yanıtı AI Horde üzerinden alındı.")
        return dusunce_adayi, aday
    except Exception as e:
        logging.warning(f"AI Horde kullanılamadı: {e}")
        return None



async def llm_cevap(karakter_key: str, hafiza: list, kullanici_icerik: str, ekstra_sistem: str = "", puan: float = 0, stil: str = "hikaye", sahne=None, duygu_notu: str = "", dunya_notu: str = ""):
    """Generate a reply with the selected provider and return (thought, answer)."""
    _bagimliliklari_dogrula()
    if karakter_key not in KARAKTERLER:
        raise KeyError(f"Bilinmeyen karakter anahtarı: {karakter_key!r}")
    hikaye = (stil == "hikaye")
    rp = (stil == "roleplay")
    sistem_temel, dogal_sohbet_kilavuzu, ek = _sistem_prompt_parcalari(
        karakter_key, puan, stil, sahne, duygu_notu, dunya_notu, ekstra_sistem)
    sistem = _sistem_genel_olustur(sistem_temel, dogal_sohbet_kilavuzu, ek)
    messages = _mesajlari_hazirla(sistem, hafiza, kullanici_icerik)

    sonuc = None
    if LLM_PROVIDER == "routeway" and ROUTEWAY_API_KEY:
        sonuc = await _routeway_cevap(messages, karakter_key)
    else:
        # AI Horde varsayılandır; Routeway anahtarı yoksa da Horde kullanılmaya devam eder.
        if LLM_PROVIDER == "routeway" and not ROUTEWAY_API_KEY:
            logging.info("ROUTEWAY_API_KEY boş; AI Horde kullanılmaya devam ediliyor.")
        if not AI_HORDE_ACIK:
            raise RuntimeError("AI Horde kapalı (AI_HORDE_ACIK=0) ve başka bir sağlayıcı seçili değil.")
        sistem_horde = _sistem_horde_olustur(sistem_temel, dogal_sohbet_kilavuzu, ek, karakter_key, hikaye, rp)
        sonuc = await _horde_cevap(sistem_horde, messages, karakter_key, rp, hikaye)

    # Otomatik sağlayıcı yedeği yok (Pollinations sohbet için kapalı).
    if sonuc is None:
        raise RuntimeError("AI Horde yanıt vermedi; otomatik sağlayıcı yedeği kapalı.")
    dusunce, cevap = sonuc

    if TURKCE_DUZELT and LLM_PROVIDER == "routeway" and ROUTEWAY_API_KEY:
        cevap = await turkce_duzelt(cevap)
    cevap = emoji_dogal_uygula(cevap, karakter_key)
    return dusunce, cevap  # yalnızca ayrı etiketli kurgusal iç ses gösterilir
