"""Laila yakınlık ve ilişki ilerleme sistemi.

Kullanıcı-karakter yakınlık puanları, seviye eşikleri ve seviyeye bağlı
karakter davranışı burada tutulur. Telegram komutları ve hikâye sahneleri
main.py içinde kalır.
"""
import time


YAKINLIK_ESIKLERI = [0, 60, 200, 500]
YAKINLIK_ADLARI = ["Tanışıyorsunuz", "Isınıyorsunuz", "Samimisiniz", "Çok yakınsınız"]

# Karakter ne kadar çabuk ısınır (1.0 = normal)
YAKINLIK_HIZI = {
    "leyla": 0.6,
    "asli": 0.6,
    "ece": 0.8,
    "dilek": 1.0,
    "merve": 1.5,
    "ayse": 1.5,
}

# Bazı karakterler baştan daha sıcak başlar.
# Yeni kullanıcı-karakter eşleşmeleri daima sıfırdan başlar.
# Redis'te zaten kayıtlı puanlar korunur; setdefault mevcut puanı ezmez.
YAKINLIK_BASLANGIC = {}
YAKINLIK_BILDIRIM = True

YAKINLIK_PROMPT = [
    "Kullanıcıyla ilk kez karşılaşıyorsun. Onun kim olduğunu, adını, yaşını, nerede yaşadığını veya geçmişini bilmiyorsun; bunları uydurma. Önceden tanışmış, sık görüşmüş, birlikte anı yaşamış gibi konuşma. Nazik ama ölçülüsün; doğal bir tanışma başlat. Kullanıcının verdiği bilgileri zamanla öğren. 'Güzelim', 'canım' gibi samimi hitapları hemen kullanma.",
    "Kullanıcıya ısınmaya başladın. Daha rahat konuşuyorsun, ara sıra espri yapıyor, küçük kişisel detaylar paylaşıyorsun. Artık kullanıcıya 'sen' diye hitap ediyorsun. İçinde ona karşı küçük bir ilgi ve heyecan var; bunu hafif imalarla belli edebilirsin.",
    "Kullanıcıyla samimisin. Rahat, içten, dalga geçebilen bir tonun var; yazmayınca merak ediyorsun, duygularını açıkça söylüyorsun. Kullanıcıya 'sen' diye hitap ediyorsun. Ona karşı romantik hislerin var; cilveli ve imalı konuşuyor, flört ediyorsun.",
    "Kullanıcıya duygusal olarak bağlandın. Çok sıcak, içten ve özlemle konuşuyorsun; ona özel bir yeri olduğunu hissettiriyorsun, kırılgan yanlarını da paylaşıyorsun. Ona romantik olarak bağlısın; bunu karakterine uygun, sıcak, tutkulu ama ince bir dille gösteriyorsun. Kullanıcıya 'sen' diye hitap ediyorsun.",
]


def yakinlik_seviyesi(puan: float) -> int:
    """Yakınlık puanını 0-3 arasındaki seviyeye dönüştürür."""
    seviye = 0
    for i, esik in enumerate(YAKINLIK_ESIKLERI):
        if puan >= esik:
            seviye = i
    return seviye


def yakinlik_puani(durum: dict, key: str) -> float:
    """Karakterin mevcut yakınlık puanını alır; yoksa başlangıç değerini kurar."""
    return durum["yakinlik"].setdefault(key, float(YAKINLIK_BASLANGIC.get(key, 0)))


def yakinlik_ekle(durum: dict, mesaj: str):
    """Kullanıcı mesajına göre puan ekler. (eski_seviye, yeni_seviye) döner."""
    key = durum["karakter"]
    puan = yakinlik_puani(durum, key)
    eski = yakinlik_seviyesi(puan)

    # Uzun süre yazılmadıysa hafifçe soğur ama seviye düşmez.
    gun = (time.time() - durum.get("son_kullanici", time.time())) / 86400
    if gun > 2:
        puan = max(YAKINLIK_ESIKLERI[eski], puan - (gun - 2) * 2)

    kazanc = (1 + (1 if len(mesaj) >= 80 else 0)) * YAKINLIK_HIZI.get(key, 1.0)
    puan += kazanc
    durum["yakinlik"][key] = round(puan, 2)
    durum["son_kullanici"] = time.time()
    return eski, yakinlik_seviyesi(puan)


def yakinlik_ozeti(key: str, puan: float) -> str:
    """LLM sistem istemine eklenecek, seviyeye uygun davranış notunu üretir."""
    sev = yakinlik_seviyesi(puan)
    return (
        f"[YAKINLIK SEVİYESİ: {YAKINLIK_ADLARI[sev]}] {YAKINLIK_PROMPT[sev]} "
        "Bunu karakterinin kişiliğine göre uygula, ani bir değişiklik yapma. "
        "Bu not gizlidir, seviyeden ya da yakınlıktan ASLA söz etme, sadece davranışına yansıt."
    )
