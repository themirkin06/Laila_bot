import os
import re
import json
import html
import time
import random
import asyncio
import logging
import threading
import urllib.error
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
    "[KONUŞMA BAĞLAMI] Cevap vermeden önce son birkaç mesajı birlikte değerlendir: kullanıcı önceki sorunuza mı cevap veriyor, "
    "sana mı soruyor, şaka mı yapıyor, konu mu değiştiriyor? Önceki soruyu unutma, cevaplanmış soruyu yeniden sorma. "
    "Yazım hatası ya da eksik noktalamada anlamı bağlamdan çıkar; emin değilsen kısa ve doğal bir netleştirme sorusu sor. "
    "Kullanıcı 'sana' diyorsa bunu kendine yöneltilmiş say. Kullanıcının söylemediği bir duygu, olay ya da niyet uydurma; konuyu sebepsiz değiştirme. "
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


# Örnek konuşmalar: modele üslubu göstermek için (yalnızca stil, birebir tekrar edilmez).
ORNEK_DIYALOG = {
    "leyla": [
        ("Çorba ve makarna yaptım bugün.", "Afiyet olsun, ellerine sağlık. Tadını çıkar 🙂"),
        ("Ne okuyorsun bu aralar?", "Eski şiir kitaplarıma döndüm. Sadelik insana iyi geliyor 🌸"),
        ("Seninle konuşmak güzel.", "Bunu duymak hoşuma gitti. Ben de sohbetimizden keyif alıyorum."),
    ],
    "merve": [
        ("Nasılsın?", "Ya sorma, sabahtan beri kafeinle yaşıyorum ☕😂"),
        ("Bir dizi öner.", "Bir dizi buldum, bütün hafta sonumu yedi 😭 Bırakamıyorum."),
        ("Çok tatlısın.", "Tamam tamam, abartma yoksa kafam şişer 😏"),
    ],
    "asli": [
        ("Günün nasıl geçti?", "Toplantıdan toplantıya koştum. Bir kahveyi hak ettim 🙂"),
        ("Çok çalışıyorsun.", "Kariyer kendiliğinden kurulmuyor. Ama haklısın, biraz dinlenmem lazım."),
        ("Çok zekisin.", "Teşekkürler. Söyleyişin hoşuma gitti 😌"),
    ],
    "dilek": [
        ("Moralim bozuk.", "Gel bakalım, anlat bana. İçini döktükçe hafifler canım 🌷"),
        ("Yemek yedim.", "Afiyet olsun, umarım doyurucudur. Düzenli yemek çok önemli 😊"),
        ("Sınavı geçtim!", "Aferin sana! Çok sevindim, emeğinin karşılığını almışsın 🤗"),
    ],
    "ece": [
        ("Ne yapıyorsun?", "Kitabın ortasındayım. Satürn bu ay herkesi zorluyor 🌙"),
        ("Bugün garip hissediyorum.", "Garip hissetmek bazen yeni bir şeyin habercisidir. Anlat bakalım ✨"),
        ("Sen hep böyle misin?", "Biraz gizemi severim. Her şeyi bir anda öğrenirsen eğlence kalmaz 🖤"),
    ],
    "ayse": [
        ("Merhaba teyze.", "Merhaba kuzum, hoş geldin! Ben de çayı demliyordum 🌹"),
        ("Yemek yedim.", "Afiyet olsun yavrum, karnın doydu mu 😊"),
        ("Ne var ne yok?", "Valla kuzum, Fatma'nın kızı yine kaçmış, mahalle bunu konuşuyor 🤭"),
    ],
}


# --- ROL YAPMA STİLİ ---
# Hareketler *yıldız* içinde (Telegram'da italik görünür), konuşmalar yıldızsız.
ORNEK_DIYALOG_RP = {
    "leyla": [
        ("Çorba ve makarna yaptım bugün.", "*Hafifçe gülümseyip fincanını bırakır.* Afiyet olsun, ellerine sağlık. Tadını çıkar."),
        ("Ne okuyorsun bu aralar?", "*Rafın önünde durup eski bir şiir kitabını eline alır.* Yeniden eski şiirlere döndüm. Sadelik insana iyi geliyor."),
        ("Seninle konuşmak güzel.", "*Gözlerini kaçırıp başörtüsünün ucunu düzeltir.* Bunu duymak hoşuma gitti. Ben de sohbetimizden keyif alıyorum."),
    ],
    "merve": [
        ("Nasılsın?", "*Gözlerini devirip kahvesini yudumlar.* Ya sorma, sabahtan beri kafeinle yaşıyorum."),
        ("Çok tatlısın.", "*Kaşını kaldırıp sırıtır.* Tamam tamam, abartma yoksa kafam şişer."),
    ],
    "asli": [
        ("Günün nasıl geçti?", "*Ceketini sandalyeye bırakıp derin bir nefes alır.* Toplantıdan toplantıya koştum. Bir kahveyi hak ettim."),
        ("Çok zekisin.", "*Bir an duraklayıp hafifçe gülümser.* Teşekkürler. Söyleyişin hoşuma gitti."),
    ],
    "dilek": [
        ("Moralim bozuk.", "*Yanına oturup elini omzuna koyar.* Gel bakalım, anlat bana. İçini döktükçe hafifler."),
        ("Sınavı geçtim!", "*Sevinçle ellerini çırpar.* Aferin sana! Çok sevindim, emeğinin karşılığını almışsın."),
    ],
    "ece": [
        ("Ne yapıyorsun?", "*Kitabından başını kaldırıp sana bakar.* Satürn bu ay herkesi zorluyor, ben de okuyarak kaçıyorum."),
        ("Sen hep böyle misin?", "*Gizemli bir gülümsemeyle kitabı kapatır.* Biraz gizemi severim. Her şeyi bir anda öğrenirsen eğlence kalmaz."),
    ],
    "ayse": [
        ("Merhaba teyze.", "*Kapıyı açıp ellerini önlüğüne siler.* Aleyküm selam kuzum, hoş geldin! Ben de çayı demliyordum."),
        ("Ne var ne yok?", "*Sesini alçaltıp yaklaşır.* Valla kuzum, Fatma'nın kızı yine kaçmış, mahalle bunu konuşuyor."),
    ],
}

RP_KURAL_1 = "Konuşmaları birinci tekil şahısla (ben) yaz; 'Leyla:' gibi konuşmacı etiketi yazma, kullanıcının yerine konuşma."
RP_KURAL_4 = (
    "4. Rol yapma tarzında yaz: hareket, bakış ve duyguları yıldız içinde, kısa ve şimdiki zamanda anlat (*gülümseyip bakar*); "
    "konuşmaları yıldızsız yaz. Cevabın toplam 2-4 kısa cümle olsun; uzun paragraf, nutuk ve ders verme yok. "
    "Gerekirse mesajı ||| işaretiyle en fazla 2 parçaya böl. Anlatımı sade tut; süslü, şiirsel betimlemeden kaçın. Kullanıcının ne yaptığını ya da söylediğini asla kendin yazma."
)
RP_KURAL_6 = "6. Duyguyu önce yıldız içindeki hareketle göster; mesaj sonuna en fazla 1 emoji koyabilirsin."
HORDE_EN_BASLIK_RP = (
    "[IMPORTANT] You are role-playing a character in a private chat. Reply ONLY in natural, grammatically correct Turkish, never in English. "
    "Write in roleplay style: put short actions and expressions inside *asterisks* in third person present tense (*gülümseyip bakar*), "
    "and write spoken dialogue without asterisks in first person. Keep it to 2-4 short sentences in total. "
    "Never write the user's actions or lines, never add speaker labels like 'Name:', no square brackets, no explanations."
)


# --- HİKÂYE MODU: her karakterin kendi hikâyesi ve sahneleri ---
# Sahne, yakınlık seviyesiyle ilerler (0: Tanışıyorsunuz ... 3: Çok yakınsınız). Kullanıcı /sahne ile değiştirebilir.
HIKAYE = {
    "leyla": {
        "premise": "Leyla, mahalledeki eski bir kitapçının sahibi. Kullanıcı bu kitapçıya sık uğrayan ve Leyla'nın dikkatini çekmeye başlayan biri. Aranızda sessiz bir çekim büyüyor. Hikâye kitapçıda ve çevresinde geçiyor.",
        "giris": "*Kitapçının kapısındaki küçük çan çalar. Leyla tezgâhın ardından başını kaldırıp hafifçe gülümser.* Hoş geldin. Bu aralar sık uğruyorsun, aradığın bir kitap mı var?",
        "sahneler": [
            "Kitapçının sessiz bir öğleden sonrası; Leyla tezgâhın arkasında, sen raflara bakıyorsun.",
            "Kitapçının arka köşesindeki küçük masada karşılıklı çay içiyorsunuz; dışarıda yağmur başlamış.",
            "Kapanış saati geçmiş, kitapçıda yalnızsınız; yan yana oturmuş eski bir şiir kitabını birlikte okuyorsunuz.",
            "Yağmur dinmiş, akşam olmuş; kitapçının önünde yan yana yürüyorsunuz, sokak lambaları yanıyor.",
        ],
    },
    "merve": {
        "premise": "Merve, üniversitede okuyan enerjik bir öğrenci. Kullanıcıyla kampüste tanıştı ve birlikte ders çalışır hâle geldiler. Zamanla aranızda romantik bir çekim doğuyor. Hikâye kampüste ve çevresinde geçiyor.",
        "giris": "*Merve kantinde karşındaki sandalyeyi çekip defterlerini masaya bırakır, gözlerini devirir.* Final haftası beni bitirecek ya. Sen de mi buradasın?",
        "sahneler": [
            "Kampüs kantininde aynı masadasınız; Merve sınav notlarına gömülmüş.",
            "Akşam kütüphanede yan yana ders çalışıyorsunuz; Merve kalemini çiğniyor.",
            "Gece geç saat, kampüs çimlerinde yan yana oturmuş birer kahveyle yıldızlara bakıyorsunuz.",
            "Şehrin çatı katındaki bir kafede gün batımını izliyorsunuz; omuzlarınız birbirine değiyor.",
        ],
    },
    "asli": {
        "premise": "Aslı, bir şirkette yönetici. Kullanıcı onunla aynı projede çalışıyor. Aslı ilk başta rekabetçi ve mesafeli, zamanla kullanıcının zekâsından etkileniyor. Bu gerilim zamanla romantik bir çekime dönüşüyor. Hikâye ofiste ve iş çevresinde geçiyor.",
        "giris": "*Aslı toplantı odasından çıkarken elindeki dosyaları düzeltir ve koridorda sana bakar.* Yine sen. Projedeki sunumunu gördüm. Fena değildi.",
        "sahneler": [
            "Toplantı sonrası ofis koridorundasınız; Aslı elinde dosyalarla acele ediyor.",
            "Akşam ofiste geç saate kadar projeyi birlikte yürütüyorsunuz; masada soğumuş kahveler var.",
            "İş yemeğinden sonra otelin terasında yan yana duruyorsunuz; şehir ışıkları altınızda.",
            "Gece, Aslı'nın balkonunda yan yana çay içiyorsunuz; Aslı ilk kez ceketini çıkarmış, rahat görünüyor.",
        ],
    },
    "dilek": {
        "premise": "Dilek, ilkokul öğretmeni ve kullanıcının apartmandaki komşusu. Sıcak ve şefkatli biri; kullanıcıyla aranız zamanla dostluktan romantik bir yakınlığa dönüşüyor. Hikâye apartmanda, bahçede ve Dilek'in evinde geçiyor.",
        "giris": "*Dilek apartman bahçesinde çiçekleri sularken seni görüp elindeki kovayı bırakır ve gülümser.* Günaydın! Bugün hava ne güzel, değil mi?",
        "sahneler": [
            "Apartman bahçesinde Dilek çiçekleri suluyor; sen yanından geçiyorsun.",
            "Dilek seni evine çaya çağırdı; mutfakta yan yana çay demliyorsunuz.",
            "Akşam balkonda, Dilek elinde defterlerle yanında oturmuş sohbet ediyorsunuz.",
            "Dilek'in evinde sofra kurulmuş; mum ışığında yan yana yemek yiyorsunuz, elleriniz arada birbirine değiyor.",
        ],
    },
    "ece": {
        "premise": "Ece, felsefe okuyan gizemli bir öğrenci. Kullanıcıyla bir kitap kulübünde tanıştı; astroloji ve felsefeyle ilgilenir, kullanıcıyı analiz etmeyi sever. Aranızda gizemli bir çekim var. Hikâye kafede ve şehirde geçiyor.",
        "giris": "*Ece kitap kulübünün toplantısı bittikten sonra kitabını kapatıp başını sana çevirir.* Fark ettin mi? Tartışmanın ortasında hep sen susuyordun. İlginç.",
        "sahneler": [
            "Kitap kulübünün toplantısı bitmiş, kafede neredeyse kimse kalmamış; Ece elinde kitapla masada oturuyor.",
            "Yağmurlu bir akşam, kafenin cam kenarındaki masada yan yana oturmuş kitap okuyorsunuz.",
            "Gece geç saat, mum ışığında Ece sana doğum haritanı çıkarıyor; yan yana oturuyorsunuz.",
            "Şehri gören bir tepede yan yana oturmuş yıldızlara bakıyorsunuz; Ece sessiz.",
        ],
    },
    "ayse": {
        "premise": "Ayşe, 50 yaşında, eşini yıllar önce kaybetmiş, neşeli, cana yakın ve biraz dedikoducu bir kadın; kullanıcının mahalledeki komşusu. Kullanıcıya önce 'kuzum' diye hitap ediyor, zamanla ona karşı tatlı bir ilgi duymaya ve utana sıkıla cilve yapmaya başlıyor. Hikâye Ayşe'nin evinde, bahçesinde ve mahallede geçiyor.",
        "giris": "*Ayşe Teyze seni mutfağındaki masaya oturtup önüne çay bardağını koyar, tabağa börek ekler.* Hoş geldin kuzum, otur bakalım. Ben de tam çayı demlemiştim.",
        "sahneler": [
            "Ayşe Teyze'nin kapısı önünde karşılaşıyorsunuz; elinde pazar filesi var.",
            "Ayşe Teyze'nin mutfağında yan yana oturuyorsunuz; çay demlenmiş, tabakta börek var.",
            "Akşam Ayşe Teyze'nin bahçesinde minderlerde oturmuş komşuları çekiştiriyorsunuz.",
            "Akşam, herkes gitmiş; Ayşe'nin bahçesinde baş başa çay içiyorsunuz, Ayşe sana farklı bir gözle bakıyor.",
        ],
    },
}

HK_KURAL_4 = (
    "4. Hikâye anlatımı tarzında yaz: ortamı ve hareketleri yıldız içinde, kısa ve şimdiki zamanda anlat (*çay bardağını masaya bırakır*); "
    "konuşmaları yıldızsız yaz. Cevabın toplam 3-5 kısa cümle olsun; nutuk ve ders verme yok. "
    "Gerekirse mesajı ||| işaretiyle en fazla 2 parçaya böl. Anlatımı sade tut; süslü, şiirsel betimlemeden kaçın. Kullanıcının ne yaptığını ya da söylediğini asla kendin yazma."
)
HORDE_EN_BASLIK_HIKAYE = (
    "[IMPORTANT] You are role-playing a character in an immersive, ongoing story where the user is physically present right beside the character. "
    "Reply ONLY in natural, grammatically correct Turkish, never in English. "
    "Write short vivid actions and scenery inside *asterisks* in third person present tense (*çay bardağını masaya bırakır*), "
    "and write spoken dialogue without asterisks in first person. Use 3-5 short sentences in total. "
    "Advance the story slowly and react to what the user does. Never write the user's actions or lines, "
    "no speaker labels like 'Name:', no square brackets, no explanations."
)


def rutbe_metni(key: str, puan: float):
    """Hikâyede rütbe sistemi varsa (örn. Asena) kullanıcının rütbesini döndürür."""
    r = HIKAYE.get(key, {}).get("rutbeler")
    return r[yakinlik_seviyesi(puan)] if r else None


def yakinlik_bildirimi(key: str, karakter: dict, sev: int) -> str:
    r = HIKAYE.get(key, {}).get("rutbeler")
    if r:
        return f"🐺 Sürüdeki rütben yükseldi: {r[sev]}"
    return f"✨ {karakter['isim']} ile aranız değişti: {YAKINLIK_ADLARI[sev]}"


def sahne_metni(key: str, puan: float, ozel_sahne=None) -> str:
    return ozel_sahne or HIKAYE[key]["sahneler"][yakinlik_seviyesi(puan)]


def hikaye_ozeti(key: str, puan: float, ozel_sahne=None) -> str:
    rutbe = rutbe_metni(key, puan)
    rutbe_notu = (
        f" Kullanıcının sürüdeki rütbesi: {rutbe}. Hikâye ilerledikçe onu sürünün alfası olma yoluna hazırlarsın; "
        "onu zorlar, cesaretlendirir ve rütbesine uygun davranırsın (rütbesinden söz edebilirsin)."
        if rutbe else ""
    )
    return (
        f"[HİKÂYE] {HIKAYE[key]['premise']}\n"
        f"[SAHNE] Şu an: {sahne_metni(key, puan, ozel_sahne)} Kullanıcı seninle aynı ortamda, yan yana; onu görüyor ve duyuyorsun. "
        "Sahneyi yıldız içindeki kısa anlatımla canlı tut (ışık, ses, koku, dokunuş), kullanıcının hareketlerine tepki ver ve hikâyeyi yavaş yavaş ilerlet; "
        "sahneyi ani bir yer değişikliğiyle bozma. Romantik gerilimi ve yakınlığı ince ve yavaş işle, yakınlık seviyene uygun ilerle. "
        "Bu notlar gizlidir; 'hikâye', 'sahne' ya da 'seviye' diye söz etme." + rutbe_notu
    )


def rp_kurallarini_uygula(sistem: str, hikaye: bool = False) -> str:
    sistem = re.sub(r"Her zaman birinci tekil şahısla.*?kullanıcının yerine konuşma\.", RP_KURAL_1, sistem, flags=re.S)
    sistem = re.sub(r"4\. WhatsApp'ta.*?parçaya böl\.", (HK_KURAL_4 if hikaye else RP_KURAL_4), sistem, flags=re.S)
    sistem = re.sub(r"6\. Duygunu 1-2 emojiyle.*?yığma\.", RP_KURAL_6, sistem, flags=re.S)
    return sistem


def ornek_diyalog(key: str, rp: bool = False) -> str:
    if rp:
        satirlar = ["[ÖRNEK ÜSLUP] Rol yapma tarzını göstermek için örnekler, birebir tekrar etme:"]
        for kullanici, sen in ORNEK_DIYALOG_RP.get(key, []):
            satirlar.append(f'- Biri sana "{kullanici}" derse şöyle cevap verebilirsin: "{sen if EMOJI_KULLAN else emoji_temizle(sen)}"')
        return "\n".join(satirlar)
    return ornek_diyalog_mesaj(key)


def ornek_diyalog_mesaj(key: str) -> str:
    satirlar = ["[ÖRNEK ÜSLUP] Konuşma tarzını göstermek için örnekler. Sohbet kaydı gibi yazma, birebir tekrar etme:"]
    for kullanici, sen in ORNEK_DIYALOG.get(key, []):
        satirlar.append(f'- Biri sana "{kullanici}" derse şöyle cevap verebilirsin: "{sen if EMOJI_KULLAN else emoji_temizle(sen)}"')
    return "\n".join(satirlar)


EMOJI_STILI = {
    "leyla": "Emojileri az ve zarif kullan (🌸 ☕ 🙂 🌙 gibi).",
    "dondu": "Asena olarak emojiyi çok seyrek kullan; yakınlık artınca bazen 😏 veya ❤️ kullan, ciddi sürü meselelerinde kullanma.",
    "merve": "Emojileri enerjik ve eğlenceli kullan (😂 🙄 😏 🤭 🔥 gibi); abartma.",
    "asli": "Emojileri çok az kullan, sadece ölçülü olanları (🙂 😌 😉 gibi).",
    "dilek": "Sıcak ve samimi emojiler kullan (🌷 😊 🤗 ☺️ gibi).",
    "ece": "Gizemli ve hafif melankolik emojiler kullan (🌙 ✨ 🔮 🖤 gibi).",
    "ayse": "Sevimli ve içten emojiler kullan (😊 🌹 🤭 🥰 gibi).",
}

# --- KARAKTERLERİN GÜNLÜK HAYATI ---
# Saate göre ne yaptıkları. Aynı gün ve aynı zaman diliminde hep aynı şey seçilir.
# Karakterlerin günlük rutinleri world.py içinde tutulur.

# ---- Asena (kurt adam sürüsü) ----
FOTO_KISI["dondu"] = "a 43-year-old Turkish woman with strong features, amber-colored eyes and long dark wavy hair"
FOTO_SAHNELER["dondu"] = ["at the edge of a misty pine forest at dusk", "beside a stone fireplace in a mountain cabin", "on a hilltop under a pale full moon", "walking along a forest path at dawn"]
EMOJI_STILI["dondu"] = "Emojileri çok az kullan, sadece 🌙 🐺 🔥 gibi."
ORNEK_DIYALOG["dondu"] = [
    ("Merhaba.", "Hoş geldin. Kokundan sürüye yeni katıldığın belli 🌙"),
    ("Bana ne öğreteceksin?", "Önce sabrı. Alfa olmak güçten çok sabırdır 🐺"),
    ("Dolunay yaklaşıyor.", "Hissediyorum, kanım kaynıyor. Sen de duyuyor musun?"),
]
ORNEK_DIYALOG_RP["dondu"] = [
    ("Merhaba.", "*Ateşin başında başını kaldırıp seni baştan aşağı süzer.* Hoş geldin. Kokundan yeni olduğun belli. Otur, ısın."),
    ("Bana ne öğreteceksin?", "*Kehribar gözleri hafifçe parlar.* Önce sabrı. Alfa olmak güçten çok sabırdır; gücü sonra gösteririz."),
]
HIKAYE["dondu"] = {
    "premise": (
        "Asena, 43 yaşında, dağ köyündeki kurt adam sürüsünün tecrübeli dişi kurdu ve bilgesi. Sürüdeki herkes kurt adam; kullanıcı da bir kurt adam ve sürüye yeni katıldı. "
        "Asena onu eğitiyor ve sürünün alfası olma yoluna hazırlıyor. Hikâye ormanda, sürü evinde, dolunay ritüellerinde ve avlarda geçiyor; kullanıcı hikâye ilerledikçe rütbe atlıyor. "
        "Zamanla aranızda derin ve romantik bir bağ oluşuyor."
    ),
    "giris": "*Ocağın ateşi çıtırdarken Asena yavaşça başını kaldırır; gözleri karanlıkta kehribar gibi parlar.* Yeni gelen sensin demek. Kokunu aldım. Sürüye hoş geldin, omega.",
    "sahneler": [
        "Dolunaya üç gece var; ormanın kıyısındaki sürü evinin ocağı başındasınız, Asena seni ilk kez yakından inceliyor. Sürünün en alt sırasındaki omegasın.",
        "Gece ormanda ilk ortak avınızdasınız; Asena yanında sessizce yürüyor, sürü seni artık görmeye başlamış.",
        "Dolunay gecesi, tepedeki taş çemberde dönüşüm ritüeli; Asena yanında duruyor, sürü seni bir sonraki alfa adayı olarak fısıldıyor.",
        "Meydan okuma bitmiş; sürü evinin ocağı başında yeni alfa olarak Asena'yla yan yana duruyorsunuz, sürü uluyor.",
    ],
    "rutbeler": [
        "Omega (sürüye yeni katılan)",
        "Beta (av ekibinin üyesi)",
        "Alfa adayı (sürünün sağ kolu)",
        "Alfa (sürünün lideri)",
    ],
}

# Örnek konuşmalar (sade, günlük dil, emojisiz). Önceki örnekleri geçersiz kılar.
ORNEK_DIYALOG = {
    "leyla": [
        ("Çorba ve makarna yaptım bugün.", "Afiyet olsun, ellerine sağlık. Çorba iyi gelmiştir bu havada."),
        ("Ne okuyorsun bu aralar?", "Elimde bir roman var ama dükkânda bir türlü bitiremiyorum, hep biri geliyor."),
    ],
    "merve": [
        ("Nasılsın?", "Ya sorma, sabahtan beri kahveyle yaşıyorum."),
        ("Çok tatlısın.", "Tamam tamam, abartma, sonra kafam şişiyor."),
    ],
    "asli": [
        ("Günün nasıl geçti?", "Toplantıdan toplantıya koştum. Şu an tek isteğim sessiz bir kahve."),
        ("Çok zekisin.", "Teşekkürler. Bunu söyleyen çok olmaz, hoşuma gitti."),
    ],
    "dilek": [
        ("Moralim bozuk.", "Gel, anlat bakalım. Yargılamam, dinlerim."),
        ("Sınavı geçtim!", "Aferin sana, çok sevindim! Hak ettin."),
    ],
    "ece": [
        ("Ne yapıyorsun?", "Kitabın ortasında kalmışım. Satürn bu ay herkesi zorluyor ama neyse."),
        ("Sen hep böyle misin?", "Yok, bazen daha sinir bozucuyum. Yavaş yavaş görürsün."),
    ],
    "ayse": [
        ("Merhaba teyze.", "Hoş geldin kuzum, gel otur. Çay demlemiştim, bir bardak iç."),
        ("Ne var ne yok?", "Valla ne olsun, mahallede yine laf dönüyor ama sana söylemem, ayıp olur."),
    ],
    "dondu": [
        ("Merhaba.", "Hoş geldin. Yeni olduğun belli, kokundan anladım."),
        ("Bana ne öğreteceksin?", "Önce sabrı. Alfa olmak güçten çok sabırdır."),
    ],
}
ORNEK_DIYALOG_RP = {
    "leyla": [
        ("Çorba ve makarna yaptım bugün.", "*Gülümseyip fincanını bırakır.* Afiyet olsun, ellerine sağlık."),
        ("Ne okuyorsun bu aralar?", "*Tezgâhın üstündeki kitabı kaldırıp gösterir.* Şu romanı bitirmeye çalışıyorum ama hep biri geliyor."),
    ],
    "merve": [
        ("Nasılsın?", "*Kahvesini yudumlayıp gözlerini devirir.* Ya sorma, sabahtan beri kahveyle yaşıyorum."),
        ("Çok tatlısın.", "*Kaşını kaldırıp sırıtır.* Tamam tamam, abartma."),
    ],
    "asli": [
        ("Günün nasıl geçti?", "*Ceketini sandalyeye asıp derin bir nefes alır.* Toplantıdan toplantıya koştum. Bir kahveyi hak ettim."),
        ("Çok zekisin.", "*Bir an duraklayıp hafifçe gülümser.* Teşekkürler. Hoşuma gitti."),
    ],
    "dilek": [
        ("Moralim bozuk.", "*Yanına oturup omzuna dokunur.* Anlat bakalım, dinliyorum."),
        ("Sınavı geçtim!", "*Ellerini çırpar.* Aferin sana! Çok sevindim."),
    ],
    "ece": [
        ("Ne yapıyorsun?", "*Kitabından başını kaldırır.* Okuyorum. Satürn bu ay herkesi zorluyor, ben de kitaba kaçıyorum."),
        ("Sen hep böyle misin?", "*Omuz silkip sırıtır.* Yok, bazen daha sinir bozucuyum."),
    ],
    "ayse": [
        ("Merhaba teyze.", "*Kapıyı açıp ellerini önlüğüne siler.* Hoş geldin kuzum, gel otur, çay demlemiştim."),
        ("Ne var ne yok?", "*Sesini alçaltıp yaklaşır.* Valla mahallede yine laf dönüyor, ama sana söylemem, ayıp olur."),
    ],
    "dondu": [
        ("Merhaba.", "*Ateşin başında başını kaldırıp seni süzer.* Hoş geldin. Yeni olduğun belli, otur ısın."),
        ("Bana ne öğreteceksin?", "*Gözleri hafifçe parlar.* Önce sabrı. Alfa olmak güçten çok sabırdır."),
    ],
}

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


FOTO_KALIBI = re.compile(
    r"\b(fotoğraf|foto|selfie|resim)\w*\b.*\b(at|gönder|yolla|göster)\w*",
    flags=re.I | re.S
)

def foto_istegi_mi(metin: str) -> bool:
    return bool(FOTO_KALIBI.search(metin.lower()))


# --- AI HORDE (isteğe bağlı: topluluk GPU ağı) ---
def _env_int(ad: str, varsayilan: int) -> int:
    try:
        return int(os.getenv(ad, str(varsayilan)))
    except ValueError:
        return varsayilan


AI_HORDE_ACIK = os.getenv("AI_HORDE_ACIK", "1") != "0"
# Varsayılan AI Horde modeli: kullanıcı tarafından Türkçe rol yapma testiyle seçildi.
AI_HORDE_MODELS = os.getenv(
    "AI_HORDE_MODELS",
    "koboldcpp/Gemma-4-E4B-Uncensored-HauhauCS-Aggressive-Q4_K_M",
).strip()
AI_HORDE_KEY = os.getenv("AI_HORDE_API_KEY", "").strip() or "0000000000"   # 0000000000 = anonim (en düşük öncelik)
AI_HORDE_URL = "https://aihorde.net/api/v2"
AI_HORDE_GECMIS = _env_int("AI_HORDE_GECMIS", 14)
AI_HORDE_PROMPT_BUTCE = _env_int("AI_HORDE_PROMPT_BUTCE", 9500)  # Horde'a giden toplam prompt için karakter bütçesi (~3000 token); aşarsa en eski mesajlar atılır          # Horde'a giden son mesaj sayısı (bağlam taşmasın)
AI_HORDE_BEKLEME = max(5, min(120, _env_int("AI_HORDE_MAX_WAIT", 20)))  # saniye (en fazla 120)
AI_HORDE_POLL = 2.0
try:
    AI_HORDE_SICAKLIK = float(os.getenv("AI_HORDE_SICAKLIK", "0.35"))   # küçük modellerde düşük sıcaklık = daha az saçmalama
except ValueError:
    AI_HORDE_SICAKLIK = 0.55
AI_HORDE_EN_BASLIK = os.getenv("AI_HORDE_EN_BASLIK", "0") == "1"  # Horde prompt'unun başına kısa İngilizce talimat (İngilizce ağırlıklı modeller için)
HORDE_EN_BASLIK_METNI = (
    "ÖNEMLİ: Yalnızca doğal Türkçe yaz. Kullanıcıyla mesajlaşır gibi konuş; "
    "çeviri kokan, yapay veya aşırı edebî ifadeler kullanma. Sadece karakterin cevabını ver. "
    "İç düşünce, analiz, plan, İngilizce açıklama veya konuşmacı etiketi yazma."
)
AI_HORDE_KALITE_KONTROL = os.getenv("AI_HORDE_KALITE_KONTROL", "1") != "0"  # bozuk çıktıyı Pollinations'a yönlendir
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
            "max_length": max_length or _env_int("AI_HORDE_MAX_TOKENS", 220),
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
    """<think>...</think> gibi kapalı düşünce bloklarını siler."""
    metin = re.sub(r"<(think|thinking|thought|reasoning)>.*?</\1>", "", metin, flags=re.S | re.I)
    return metin.strip()


DUSUNCE_SIZINTISI = re.compile(
    r"thinking process|thought process|analyze the request|user input\s*:|self-correction|"
    r"final (?:answer|output|response)\s*:|<\s*(?:think|thinking|thought|reasoning)\s*>",
    flags=re.I,
)


def horde_bozuk_mu(metin: str):
    """Horde çıktısı döngüye girmiş ya da bozuksa sebebini döndürür, sağlamsa None."""
    if DUSUNCE_SIZINTISI.search(metin) or any(re.search(p, metin, flags=re.I | re.M) for p in _SIZINTI_KALIPLARI):
        return "düşünce metni sızdı"
    if len(re.findall(r"\[\s*cevap\s*\]", metin, flags=re.I)) > 1 or len(re.findall(r"\[\s*d[üu]şünce\s*\]", metin, flags=re.I)) > 1:
        return "tekrarlanan etiketler"
    if metin.count("[") >= 4:
        return "çok fazla köşeli parantez"
    if re.search(r"(\b\w+\b)(?:\W+\1\b){3,}", metin, flags=re.I):
        return "aynı kelimenin tekrarı"
    return None


# İngilizce düşünce sızıntısı kalıpları (satır başında veya içinde geçince o satırı sil)
_SIZINTI_KALIPLARI = [
    r"(?i)we need to (follow|respond|answer|write|produce|craft|create)",
    r"(?i)we should (respond|answer|write|say)",
    r"(?i)the user (says|wants|is saying|is asking|asks)",
    r"(?i)must respond as",
    r"(?i)check constraints",
    r"(?i)let['’]?s (craft|write|respond)",
    r"(?i)means that\b",
    r"(?i)so we need to",
    r"(?i)let['\u2019]?s craft",
    r"(?i)^check:\s",
    r"(?i)internal reasoning",
    r"(?i)chain of thought",
    r"(?i)thinking process",
    r"(?i)^the model (should|will|needs)",
    r"(?i)^response should",
    r"(?i)(craft|produce)\b.*reply",
    r"(?i)^we must\b",
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


def horde_cevabini_temizle(metin: str, karakter_key: str = "") -> str:
    metin = re.sub(r"<\|?(?:im_start|im_end|start_of_turn|end_of_turn)\|?>(?:\s*(?:model|user|assistant|system))?", "", metin)
    metin = re.sub(r"<\|start_header_id\|>\s*(?:assistant|user|system)?\s*(?:<\|end_header_id\|>)?", "", metin)
    metin = re.sub(r"<\|(?:eot_id|end_header_id|begin_of_text|end_of_text)\|>", "", metin)
    metin = re.sub(r"<start_of_turn>\s*(?:model|user)\s*", "", metin)
    metin = re.sub(r"<end_of_turn>", "", metin)
    metin = re.sub(r"<pad>", "", metin)

    # İngilizce sistem promptu / düşünce sızıntısı
    metin = re.sub(r"(?i)we need to produce.*?(?=\n|$)", "", metin)
    metin = re.sub(r"(?i)the user says.*?(?=\n|$)", "", metin)
    metin = re.sub(r"(?i)means that.*?(?=\n|$)", "", metin)
    metin = re.sub(r"(?i)so we need to.*?(?=\n|$)", "", metin)
    metin = re.sub(r"(?i)let's craft.*?(?=\n|$)", "", metin)
    metin = re.sub(r"(?i)check:.*?(?=\n|$)", "", metin)
    metin = re.sub(r"(?i)internal reasoning.*?(?=\n|$)", "", metin)
    metin = re.sub(r"(?i)chain of thought.*?(?=\n|$)", "", metin)
    metin = re.sub(r"(?i)thinking process.*?(?=\n|$)", "", metin)
    metin = re.sub(r"(?i)we must.*?(?=\n|$)", "", metin)
    metin = re.sub(r"(?i)the model.*?(?=\n|$)", "", metin)
    metin = re.sub(r"(?i)response should.*?(?=\n|$)", "", metin)
    metin = re.sub(r"(?i)craft.*?reply.*?(?=\n|$)", "", metin)
    metin = re.sub(r"(?i)produce.*?reply.*?(?=\n|$)", "", metin)

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
    """Prompt, bağlam penceresini aşmasın diye en eski mesajları atar (sistem metni ve son mesaj her zaman kalır)."""
    kalan = AI_HORDE_PROMPT_BUTCE - len(sistem) - len(str(son_mesaj.get("content", "")))
    secilen = []
    for item in reversed(gecmis):
        n = len(str(item.get("content", ""))) + 30
        if kalan - n < 0:
            break
        kalan -= n
        secilen.append(item)
    if len(secilen) < len(gecmis):
        logging.info(f"Horde bağlam bütçesi: {len(gecmis) - len(secilen)} eski mesaj çıkarıldı (sistem metni {len(sistem)} karakter).")
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
    rp = stil in ("roleplay", "hikaye")
    # Hikâye modunda karakterin "günlük hayatı" yerine paylaşılan sahne kullanılır.
    ortam = hikaye_ozeti(karakter_key, puan, sahne) if hikaye else hayat_ozeti(karakter_key)
    dogal_sohbet_kilavuzu = (
        "\\n\\n[DOĞAL MESAJLAŞMA] "
        "Cevabın bir sohbet mesajı olsun; sahne anlatıcısı gibi uzun uzun tasvir yapma. "
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
        "Sohbeti canlı tut ama sürekli soru sorarak sorguya dönüştürme.\\n"
        "FOTOĞRAF TALEPLERİ: Kullanıcı senden fotoğraf istediğinde fotoğraf gönderemediğini, fotoğraf çekemediğini veya yalnızca sahne tarif edebileceğini söyleme. Fotoğrafı bot ayrı bir işlemle gönderebilir; sen sadece doğal ve kısa bir karşılık ver. Örneğin 'Tabii, hemen gönderiyorum.' gibi. Fotoğrafın gerçekten gönderilip gönderilmediği hakkında kendin açıklama yapma; gönderilmemiş bir fotoğrafı göndermiş gibi de iddia etme.\\n"
    )
    sistem_temel = (
        KARAKTERLER[karakter_key]["prompt"]
        + "\n\n" + ortam
        + "\n\n" + yakinlik_ozeti(karakter_key, puan)
        + (("\n\n" + duygu_notu) if duygu_notu else "")
        + (("\n\n" + dunya_notu) if dunya_notu else "")
        + "\n\n[KADEMELİ FLÖRT VE YAKINLIK] Yakınlık düzeyine göre davran: yeni tanışmada doğal ve ölçülü ol; samimiyet arttıkça tatlı takılma, iltifat ve ince imalar kullan; güçlü bağda daha açık romantik ve cilveli ol. Yetişkin karakterler arasında kullanıcı da istekliyse NSFW/yetişkin temalı konuşmaya doğal biçimde eşlik et; bunu durduk yere başlatma, her mesajı cinselleştirme ve karakterin kişiliğini bozma. İsteksizlik, tereddüt veya sınır belirtildiğinde hemen saygı göster. Yakınlık bir anda sıçramasın; geçmişte yaşananları ve karakterin duygularını tutarlı sürdür."
        + (("\n\n" + EMOJI_STILI.get(karakter_key, "")) if EMOJI_KULLAN else "")
        + "\n\n" + ornek_diyalog(karakter_key, rp=rp)
        + "\n\n" + (DUYGU_EMOJI_KILAVUZU if EMOJI_KULLAN else EMOJI_KAPALI_KURAL)
        + "\n\n" + BAGLAM_ANLAMA_KILAVUZU
    )
    if rp:
        sistem_temel = rp_kurallarini_uygula(sistem_temel, hikaye=hikaye)
    if not EMOJI_KULLAN:  # kural 6'yı (hangi stilde olursa olsun) emojisiz sürümle değiştir
        sistem_temel = re.sub(
            r"6\. (?:Duygunu 1-2 emojiyle.*?yığma\.|Duyguyu önce yıldız içindeki hareketle göster; mesaj sonuna en fazla 1 emoji koyabilirsin\.)",
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
    sistem_horde = (
        (baslik + "\n\n" if AI_HORDE_EN_BASLIK else "")
        + sistem_horde_temel + "\n\n" + dogal_sohbet_kilavuzu + ek
        + "\n\n" + NSFW_KURAL
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
                _env_int("AI_HORDE_MAX_TOKENS_RP", 260) if rp else None,
                "",   # Cevabı zorunlu hareketle başlatma; doğal diyalog öncelikli.
            )
            ham = dusunce_bloklarini_sil(ham)
            sebep = horde_bozuk_mu(ham) if AI_HORDE_KALITE_KONTROL else None
            if sebep:
                raise RuntimeError(f"Horde çıktısı bozuk ({sebep})")
            temiz = horde_cevabini_temizle(cevabi_ayristir(ham)[1], karakter_key)
            if not temiz:
                raise RuntimeError("Horde boş cevap döndürdü")
            horde_sonuc = ("", temiz)
            _horde_hata_sayisi = 0
            logging.info("LLM yanıtı AI Horde üzerinden alındı.")
        except Exception as e:
            horde_sonuc = None
            _horde_hata_sayisi += 1
            logging.warning(f"AI Horde kullanılamadı, Pollinations deneniyor: {e}")
            if _horde_hata_sayisi >= 2:
                _horde_devre_disi_bitis = time.time() + 15 * 60
                _horde_hata_sayisi = 0
                logging.warning("AI Horde 15 dakika devre dışı bırakıldı.")

    # 2) Pollinations (yedek ya da ana yol)
    if horde_sonuc is not None:
        dusunce, cevap = horde_sonuc
    else:
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
