"""Laila yaşayan dünya modülü.

Karakterlerin gün içindeki rutinlerini ve kullanıcı durumunda saklanan
mekân, yan karakter, sır ve son olay bağlamını yönetir.
"""
import random
from datetime import datetime

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


# Karakter başına sade rutin çerçevesi. Aralıklar [başlangıç, bitiş) biçimindedir;
# gece yarısını aşan uyku aralıkları da desteklenir. Saat dilimi Türkiye saatidir.
RUTINLER = {
    "leyla": {"uyku": (23, 7), "is": (10, 18)},
    "merve": {"uyku": (1, 9), "is": (10, 17)},
    "asli": {"uyku": (23, 7), "is": (9, 18)},
    "dilek": {"uyku": (23, 6), "is": (8, 16)},
    "ece": {"uyku": (2, 10), "is": (11, 16)},
    "ayse": {"uyku": (22, 6), "is": (8, 13)},
    "dondu": {"uyku": (0, 6), "is": (8, 17)},
}


def karakter_durumu(karakter_key: str, simdi: datetime | None = None) -> dict:
    """Türkiye yerel saatiyle karakterin tarih, saat ve temel günlük durumunu verir."""
    simdi = (simdi or datetime.now(TZ)).astimezone(TZ)
    rutin = RUTINLER.get(karakter_key, {"uyku": (23, 7), "is": (9, 17)})
    saat = simdi.hour
    uyku_bas, uyku_son = rutin["uyku"]
    is_bas, is_son = rutin["is"]
    uykuda = saat >= uyku_bas or saat < uyku_son if uyku_bas > uyku_son else uyku_bas <= saat < uyku_son
    calisiyor = is_bas <= saat < is_son
    durum = "uyuyor" if uykuda else "çalışıyor/okulda" if calisiyor else "boş zamanında"
    return {
        "datetime": simdi,
        "tarih": simdi.date().isoformat(),
        "saat": simdi.strftime("%H:%M"),
        "durum": durum,
        "uykuda": uykuda,
        "calisiyor": calisiyor,
    }


def hayat_ozeti(karakter_key: str) -> str:
    """Karakterin kısa, Türkiye saatine göre günlük durum bilgisini döndürür."""
    bilgi = karakter_durumu(karakter_key)
    simdi = bilgi["datetime"]
    dilim = zaman_dilimi(simdi.hour)
    gun = simdi.strftime("%Y-%m-%d")
    secenekler = HAYAT.get(karakter_key, {}).get(dilim) or ["günlük işlerinle ilgileniyorsun"]
    aktivite = random.Random(f"{gun}-{dilim}-{karakter_key}").choice(secenekler)
    olay = random.Random(f"{gun}-{karakter_key}-olay").choice(GUNLUK_OLAYLAR)
    return (
        f"[Günlük durum: {bilgi['tarih']} {bilgi['saat']} Türkiye saati; "
        f"{bilgi['durum']}; {aktivite}; {olay}.]"
    )


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

    dunya = durum.get("dunya", {})
    if isinstance(dunya, dict):
        veri = dunya.get(karakter_key, {})
        if isinstance(veri, dict):
            for alan, deger in veri.items():
                if deger not in (None, "", [], {}):
                    ekle(str(alan)[:50], deger)
        elif veri:
            ekle("Dünya", veri)

    yanlar = durum.get("yan_karakterler", {}).get(karakter_key, {})
    if isinstance(yanlar, dict):
        for ad, detay in list(yanlar.items())[-8:]:
            ekle(f"Yan karakter {str(ad)[:50]}", detay)
    elif isinstance(yanlar, list):
        for detay in yanlar[-8:]:
            ekle("Yan karakter", detay)

    sirlar = durum.get("karakter_sirlari", {}).get(karakter_key, [])
    if isinstance(sirlar, list):
        for sir in sirlar[-5:]:
            ekle("Kayıtlı sır", sir)
    elif sirlar:
        ekle("Kayıtlı sır", sirlar)

    olaylar = durum.get("son_olaylar", {}).get(karakter_key, [])
    if isinstance(olaylar, list):
        for kayit in olaylar[-8:]:
            olay = kayit.get("olay") if isinstance(kayit, dict) else kayit
            if olay:
                ekle("Son olay", olay)

    if not bolumler:
        return ""
    # Eski veya büyük kayıtların sistem mesajını gereksiz büyütmesini engelle.
    return "[Dünya notları]\n" + "\n".join(bolumler[-16:])[:1800]
