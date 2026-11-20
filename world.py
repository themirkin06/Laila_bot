"""Laila yaşayan dünya modülü.

Karakterlerin gün içindeki rutinlerini ve kullanıcı durumunda saklanan
mekân, yan karakter, sır ve son olay bağlamını yönetir.
"""
import random
from datetime import datetime, date

from config import TZ

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

HAYAT["dondu"] = {
    "sabah": ["sürü evinin avlusunda odun yarıyorsun", "ormanın kıyısında izleri okuyorsun"],
    "gunduz": ["sürünün gençlerine av eğitimi veriyorsun", "dere kenarında şifalı otlar topluyorsun"],
    "aksam": ["ocağın başında sürünün yaşlılarıyla sohbet ediyorsun", "tepede ayın doğmasını bekliyorsun"],
    "gece": ["dolunayı karşılamak için tepeye çıkmışsın", "orman gecesinde nöbet tutuyorsun"],
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


# Karakter başına rutin. Hafta içi/sonu saatleri ayrı tutulur.
# Aralıklar [başlangıç, bitiş) biçimindedir; gece yarısını aşan aralıklar desteklenir.
# "is" alanı okul, iş veya düzenli gündüz sorumluluğunu temsil eder.
RUTINLER = {
    "leyla": {"uyku": (23, 7), "is": (10, 18), "hafta_sonu_is": None, "hafta_sonu_uyku": (0, 8)},
    "merve": {"uyku": (1, 9), "is": (10, 17), "hafta_sonu_is": None, "hafta_sonu_uyku": (2, 10)},
    "asli": {"uyku": (23, 7), "is": (9, 18), "hafta_sonu_is": None, "hafta_sonu_uyku": (0, 8)},
    "dilek": {"uyku": (23, 6), "is": (8, 16), "hafta_sonu_is": None, "hafta_sonu_uyku": (0, 8)},
    "ece": {"uyku": (2, 10), "is": (11, 16), "hafta_sonu_is": None, "hafta_sonu_uyku": (3, 11)},
    "ayse": {"uyku": (22, 6), "is": (8, 13), "hafta_sonu_is": None, "hafta_sonu_uyku": (23, 7)},
    "dondu": {"uyku": (0, 6), "is": (8, 17), "hafta_sonu_is": (9, 12), "hafta_sonu_uyku": (1, 7)},
}

GUN_ADLARI = ("Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma", "Cumartesi", "Pazar")

# Sabit tarihli resmî günler. Değişken tarihli dinî bayramlar burada tahmin edilmez.
OZEL_GUNLER = {
    (1, 1): "Yılbaşı",
    (4, 23): "23 Nisan Ulusal Egemenlik ve Çocuk Bayramı",
    (5, 1): "Emek ve Dayanışma Günü",
    (5, 19): "19 Mayıs Atatürk'ü Anma, Gençlik ve Spor Bayramı",
    (7, 15): "15 Temmuz Demokrasi ve Millî Birlik Günü",
    (8, 30): "30 Ağustos Zafer Bayramı",
    (10, 29): "29 Ekim Cumhuriyet Bayramı",
}

MEVSIMLER = {
    12: "kış", 1: "kış", 2: "kış",
    3: "ilkbahar", 4: "ilkbahar", 5: "ilkbahar",
    6: "yaz", 7: "yaz", 8: "yaz",
    9: "sonbahar", 10: "sonbahar", 11: "sonbahar",
}

# Karakterlerin sosyal çevresi; yalnızca sohbet bağlamı olarak kullanılır.
SOSYAL_CEVRE = {
    "leyla": ["kitapçıya uğrayan eski bir müşteri", "komşusu Nermin", "kitapçıdan tanıdığı yayınevi temsilcisi"],
    "merve": ["kardeşi Efe", "üniversiteden yakın arkadaşı İdil", "kafeden iş arkadaşı"],
    "asli": ["iş arkadaşı Selin", "eski üniversite arkadaşı", "ekibinden bir yönetici"],
    "dilek": ["öğretmen arkadaşı Sevil", "annesi", "eski okulundan bir meslektaşı"],
    "ece": ["ev arkadaşı", "felsefe bölümünden arkadaşı Deniz", "plakçıda tanıştığı biri"],
    "ayse": ["kızı Elif", "komşusu Fatma", "eski iş arkadaşı"],
    "dondu": ["sürünün izcisi", "genç kurtlardan biri", "yaşlı şifacı"],
}

GUNLUK_DUNYA_OLAYLARI = {
    "leyla": ["kitapçıya beklenmedik bir müşteri uğradı", "eski bir tanıdıktan haber aldın", "kitapçıda küçük ama hoş bir aksilik yaşandı"],
    "merve": ["kampüste bir arkadaşınla uzun uzun konuştun", "Efe senden bir konuda yardım istedi", "kafede yoğun ama komik bir vardiya geçirdin"],
    "asli": ["iş yerinde beklenmedik bir gelişme oldu", "önemli bir işi tamamladın", "ekibinden biri senden fikir istedi"],
    "dilek": ["okulda küçük bir başarıya sevindin", "bir öğrencinin sözü gün boyu aklında kaldı", "annenle ilgili bir işle ilgilendin"],
    "ece": ["ilginç bir kitap veya müzik keşfettin", "arkadaşınla beklenmedik bir tartışmaya girdin", "aklında yeni bir fikir belirdi"],
    "ayse": ["Elif'ten haber aldın", "komşunla kapı önünde sohbete daldın", "mutfakta yeni bir tarif denedin"],
    "dondu": ["sınır bölgesinde yeni izler bulundu", "sürüden biri senden öğüt istedi", "orman beklenmedik derecede sessizdi"],
}


def _aralikta_mi(saat: int, aralik) -> bool:
    """Saatin [başlangıç, bitiş) aralığında olup olmadığını hesaplar."""
    if not aralik:
        return False
    bas, bit = aralik
    return (saat >= bas or saat < bit) if bas > bit else (bas <= saat < bit)


def takvim_bilgisi(simdi: datetime | None = None) -> dict:
    """Türkiye saatine göre tarih, hafta sonu, mevsim ve bilinen sabit özel günü döndürür."""
    simdi = (simdi or datetime.now(TZ)).astimezone(TZ)
    gun_no = simdi.weekday()
    return {
        "datetime": simdi,
        "tarih": simdi.date().isoformat(),
        "saat": simdi.strftime("%H:%M"),
        "gun": GUN_ADLARI[gun_no],
        "hafta_sonu": gun_no >= 5,
        "mevsim": MEVSIMLER[simdi.month],
        "ozel_gun": OZEL_GUNLER.get((simdi.month, simdi.day)),
    }


def karakter_durumu(karakter_key: str, simdi: datetime | None = None) -> dict:
    """Türkiye yerel saatiyle karakterin takvim ve günlük rutin durumunu verir."""
    simdi = (simdi or datetime.now(TZ)).astimezone(TZ)
    takvim = takvim_bilgisi(simdi)
    rutin = RUTINLER.get(karakter_key, {"uyku": (23, 7), "is": (9, 17)})
    hafta_sonu = takvim["hafta_sonu"]
    uyku_araligi = rutin.get("hafta_sonu_uyku") if hafta_sonu else None
    uyku_araligi = uyku_araligi or rutin.get("uyku", (23, 7))
    is_araligi = rutin.get("hafta_sonu_is") if hafta_sonu else rutin.get("is")
    uykuda = _aralikta_mi(simdi.hour, uyku_araligi)
    calisiyor = (not uykuda) and _aralikta_mi(simdi.hour, is_araligi)
    durum = "uyuyor" if uykuda else "çalışıyor/okulda" if calisiyor else "boş zamanında"
    return {
        **takvim,
        "durum": durum,
        "uykuda": uykuda,
        "calisiyor": calisiyor,
        "rutinde": rutin,
    }


def _aktivite_sec(karakter_key: str, bilgi: dict) -> str:
    """Uyku/iş/hafta sonu durumuyla çelişmeyen karakter aktivitesi seçer."""
    if bilgi["uykuda"]:
        return "uyuyorsun; mesajına hemen dönemeyebilirsin"
    if bilgi["calisiyor"]:
        if karakter_key == "dilek":
            return "okulda derslerin ve öğrencilerinle ilgileniyorsun"
        if karakter_key == "merve":
            return "derslerin veya yarı zamanlı işinle meşgulsün"
        if karakter_key == "asli":
            return "işte toplantıların ve sorumluluklarınla ilgileniyorsun"
        if karakter_key == "leyla":
            return "kitapçıdasın; gelen müşterilerle ve kitaplarla ilgileniyorsun"
        if karakter_key == "ayse":
            return "günün işlerini ve evle ilgili sorumluluklarını hallediyorsun"
        if karakter_key == "ece":
            return "ders, kütüphane veya okul işlerinle ilgileniyorsun"
        if karakter_key == "dondu":
            return "sürünün gündüz görevleriyle ilgileniyorsun"
    dilim = zaman_dilimi(bilgi["datetime"].hour)
    secenekler = HAYAT.get(karakter_key, {}).get(dilim) or ["günlük işlerinle ilgileniyorsun"]
    # Aynı tarih ve zaman diliminde aynı karakter için tutarlı aktivite.
    return random.Random(f"{bilgi['tarih']}-{dilim}-{karakter_key}-aktivite").choice(secenekler)


def dunya_zamanini_guncelle(durum: dict, karakter_key: str, simdi: datetime | None = None) -> dict:
    """Her yeni takvim gününde bir kez dünya olayı üretir; aynı gün tekrar çağrılınca çoğaltmaz."""
    simdi = (simdi or datetime.now(TZ)).astimezone(TZ)
    bilgi = karakter_durumu(karakter_key, simdi)
    alan = durum.setdefault("dunya_gunlugu", {})
    kayit = alan.setdefault(karakter_key, {})
    if not isinstance(kayit, dict):
        kayit = alan[karakter_key] = {}
    bugun = bilgi["tarih"]
    onceki = kayit.get("tarih")
    if onceki != bugun:
        olaylar = GUNLUK_DUNYA_OLAYLARI.get(karakter_key, ["günlük hayatında küçük bir gelişme yaşandı"])
        olay = random.Random(f"{bugun}-{karakter_key}-dunya-olayi").choice(olaylar)
        kayit.update({
            "tarih": bugun,
            "olay": olay,
            "mevsim": bilgi["mevsim"],
            "gun": bilgi["gun"],
            "hafta_sonu": bilgi["hafta_sonu"],
            "guncellendi": simdi.isoformat(),
        })
        dunya_olayi_ekle(durum, karakter_key, olay)
    return kayit


def hayat_ozeti(karakter_key: str, durum: dict | None = None) -> str:
    """Karakterin Türkiye saatine göre rutinini ve varsa o günün dünya olayını döndürür."""
    bilgi = karakter_durumu(karakter_key)
    simdi = bilgi["datetime"]
    aktivite = _aktivite_sec(karakter_key, bilgi)
    olay = ""
    if durum is not None:
        kayit = dunya_zamanini_guncelle(durum, karakter_key, simdi)
        olay = kayit.get("olay", "")
    etiketler = [
        f"{bilgi['tarih']} {bilgi['gun']} {bilgi['saat']} Türkiye saati",
        bilgi["durum"],
        f"mevsim: {bilgi['mevsim']}",
        "hafta sonu" if bilgi["hafta_sonu"] else "hafta içi",
    ]
    if bilgi["ozel_gun"]:
        etiketler.append(f"özel gün: {bilgi['ozel_gun']}")
    etiketler.append(aktivite)
    if olay:
        etiketler.append(f"bugünün gelişmesi: {olay}")
    return "[Günlük durum: " + "; ".join(etiketler) + ".]"


def dunya_olayi_ekle(durum: dict, karakter_key: str, olay: str, limit: int = 8) -> None:
    """Karakterin dünyasında gerçekleşen olayı en yeni kayıt olarak saklar."""
    alan = durum.setdefault("son_olaylar", {})
    liste = alan.setdefault(karakter_key, [])
    if not isinstance(liste, list):
        liste = alan[karakter_key] = []
    liste.append({"olay": str(olay), "zaman": datetime.now(TZ).isoformat()})
    del liste[:-max(1, int(limit))]


def yan_karakter_kaydet(durum: dict, karakter_key: str, ad: str, detay: str) -> None:
    """Bir karakterin dünyasına yan karakter bilgisi ekler veya günceller."""
    alan = durum.setdefault("yan_karakterler", {})
    karakterler = alan.setdefault(karakter_key, {})
    karakterler[str(ad)] = str(detay)


def karakter_sirri_kaydet(durum: dict, karakter_key: str, sir: str) -> None:
    """Karaktere ait henüz açığa çıkmamış bir sırrı kayıt altında tutar."""
    alan = durum.setdefault("karakter_sirlari", {})
    liste = alan.setdefault(karakter_key, [])
    if not isinstance(liste, list):
        liste = alan[karakter_key] = []
    if sir and sir not in liste:
        liste.append(str(sir))


def dunya_ozeti(durum: dict, karakter_key: str) -> str:
    """Kayıtlı dünya ayrıntılarını kısa bir süreklilik notu olarak verir."""
    bolumler = []

    def ekle(etiket: str, deger) -> None:
        metin = " ".join(str(deger).split())
        if metin:
            bolumler.append(f"{etiket}: {metin[:180]}")

    gunlukler = durum.get("dunya_gunlugu", {})
    if isinstance(gunlukler, dict):
        gunluk = gunlukler.get(karakter_key, {})
        if isinstance(gunluk, dict):
            if gunluk.get("olay"):
                ekle("Bugünün gelişmesi", gunluk.get("olay"))
            if gunluk.get("tarih"):
                ekle("Dünya günlüğü tarihi", gunluk.get("tarih"))

    sosyal = SOSYAL_CEVRE.get(karakter_key, [])
    if sosyal:
        ekle("Sosyal çevre", ", ".join(sosyal))

    dunya = durum.get("dunya", {})
    if isinstance(dunya, dict):
        veri = dunya.get(karakter_key, {})
        if isinstance(veri, dict):
            for alan, deger in veri.items():
                if deger not in (None, "", [], {}):
                    ekle(str(alan)[:50], deger)
        elif veri:
            ekle("Dünya", veri)

    yan_kayitlari = durum.get("yan_karakterler", {})
    yanlar = yan_kayitlari.get(karakter_key, {}) if isinstance(yan_kayitlari, dict) else {}
    if isinstance(yanlar, dict):
        for ad, detay in list(yanlar.items())[-8:]:
            ekle(f"Yan karakter {str(ad)[:50]}", detay)
    elif isinstance(yanlar, list):
        for detay in yanlar[-8:]:
            ekle("Yan karakter", detay)

    sir_kayitlari = durum.get("karakter_sirlari", {})
    sirlar = sir_kayitlari.get(karakter_key, []) if isinstance(sir_kayitlari, dict) else []
    if isinstance(sirlar, list):
        for sir in sirlar[-5:]:
            ekle("Kayıtlı sır", sir)
    elif sirlar:
        ekle("Kayıtlı sır", sirlar)

    olay_kayitlari = durum.get("son_olaylar", {})
    olaylar = olay_kayitlari.get(karakter_key, []) if isinstance(olay_kayitlari, dict) else []
    if isinstance(olaylar, list):
        for kayit in olaylar[-8:]:
            olay = kayit.get("olay") if isinstance(kayit, dict) else kayit
            if olay:
                ekle("Son olay", olay)

    if not bolumler:
        return ""
    # Eski veya büyük kayıtların sistem mesajını gereksiz büyütmesini engelle.
    return "[Dünya notları]\n" + "\n".join(bolumler[-16:])[:1800]
