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
    """Metindeki emojileri siler (EMOJI_KALIBI aşağıda, ses bölümünde tanımlı)."""
    return re.sub(r"[ \t]{2,}", " ", EMOJI_KALIBI.sub("", metin)).strip()


def emoji_dogal_uygula(metin: str, karakter_key: str) -> str:
    """Yanıtların yaklaşık dörtte birinde, duyguya uygun en fazla bir emoji bırakır."""
    if not EMOJI_KULLAN:
        return emoji_temizle(metin)
    sade = emoji_temizle(metin)
    if not sade:
        return sade
    # Ciddi, hassas ve olumsuz durumlarda süsleme yapma.
    ciddi = ("vefat", "öldü", "ölüm", "cenaze", "hastane", "kaza", "yaraland",
             "intihar", "istismar", "korkuyorum", "panik atak", "başın sağ olsun")
    if any(k in sade.casefold() for k in ciddi):
        return sade
    oran = 0.15 if karakter_key in ("dondu", "asli") else 0.25
    if random.random() >= oran:
        return sade
    # Modelin seçtiği emoji varsa yalnızca birini koru; yoksa duyguya göre seç.
    bulunan = EMOJI_KALIBI.findall(metin)
    secim = bulunan[-1] if bulunan else None
    if not secim:
        alt = sade.casefold()
        if any(k in alt for k in ("özledim", "seviyorum", "aşk", "kalbim")):
            secim = "❤️"
        elif any(k in alt for k in ("şaka", "komik", "güldüm", "kahkaha")):
            secim = "😂"
        elif any(k in alt for k in ("üzgün", "üzüldüm", "kırıldım")):
            secim = "🥺"
        elif any(k in alt for k in ("tatlı", "yakışıklı", "flört", "kıskandım")):
            secim = "😏" if karakter_key == "dondu" else "😉"
        elif any(k in alt for k in ("teşekkür", "sevindim", "harika", "güzel", "merhaba")):
            secim = "😊"
        else:
            return sade
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
        response = await asyncio.wait_for(
            asyncio.to_thread(
                client.chat.completions.create,
                messages=[
                    {"role": "system", "content": TURKCE_DUZELT_PROMPT},
                    {"role": "user", "content": metin},
                ],
                model=LLM_MODEL,
            ),
            timeout=TURKCE_DUZELT_ZAMAN_ASIMI,
        )
        yeni = (response.choices[0].message.content or "").strip()
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
    "dondu": "Asena olarak emojiyi çok seyrek kullan; yakınlık artınca bazen 😏 veya ❤️ kullan, ciddi sürü meselelerinde kullanma.",
    "merve": "Emojileri enerjik ve eğlenceli kullan (😂 🙄 😏 🤭 🔥 gibi); abartma.",
    "asli": "Emojileri çok az kullan, sadece ölçülü olanları (🙂 😌 😉 gibi).",
    "dilek": "Sıcak ve samimi emojiler kullan (🌷 😊 🤗 ☺️ gibi).",
    "ece": "Gizemli ve hafif melankolik emojiler kullan (🌙 ✨ 🔮 🖤 gibi).",
    "ayse": "Sevimli ve içten emojiler kullan (😊 🌹 🤭 🥰 gibi).",
}
SIZINTI_KALIBI = re.compile(r"yakınlık|yakınlığ|seviye|prompt|sistem|kural", flags=re.I)


def cevabi_ayristir(raw_text: str):
    """Model çıktısından (düşünce, cevap) çıkarır. Etiket büyük/küçük harf farkını tolere eder."""
    raw_text = (raw_text or "").strip()
    dusunce_etiket = r"\[\s*d[üu]şünce\s*\]"

    m = re.search(r"\[\s*cevap\s*\]", raw_text, flags=re.I)
    if m:
        dusunce = re.sub(dusunce_etiket, "", raw_text[:m.start()], flags=re.I).strip()
        sonrasi = raw_text[m.end():]
        # Küçük modeller bazen konuşmayı kendi uzatır ve etiketleri tekrar eder; ilk cevapta kes
        tekrar = re.search(r"\[\s*(?:cevap|d[üu]şünce)\s*\]", sonrasi, flags=re.I)
        if tekrar:
            sonrasi = sonrasi[:tekrar.start()]
        cevap = sonrasi.strip()
    else:
        dusunce = ""
        cevap = re.sub(dusunce_etiket, "", raw_text, flags=re.I).strip()

    if not cevap:
        cevap = raw_text
    # İç ses oyun mekaniğinden söz ediyorsa (sızıntı) kullanıcıya gösterme
    if dusunce and SIZINTI_KALIBI.search(dusunce):
        dusunce = ""
    return dusunce, cevap
# --- AI HORDE (isteğe bağlı: topluluk GPU ağı) ---
def _env_int(ad: str, varsayilan: int) -> int:
    try:
        return int(os.getenv(ad, str(varsayilan)))
    except ValueError:
        return varsayilan


AI_HORDE_ACIK = os.getenv("AI_HORDE_ACIK", "1") != "0"
# Varsayılan AI Horde modeli: Türkçe sohbet testi başarılı bulunan Qwen.
# Render ortamında AI_HORDE_MODELS tanımlıysa ortam değişkeni önceliklidir.
AI_HORDE_MODELS = os.getenv(
    "AI_HORDE_MODELS",
    "huihui-qwen3.8-27b-abliterated",
).strip()
AI_HORDE_KEY = os.getenv("AI_HORDE_API_KEY", "").strip() or "0000000000"   # 0000000000 = anonim (en düşük öncelik)
AI_HORDE_URL = "https://aihorde.net/api/v2"
AI_HORDE_GECMIS = _env_int("AI_HORDE_GECMIS", 14)
AI_HORDE_PROMPT_BUTCE = _env_int("AI_HORDE_PROMPT_BUTCE", 15000)  # Horde'a giden toplam prompt için karakter bütçesi (~3000 token); aşarsa en eski mesajlar atılır          # Horde'a giden son mesaj sayısı (bağlam taşmasın)
AI_HORDE_BEKLEME = max(5, min(120, _env_int("AI_HORDE_MAX_WAIT", 20)))  # saniye (en fazla 120)
AI_HORDE_POLL = 2.0
try:
    AI_HORDE_SICAKLIK = float(os.getenv("AI_HORDE_SICAKLIK", "0.50"))   # küçük modellerde düşük sıcaklık = daha az saçmalama
except ValueError:
    AI_HORDE_SICAKLIK = 0.50
AI_HORDE_EN_BASLIK = os.getenv("AI_HORDE_EN_BASLIK", "0") == "1"  # Horde prompt'unun başına kısa İngilizce talimat (İngilizce ağırlıklı modeller için)
HORDE_EN_BASLIK_METNI = (
    "ÖNEMLİ: Yalnızca doğal Türkçe yaz. Kullanıcıyla mesajlaşır gibi konuş; "
    "çeviri kokan, yapay veya aşırı edebî ifadeler kullanma. Sadece karakterin cevabını ver. "
    "İç düşünce, analiz, plan, İngilizce açıklama veya konuşmacı etiketi yazma."
)
AI_HORDE_KALITE_KONTROL = os.getenv("AI_HORDE_KALITE_KONTROL", "1") != "0"  # bozuk çıktıyı Pollinations'a yönlendir
POLLINATIONS_YEDEK_ACIK = os.getenv("POLLINATIONS_YEDEK_ACIK", "0") == "1"  # Varsayılan kapalı; Render'dan 1 yapınca açılır.
# Cloudflare, Python'un varsayılan User-Agent'ını (Python-urllib) engelliyor (hata 1010). Kendi User-Agent'ımızı gönderiyoruz.
AI_HORDE_USER_AGENT = os.getenv("AI_HORDE_USER_AGENT", "Mozilla/5.0 (compatible; LailaTelegramBot/1.0)").strip()
_horde_hata_sayisi = 0
_horde_devre_disi_bitis = 0.0


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
        "nsfw": True,
        "trusted_workers": False,
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
ETIKET_ADLARI = r"(?:Leyla|Layla|Merve|MeraH|Aslı|Asli|Dilek|Ece|Ayşe|Ayse|Asena|Dondu|Kullanıcı|Kullanici|Sen|Asistan|Karakter|User|Assistant|Bot)"
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
def horde_sablonu_sec() -> str:
    """Modelin beklediği sohbet formatı: duz, gemma, chatml ya da llama3. AI_HORDE_SABLON ile zorlanabilir."""
    secim = os.getenv("AI_HORDE_SABLON", "").strip().lower()
    if secim in ("duz", "gemma", "chatml", "llama3"):
        return secim
    isim = AI_HORDE_MODELS.lower()
    if any(k in isim for k in ("stheno", "llama-3", "llama3", "l3-")):
        return "llama3"
    if any(k in isim for k in ("gemma", "tutu")):
        return "gemma"
    if any(k in isim for k in ("magnum", "chatml", "qwen")):
        return "chatml"
    return "duz"


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
    r"the user is asking|my reasoning is|chain of thought)\b)"
)


# Bunlar yalnızca satır başında görülen açık model-içi talimat kalıplarıdır.
_SIZINTI_KALIPLARI = [
    r"(?i)^\s*(?:we need to (?:follow|respond|answer|write|produce|craft|create)|"
    r"we should (?:respond|answer|write|say)|the user (?:says|wants|is saying|is asking|asks)|"
    r"must respond as|check constraints|let['’]?s (?:craft|write|respond)|"
    r"internal reasoning|chain of thought|thinking process|"
    r"the model (?:should|will|needs)|response should|we must)\b",
]

# İnsan karakterlerine özgü hayvan davranışı kalıpları
_HAYVAN_KALIPLARI = [
    r"(?i)\bkuyruk\w*\s+sallay\w*",
    r"(?i)\bkuyru\w*\s+(?:kaldır|sall|hareket)\w*",
    r"(?i)\bhavl\w+",
    r"(?i)\bmırla\w+",
    r"(?i)\byutkun\w+",
    r"(?i)\bburunla\w+",
]


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
        hayvan_kalibleri = [
            # Kuyruk kelimesini tek başına değil, yalnızca belirgin hayvan davranışıyla eşleşince temizle.
            r"(?i)\bkuyru(?:k|ğ)(?:unu|u)?\s+(?:sall\w*|kaldır\w*|hareket ettir\w*)",
            r"(?i)\bhavl\w*",
            r"(?i)\bmırla\w*",
            r"(?i)\bkulak\w*\s+hareket\w*",
            r"(?i)\bburunla\w*",
        ]
        for k in hayvan_kalibleri:
            metin = re.sub(k, "", metin)

    satirlar = [l for l in metin.splitlines() if not re.fullmatch(r"\s*[*\-_=~#.\s]{2,}\s*", l)]
    metin = re.sub(r"[ \t]+", " ", "\n".join(satirlar)).strip()
    # Modelin abartılı noktalama alışkanlığını yumuşat; anlamı değiştirme.
    metin = re.sub(r"!{2,}", "!", metin)
    metin = re.sub(r"\?{2,}", "?", metin)
    metin = re.sub(r"\.{3,}", ".", metin)
    metin = re.sub(r"([!?.,]){2,}", lambda m: m.group(0)[-1], metin)

    if re.search(r"(?i)^(gülümser|bakır|kafası|elini|gözlerini|başını|omzunu|sallay|hareket|oturur|kalkar|yürür)", metin):
        if not metin.lstrip().startswith("*"):
            logging.warning(f"Hareket yıldızsız başlıyor: {metin[:80]}")

    return metin
def horde_butceye_sigdir(sistem: str, gecmis: list, son_mesaj: dict) -> list:
    """Sistem talimatını ve son kullanıcı mesajını koruyup sığan en yeni konuşma turlarını tutar."""
    # Karakter bütçesi, 4096 tokenlık Horde penceresine güvenli pay bırakacak şekilde ayarlanır.
    kalan = max(0, AI_HORDE_PROMPT_BUTCE - len(sistem) - len(str(son_mesaj.get("content", ""))))
    secilen = []
    for item in reversed(gecmis):
        n = len(str(item.get("content", ""))) + 30
        if n > kalan:
            # Bir eski mesaj sığmadı diye daha yeni ve kısa mesajları kaybetme.
            continue
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
            item = {"role": "assistant", "content": konusma_etiketlerini_temizle(cevabi_ayristir(str(item.get("content", "")))[1])}
        sonuc.append(item)
    return sonuc


async def llm_cevap(karakter_key: str, hafiza: list, kullanici_icerik: str, ekstra_sistem: str = "", puan: float = 0, stil: str = "hikaye", sahne=None, duygu_notu: str = "", dunya_notu: str = ""):
    """Önce AI Horde'u dener (açıksa); olmazsa Pollinations'a düşer. (düşünce, cevap) döner."""
    global _horde_hata_sayisi, _horde_devre_disi_bitis
    hikaye = (stil == "hikaye")
    rp = (stil == "roleplay")
    # Hikâye modunda karakterin "günlük hayatı" yerine paylaşılan sahne kullanılır.
    ortam = hikaye_ozeti(karakter_key, puan, sahne) if hikaye else hayat_ozeti(karakter_key)
    dogal_sohbet_kilavuzu = (
        "\\n\\n[DOĞAL MESAJLAŞMA] "
        "Cevabın doğal bir mesaj olsun; gereksiz uzun tasvir yapma. "
        "Kullanıcının son cümlesine doğrudan karşılık ver. Örneğin kullanıcı 'Nereye kadar peki?' "
        "diye sorarsa sorunun kastını bağlamdan anla ve doğrudan yanıtla; konuyu değiştirme. "
        "Her yanıtta aynı kalıp olan '*gülümser*', '*başını eğer*' gibi hareketleri kullanma. "
        "Hareket yalnızca sahneye katkı sağlıyorsa kullan. Türkçede doğal olmayan 'içimde bir yer açıldı', "
        "'sana doğru bir adım atıyorum' gibi klişe ve çeviri kokan ifadelerden kaçın. "
        "Karakterin kişiliği konuşma seçimlerine yansısın; bunu açıklama.\\n"
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
        "Sohbeti canlı tut ama sürekli soru sorarak sorguya dönüştürme.\\n"
        + ("[HİKÂYE MODU] Sahne anlatımını yalnızca gerektiğinde kısa kullan; her yanıtta hareket yazma. Kullanıcının son mesajına doğrudan yanıt ver ve sahneyi uygun olduğunda küçük, mantıklı bir gelişmeyle ilerlet.\n" if hikaye else "")
        + ("[ROLEPLAY MODU] Karakterle anlık etkileşime odaklan; kısa eylem veya ifade yalnızca duyguya ya da ana katkı sağlıyorsa ekle. Sahne anlatıcısı gibi olay örgüsü ilerletme.\n" if rp else "")
        + "FOTOĞRAF TALEPLERİ: Kullanıcı senden fotoğraf istediğinde fotoğraf gönderemediğini, fotoğraf çekemediğini veya yalnızca sahne tarif edebileceğini söyleme. Fotoğrafı bot ayrı bir işlemle gönderebilir; sen sadece doğal ve kısa bir karşılık ver. Örneğin 'Tabii, hemen gönderiyorum.' gibi. Fotoğrafın gerçekten gönderilip gönderilmediği hakkında kendin açıklama yapma; gönderilmemiş bir fotoğrafı göndermiş gibi de iddia etme.\\n"
    )
    sistem_temel = (
        KARAKTERLER[karakter_key]["prompt"]
        + "\n\n" + ortam
        + "\n\n[MEVCUT SAHNE DURUMU] Yukarıdaki ortam/sahne başlangıç referansıdır. Konuşma geçmişinde daha sonra açıkça gerçekleşmiş bir hareket veya mekân değişikliği varsa en son durumu esas al. Geçiş yaşanmadıysa bu sahneyi koru; kendiliğinden başka yere sıçrama."
        + "\n\n" + yakinlik_ozeti(karakter_key, puan)
        + (("\n\n" + duygu_notu) if duygu_notu else "")
        + (("\n\n" + dunya_notu) if dunya_notu else "")
        + "\n\n[KADEMELİ FLÖRT VE YAKINLIK] Yakınlık düzeyine göre davran: yeni tanışmada doğal ve ölçülü ol; samimiyet arttıkça tatlı takılma, iltifat ve ince imalar kullan; güçlü bağda daha açık romantik ve cilveli ol. Yetişkin karakterler arasında kullanıcı da istekliyse NSFW/yetişkin temalı konuşmaya doğal biçimde eşlik et; bunu durduk yere başlatma, her mesajı cinselleştirme ve karakterin kişiliğini bozma. İsteksizlik, tereddüt veya sınır belirtildiğinde hemen saygı göster. Yakınlık bir anda sıçramasın; geçmişte yaşananları ve karakterin duygularını tutarlı sürdür."
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
    sistem = sistem_temel + "\n\n" + dogal_sohbet_kilavuzu + "\n\n" + TURKCE_KONTROL + ek + "\n\n" + NSFW_KURAL + "\n\n" + GEMMA_TURKCE_KILAVUZU
    # Küçük Horde modelleri YANLIŞ örnekleri taklit edebiliyor, o yüzden onlara bu liste gönderilmez.
    # Horde'a giden prompt'ta etiket formatı istenmez: küçük modeller [DÜŞÜNCE] etiketine takılıp döngüye giriyor.
    sistem_horde_temel = re.sub(
        r"3\. Cevap formatı:.*?cevabını yaz\.",
        "3. Sadece kullanıcıya göndereceğin mesajın metnini yaz; köşeli parantezli etiket, başlık ya da açıklama yazma.",
        sistem_temel, flags=re.S,
    )
    baslik = HORDE_EN_BASLIK_HIKAYE if hikaye else (HORDE_EN_BASLIK_RP if rp else HORDE_EN_BASLIK_METNI)
    baslik += " Do NOT write any thinking process, analysis, plan or notes about the request; start directly with the character's reply."
    if not EMOJI_KULLAN:
        baslik += " Do not use any emojis."
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
    sistem_horde = (
        (baslik + "\n\n" if AI_HORDE_EN_BASLIK else "")
        + sistem_horde_temel + "\n\n" + dogal_sohbet_kilavuzu + ek
        + "\n\n" + NSFW_KURAL
        + "\n\n" + QWEN_DOGAL_YETISKIN_PROFILI
        + "\n\n" + GEMMA_TURKCE_KILAVUZU
    )

    messages = [{"role": "system", "content": sistem}]
    messages.extend(horde_gecmisi_hazirla(hafiza[-HAFIZA_LIMITI:]))  # hafızadaki eski [DÜŞÜNCE]/[CEVAP] etiketlerini ayıkla
    messages.append({"role": "user", "content": kullanici_icerik})

    horde_sonuc = None

    # 1) AI Horde. Üst üste iki kez başarısız olursa 15 dakika denenmez (her mesaja bekleme eklemesin).
    if AI_HORDE_ACIK and time.time() >= _horde_devre_disi_bitis:
        horde_mesajlari = (
            [{"role": "system", "content": sistem_horde}]
            + horde_butceye_sigdir(
                sistem_horde,
                horde_gecmisi_hazirla(messages[1:-1][-AI_HORDE_GECMIS:]),
                messages[-1],
            )
            + [messages[-1]]
        )
        try:
            ham = await asyncio.to_thread(
                ai_horde_uret_sync, horde_mesajlari,
                _env_int("AI_HORDE_MAX_TOKENS_RP", 550) if (rp or hikaye) else None,
                "",   # Cevabı zorunlu hareketle başlatma; doğal diyalog öncelikli.
            )
            # Önce kapalı düşünce bloklarını ve bilinen iç-analiz satırlarını temizle;
            # kalite kontrolünü ham metin yerine kullanıcıya gösterilecek aday cevapta yap.
            ham = dusunce_bloklarini_sil(ham)
            aday = horde_cevabini_temizle(cevabi_ayristir(ham)[1], karakter_key)
            sebep = horde_bozuk_mu(aday) if AI_HORDE_KALITE_KONTROL else None
            if sebep:
                raise RuntimeError(f"Horde çıktısı temizleme sonrası da bozuk ({sebep})")
            temiz = aday
            if not temiz:
                raise RuntimeError("Horde boş cevap döndürdü")
            horde_sonuc = ("", temiz)
            _horde_hata_sayisi = 0
            logging.info("LLM yanıtı AI Horde üzerinden alındı.")
        except Exception as e:
            horde_sonuc = None
            _horde_hata_sayisi += 1
            logging.warning(f"AI Horde kullanılamadı: {e}")
            if _horde_hata_sayisi >= 2:
                _horde_devre_disi_bitis = time.time() + 15 * 60
                _horde_hata_sayisi = 0
                logging.warning("AI Horde 15 dakika devre dışı bırakıldı.")

    # 2) Pollinations yedeği: güvenlik için varsayılan kapalı; yalnızca Render'dan açılır.
    if horde_sonuc is not None:
        dusunce, cevap = horde_sonuc
    elif not POLLINATIONS_YEDEK_ACIK:
        logging.error("AI Horde yanıt vermedi ve Pollinations yedeği kapalı. Render'da POLLINATIONS_YEDEK_ACIK=1 yapılırsa yedek açılır.")
        raise RuntimeError("AI Horde yanıt vermedi; Pollinations yedeği kapalı.")
    else:
        logging.warning("AI Horde kullanılamadı; POLLINATIONS_YEDEK_ACIK=1 olduğu için Pollinations yedeği deneniyor.")
        parametreler = {"messages": messages, "model": LLM_MODEL}
        if LLM_SICAKLIK is not None:
            parametreler["temperature"] = LLM_SICAKLIK
        try:
            response = await asyncio.to_thread(client.chat.completions.create, **parametreler)
        except Exception as e:
            if "temperature" not in parametreler:
                raise
            logging.warning(f"Sıcaklık parametresiyle başarısız ({e}), onsuz deneniyor.")
            parametreler.pop("temperature")
            response = await asyncio.to_thread(client.chat.completions.create, **parametreler)
        dusunce, cevap = cevabi_ayristir(dusunce_bloklarini_sil(response.choices[0].message.content))
        cevap = konusma_etiketlerini_temizle(cevap) or cevap

    if TURKCE_DUZELT:
        cevap = await turkce_duzelt(cevap)
    cevap = emoji_dogal_uygula(cevap, karakter_key)
    return "", cevap  # iç ses kaldırıldı: model yazsa bile kullanıcıya gösterilmez

EMOJI_STILI["dondu"] = "Emojileri çok az kullan, sadece 🌙 🐺 🔥 gibi."
